//! Inspect candidate layers before granting Docker any decompression work.

use super::{tar_octal, tar_text, validate_tar_checksum, RuntimeControlFailure};
use flate2::read::MultiGzDecoder;
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::time::Instant;

#[derive(Debug, Default, PartialEq, Eq)]
pub(super) struct ExpandedImage {
    pub(super) bytes: u64,
    pub(super) entries: u64,
}

/// Charge every layer, including repeated content, without materializing it.
pub(super) fn validate_layers(
    file: &mut File,
    entries: &HashMap<String, (u64, u64)>,
    layers: &[String],
    config: &[u8],
    maximum_bytes: u64,
    maximum_entries: u64,
    deadline: Instant,
) -> Result<ExpandedImage, RuntimeControlFailure> {
    let config: serde_json::Value = serde_json::from_slice(config).map_err(|_| invalid())?;
    validate_runtime_configuration(&config)?;
    let rootfs = config.get("rootfs").ok_or_else(invalid)?;
    if rootfs.get("type").and_then(|v| v.as_str()) != Some("layers") {
        return Err(invalid());
    }
    let diff_ids = rootfs
        .get("diff_ids")
        .and_then(|v| v.as_array())
        .ok_or_else(invalid)?;
    if diff_ids.len() != layers.len() {
        return Err(invalid());
    }
    let mut expanded = ExpandedImage::default();
    for (layer, expected_digest) in layers.iter().zip(diff_ids) {
        let (offset, size) = *entries.get(layer).ok_or_else(invalid)?;
        if Instant::now() >= deadline {
            return Err(RuntimeControlFailure::DeadlineExceeded);
        }
        if size < 2 {
            return Err(invalid());
        }
        file.seek(SeekFrom::Start(offset)).map_err(|_| invalid())?;
        let mut magic = [0; 2];
        file.read_exact(&mut magic).map_err(|_| invalid())?;
        file.seek(SeekFrom::Start(offset)).map_err(|_| invalid())?;
        let source = file.by_ref().take(size);
        let reader: Box<dyn Read + '_> = if magic == [0x1f, 0x8b] {
            Box::new(MultiGzDecoder::new(source))
        } else {
            Box::new(source)
        };
        let mut stream = LayerStream {
            reader,
            digest: Sha256::new(),
            expanded: &mut expanded,
            maximum_bytes,
            maximum_entries,
            deadline,
        };
        inspect_tar(&mut stream)?;
        if expected_digest.as_str()
            != Some(format!("sha256:{:x}", stream.digest.finalize()).as_str())
        {
            return Err(invalid());
        }
    }
    Ok(expanded)
}

fn validate_runtime_configuration(config: &serde_json::Value) -> Result<(), RuntimeControlFailure> {
    // Docker creates image-declared anonymous volumes before the trusted
    // launcher runs. They would sit outside its bounded filesystem and owner
    // ledger, so this runtime does not admit that image capability.
    if let Some(volumes) = config.get("config").and_then(|value| value.get("Volumes")) {
        if !volumes.is_null() && !volumes.as_object().is_some_and(|value| value.is_empty()) {
            return Err(invalid());
        }
    }
    Ok(())
}

struct LayerStream<'a> {
    reader: Box<dyn Read + 'a>,
    digest: Sha256,
    expanded: &'a mut ExpandedImage,
    maximum_bytes: u64,
    maximum_entries: u64,
    deadline: Instant,
}

impl LayerStream<'_> {
    fn read(&mut self, output: &mut [u8]) -> Result<usize, RuntimeControlFailure> {
        if Instant::now() >= self.deadline {
            return Err(RuntimeControlFailure::DeadlineExceeded);
        }
        let count = self.reader.read(output).map_err(|_| invalid())?;
        self.expanded.bytes = self
            .expanded
            .bytes
            .checked_add(count as u64)
            .ok_or_else(capacity)?;
        if self.expanded.bytes > self.maximum_bytes {
            return Err(capacity());
        }
        self.digest.update(&output[..count]);
        Ok(count)
    }

    fn exact(&mut self, mut output: &mut [u8]) -> Result<(), RuntimeControlFailure> {
        while !output.is_empty() {
            let count = self.read(output)?;
            if count == 0 {
                return Err(invalid());
            }
            output = &mut output[count..];
        }
        Ok(())
    }

    fn discard(&mut self, mut bytes: u64) -> Result<(), RuntimeControlFailure> {
        let mut buffer = [0; 32 * 1024];
        while bytes != 0 {
            let count = usize::try_from(bytes.min(buffer.len() as u64)).map_err(|_| invalid())?;
            self.exact(&mut buffer[..count])?;
            bytes -= count as u64;
        }
        Ok(())
    }

    fn charge_entries(&mut self, count: u64) -> Result<(), RuntimeControlFailure> {
        self.expanded.entries = self
            .expanded
            .entries
            .checked_add(count)
            .ok_or_else(capacity)?;
        // Reserve one allocation block per inode, including implicit directories.
        // Tar payload/padding is charged separately; never subtract whiteouts or
        // assume that repeated files/layers deduplicate on the target daemon.
        self.expanded.bytes = self
            .expanded
            .bytes
            .checked_add(count.checked_mul(4096).ok_or_else(capacity)?)
            .ok_or_else(capacity)?;
        if self.expanded.entries > self.maximum_entries || self.expanded.bytes > self.maximum_bytes
        {
            return Err(capacity());
        }
        Ok(())
    }
}

fn inspect_tar(stream: &mut LayerStream<'_>) -> Result<(), RuntimeControlFailure> {
    let mut next_path: Option<String> = None;
    let mut metadata_pending = false;
    loop {
        let mut header = [0; 512];
        stream.exact(&mut header)?;
        if header.iter().all(|b| *b == 0) {
            if metadata_pending {
                return Err(invalid());
            }
            stream.exact(&mut header)?;
            if header.iter().any(|b| *b != 0) {
                return Err(invalid());
            }
            loop {
                let count = stream.read(&mut header)?;
                if count == 0 {
                    return Ok(());
                }
                if header[..count].iter().any(|b| *b != 0) {
                    return Err(invalid());
                }
            }
        }
        validate_tar_checksum(&header)?;
        if &header[257..263] != b"ustar\0" && &header[257..263] != b"ustar " {
            return Err(invalid());
        }
        let size = tar_octal(&header[124..136])?;
        let padded = size
            .checked_add(511)
            .map(|v| v / 512 * 512)
            .ok_or_else(invalid)?;
        match header[156] {
            b'x' | b'L' | b'K' => {
                // Metadata is bounded independently of the decompression budget.
                if size == 0 || size > 64 * 1024 {
                    return Err(invalid());
                }
                stream.charge_entries(1)?;
                let mut metadata = vec![0; size as usize];
                stream.exact(&mut metadata)?;
                stream.discard(padded - size)?;
                metadata_pending = true;
                if header[156] == b'x' {
                    if let Some(path) = pax_path(&metadata)? {
                        next_path = Some(path);
                    }
                } else {
                    let text = tar_text(&metadata)?;
                    if text.is_empty() || text.len() > 4096 {
                        return Err(invalid());
                    }
                    if header[156] == b'L' {
                        next_path = Some(text);
                    }
                }
            }
            0 | b'0' | b'1' | b'2' | b'5' => {
                if !matches!(header[156], 0 | b'0') && size != 0 {
                    return Err(invalid());
                }
                let path = if let Some(path) = next_path.take() {
                    path
                } else {
                    let name = tar_text(&header[..100])?;
                    // GNU's old header uses this region for other metadata.
                    let prefix = if &header[257..263] == b"ustar\0" {
                        tar_text(&header[345..500])?
                    } else {
                        String::new()
                    };
                    if prefix.is_empty() {
                        name
                    } else {
                        format!("{prefix}/{name}")
                    }
                };
                stream.charge_entries(path_entries(&path)?)?;
                metadata_pending = false;
                stream.discard(padded)?;
            }
            // Sparse, device, FIFO, global PAX and unknown extensions have
            // allocation semantics not covered by this conservative scanner.
            _ => return Err(invalid()),
        }
    }
}

fn path_entries(path: &str) -> Result<u64, RuntimeControlFailure> {
    if path.is_empty() || path.len() > 4096 || path.starts_with('/') || path.contains('\0') {
        return Err(invalid());
    }
    let mut count = 0;
    for part in path.split('/') {
        match part {
            ".." => return Err(invalid()),
            "" | "." => {}
            _ => count += 1,
        }
    }
    Ok(count.max(1))
}

fn pax_path(bytes: &[u8]) -> Result<Option<String>, RuntimeControlFailure> {
    let mut remaining = bytes;
    let mut path = None;
    let mut keys = std::collections::HashSet::new();
    while !remaining.is_empty() {
        let space = remaining
            .iter()
            .position(|b| *b == b' ')
            .ok_or_else(invalid)?;
        let length: usize = std::str::from_utf8(&remaining[..space])
            .map_err(|_| invalid())?
            .parse()
            .map_err(|_| invalid())?;
        if length <= space + 2 || length > remaining.len() || remaining[length - 1] != b'\n' {
            return Err(invalid());
        }
        let record =
            std::str::from_utf8(&remaining[space + 1..length - 1]).map_err(|_| invalid())?;
        let (key, value) = record.split_once('=').ok_or_else(invalid)?;
        if !keys.insert(key) {
            return Err(invalid());
        }
        match key {
            "path" => {
                path_entries(value)?;
                path = Some(value.to_owned());
            }
            "linkpath" if value.len() <= 4096 && !value.contains('\0') => {}
            "mtime" | "atime" | "ctime" | "uid" | "gid" | "uname" | "gname" => {}
            _ if key.starts_with("SCHILY.xattr.") => {}
            // In particular, reject size overrides and every sparse extension.
            _ => return Err(invalid()),
        }
        remaining = &remaining[length..];
    }
    Ok(path)
}

fn invalid() -> RuntimeControlFailure {
    RuntimeControlFailure::InvalidObservation
}
fn capacity() -> RuntimeControlFailure {
    RuntimeControlFailure::CapacityExceeded
}

#[cfg(test)]
mod tests {
    use super::*;
    use flate2::write::GzEncoder;
    use flate2::Compression;
    use std::io::Write;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::time::Duration;

    static SEQUENCE: AtomicU64 = AtomicU64::new(0);

    fn entry(path: &str, kind: u8, body: &[u8]) -> Vec<u8> {
        let mut header = [0; 512];
        header[..path.len()].copy_from_slice(path.as_bytes());
        header[124..136].copy_from_slice(format!("{:011o}\0", body.len()).as_bytes());
        header[148..156].fill(b' ');
        header[156] = kind;
        header[257..263].copy_from_slice(b"ustar\0");
        header[263..265].copy_from_slice(b"00");
        let checksum: u64 = header.iter().map(|v| u64::from(*v)).sum();
        header[148..156].copy_from_slice(format!("{checksum:06o}\0 ").as_bytes());
        let mut result = header.to_vec();
        result.extend(body);
        result.resize(result.len().next_multiple_of(512), 0);
        result
    }

    fn layer(path: &str, body: &[u8]) -> Vec<u8> {
        let mut result = entry(path, b'0', body);
        result.extend([0; 1024]);
        result
    }

    fn gzip(bytes: &[u8]) -> Vec<u8> {
        let mut encoder = GzEncoder::new(Vec::new(), Compression::default());
        encoder.write_all(bytes).unwrap();
        encoder.finish().unwrap()
    }

    fn validate(
        wire: &[u8],
        plain: &[u8],
        copies: usize,
        bytes: u64,
        entries: u64,
    ) -> Result<ExpandedImage, RuntimeControlFailure> {
        let path = std::env::temp_dir().join(format!(
            "ws-image-layers-{}-{}",
            std::process::id(),
            SEQUENCE.fetch_add(1, Ordering::SeqCst)
        ));
        let mut file = std::fs::OpenOptions::new()
            .write(true)
            .read(true)
            .create_new(true)
            .open(&path)
            .unwrap();
        file.write_all(wire).unwrap();
        // Unix unlinks the private temporary immediately; its descriptor stays
        // valid for the bounded reader and no failed assertion leaves a file.
        std::fs::remove_file(path).unwrap();
        let index = HashMap::from([("layer".to_owned(), (0, wire.len() as u64))]);
        let config = serde_json::to_vec(&serde_json::json!({"rootfs": {
            "type": "layers", "diff_ids": vec![format!("sha256:{:x}", Sha256::digest(plain)); copies]
        }})).unwrap();
        validate_layers(
            &mut file,
            &index,
            &vec!["layer".to_owned(); copies],
            &config,
            bytes,
            entries,
            Instant::now() + Duration::from_secs(5),
        )
    }

    #[test]
    fn compressed_and_raw_layers_have_the_same_bound_and_digest() {
        let plain = layer("usr/share/value", b"hello");
        let expected = ExpandedImage {
            bytes: plain.len() as u64 + 3 * 4096,
            entries: 3,
        };
        assert_eq!(validate(&plain, &plain, 1, 65536, 16).unwrap(), expected);
        assert_eq!(
            validate(&gzip(&plain), &plain, 1, 65536, 16).unwrap(),
            expected
        );
        let wrong = layer("usr/share/value", b"other");
        assert_eq!(
            validate(&gzip(&plain), &wrong, 1, 65536, 16),
            Err(invalid())
        );
    }

    #[test]
    fn image_declared_volumes_cannot_create_unaccounted_writable_storage() {
        for volumes in [
            serde_json::json!({"/data": {}}),
            serde_json::json!(["/data"]),
        ] {
            assert_eq!(
                validate_runtime_configuration(
                    &serde_json::json!({"config": {"Volumes": volumes}})
                ),
                Err(invalid())
            );
        }
        validate_runtime_configuration(&serde_json::json!({"config": {"Volumes": {}}})).unwrap();
        validate_runtime_configuration(&serde_json::json!({"config": {"Volumes": null}})).unwrap();
    }

    #[test]
    fn compressed_expansion_and_implicit_directory_limits_fail_before_loading() {
        let plain = layer("value", &vec![0; 1024 * 1024]);
        let compressed = gzip(&plain);
        assert!(compressed.len() < 4096);
        assert_eq!(validate(&compressed, &plain, 1, 65536, 16), Err(capacity()));
        let deep = layer("a/b/c/d/value", b"x");
        assert_eq!(validate(&gzip(&deep), &deep, 1, 65536, 4), Err(capacity()));
    }

    #[test]
    fn repeated_layers_consume_the_aggregate_allowance() {
        let plain = layer("value", b"x");
        let one = validate(&plain, &plain, 1, 65536, 16).unwrap();
        assert_eq!(validate(&plain, &plain, 2, one.bytes, 16), Err(capacity()));
        assert_eq!(validate(&plain, &plain, 2, 65536, 1), Err(capacity()));
        let both = validate(&plain, &plain, 2, 65536, 16).unwrap();
        assert_eq!(both.bytes, 2 * one.bytes);
        assert_eq!(both.entries, 2);
    }

    #[test]
    fn malformed_streams_and_unsupported_sparse_metadata_are_refused() {
        let plain = layer("value", b"x");
        let mut truncated = gzip(&plain);
        truncated.truncate(truncated.len() - 3);
        assert_eq!(validate(&truncated, &plain, 1, 65536, 16), Err(invalid()));
        let mut extra = gzip(&plain);
        extra.extend(b"not gzip");
        assert_eq!(validate(&extra, &plain, 1, 65536, 16), Err(invalid()));
        for kind in [b'S', b'3', b'4', b'6', b'g'] {
            let mut unsupported = entry("value", kind, b"");
            unsupported.extend([0; 1024]);
            assert_eq!(
                validate(&unsupported, &unsupported, 1, 65536, 16),
                Err(invalid())
            );
        }
        assert_eq!(pax_path(b"16 size=1048576\n"), Err(invalid()));
        assert_eq!(pax_path(b"23 GNU.sparse.size=999\n"), Err(invalid()));
    }

    #[test]
    fn bounded_pax_paths_cannot_hide_implicit_directories() {
        let path = "one/two/three/four";
        let record = format!("{} path={}\n", path.len() + 9, path);
        assert_eq!(record.len(), path.len() + 9);
        let mut plain = entry("PaxHeader/value", b'x', record.as_bytes());
        plain.extend(entry("value", b'0', b"x"));
        plain.extend([0; 1024]);
        assert_eq!(
            validate(&gzip(&plain), &plain, 1, 65536, 4),
            Err(capacity())
        );
        assert_eq!(
            validate(&gzip(&plain), &plain, 1, 65536, 5)
                .unwrap()
                .entries,
            5
        );
    }
}
