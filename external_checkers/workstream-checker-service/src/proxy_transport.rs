//! Transport-only private Unix framing shared by trusted invocation relays.

use std::fs;
use std::io::{Read, Write};
use std::os::fd::FromRawFd;
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{FileTypeExt, MetadataExt};
use std::os::unix::net::UnixStream;
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

pub(crate) fn validate_private_socket(path: &Path) -> Result<(), String> {
    if !path.is_absolute() {
        return Err("private proxy socket must be absolute".into());
    }
    let parent = path
        .parent()
        .ok_or_else(|| "private proxy socket parent invalid".to_string())?;
    let canonical_parent =
        fs::canonicalize(parent).map_err(|_| "private proxy socket parent unavailable")?;
    let parent_metadata =
        fs::symlink_metadata(parent).map_err(|_| "private proxy socket parent unavailable")?;
    // SAFETY: effective IDs are read-only process attributes.
    let (uid, gid) = unsafe { (libc::geteuid(), libc::getegid()) };
    if canonical_parent != parent
        || !parent_metadata.file_type().is_dir()
        || parent_metadata.file_type().is_symlink()
        || parent_metadata.mode() & 0o777 != 0o700
        || parent_metadata.uid() != uid
        || parent_metadata.gid() != gid
    {
        return Err("private proxy socket parent custody invalid".into());
    }
    let metadata = fs::symlink_metadata(path).map_err(|_| "private proxy socket unavailable")?;
    if metadata.file_type().is_symlink()
        || !metadata.file_type().is_socket()
        || metadata.mode() & 0o777 != 0o600
        || metadata.uid() != uid
        || metadata.gid() != gid
    {
        return Err("private proxy socket invalid".into());
    }
    Ok(())
}

pub(crate) fn read_frame(
    stream: &mut UnixStream,
    maximum: usize,
    deadline: Instant,
    cancelled: &AtomicBool,
) -> Result<Vec<u8>, String> {
    match read_session_frame(stream, maximum, deadline, cancelled)? {
        SessionFrame::Frame(frame) => Ok(frame),
        SessionFrame::Eof => Err("private proxy frame incomplete".into()),
        SessionFrame::Cancelled => Err("private proxy operation cancelled".into()),
    }
}

pub(crate) enum SessionFrame {
    Frame(Vec<u8>),
    Eof,
    Cancelled,
}

/// Distinguish a closed idle session from a truncated or cancelled frame.
pub(crate) fn read_session_frame(
    stream: &mut UnixStream,
    maximum: usize,
    deadline: Instant,
    cancelled: &AtomicBool,
) -> Result<SessionFrame, String> {
    let mut header = [0_u8; 4];
    loop {
        if cancelled.load(Ordering::Acquire) {
            return Ok(SessionFrame::Cancelled);
        }
        if Instant::now() >= deadline {
            return Err("private proxy operation deadline exceeded".into());
        }
        match stream.read(&mut header[..1]) {
            Ok(0) => return Ok(SessionFrame::Eof),
            Ok(_) => break,
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                std::thread::sleep(Duration::from_millis(2));
            }
            Err(_) => return Err("private proxy I/O failed".into()),
        }
    }
    transfer(
        stream,
        &mut header[1..],
        deadline,
        cancelled,
        |stream, bytes| stream.read(bytes),
    )?;
    let size = u32::from_be_bytes(header) as usize;
    if size == 0 || size > maximum {
        return Err("private proxy frame unbounded".into());
    }
    let mut body = vec![0_u8; size];
    transfer(stream, &mut body, deadline, cancelled, |stream, bytes| {
        stream.read(bytes)
    })?;
    Ok(SessionFrame::Frame(body))
}

pub(crate) fn write_frame(
    stream: &mut UnixStream,
    body: &[u8],
    maximum: usize,
    deadline: Instant,
    cancelled: &AtomicBool,
) -> Result<(), String> {
    if body.is_empty() || body.len() > maximum || body.len() > u32::MAX as usize {
        return Err("private proxy frame unbounded".into());
    }
    let mut header = (body.len() as u32).to_be_bytes();
    transfer(stream, &mut header, deadline, cancelled, |stream, bytes| {
        stream.write(bytes)
    })?;
    let mut body = body.to_vec();
    transfer(stream, &mut body, deadline, cancelled, |stream, bytes| {
        stream.write(bytes)
    })
}

fn transfer(
    stream: &mut UnixStream,
    bytes: &mut [u8],
    deadline: Instant,
    cancelled: &AtomicBool,
    mut operation: impl FnMut(&mut UnixStream, &mut [u8]) -> std::io::Result<usize>,
) -> Result<(), String> {
    let mut offset = 0;
    while offset < bytes.len() {
        if cancelled.load(Ordering::Acquire) {
            return Err("private proxy operation cancelled".into());
        }
        if Instant::now() >= deadline {
            return Err("private proxy operation deadline exceeded".into());
        }
        match operation(stream, &mut bytes[offset..]) {
            Ok(0) => return Err("private proxy frame incomplete".into()),
            Ok(count) => offset += count,
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                std::thread::sleep(Duration::from_millis(2));
            }
            Err(_) => return Err("private proxy I/O failed".into()),
        }
    }
    Ok(())
}

pub(crate) fn connect_private(
    path: &Path,
    deadline: Instant,
    cancelled: &AtomicBool,
) -> Result<UnixStream, String> {
    let bytes = path.as_os_str().as_bytes();
    if bytes.is_empty() || bytes.len() >= 108 || bytes.contains(&0) {
        return Err("private proxy socket path invalid".into());
    }
    // SAFETY: socket returns a new descriptor or -1 and has no borrowed inputs.
    let descriptor = unsafe {
        libc::socket(
            libc::AF_UNIX,
            libc::SOCK_STREAM | libc::SOCK_NONBLOCK | libc::SOCK_CLOEXEC,
            0,
        )
    };
    if descriptor < 0 {
        return Err("private proxy connection unavailable".into());
    }
    // SAFETY: zero is a valid initialized representation for sockaddr_un.
    let mut address: libc::sockaddr_un = unsafe { std::mem::zeroed() };
    address.sun_family = libc::AF_UNIX as libc::sa_family_t;
    for (target, source) in address.sun_path.iter_mut().zip(bytes) {
        *target = *source as libc::c_char;
    }
    let length = (std::mem::size_of::<libc::sa_family_t>() + bytes.len() + 1) as libc::socklen_t;
    // SAFETY: descriptor is owned and address/length describe initialized storage.
    let connected = unsafe {
        libc::connect(
            descriptor,
            (&address as *const libc::sockaddr_un).cast(),
            length,
        )
    };
    if connected != 0 {
        let error = std::io::Error::last_os_error();
        if !matches!(
            error.raw_os_error(),
            Some(code) if code == libc::EINPROGRESS || code == libc::EAGAIN
        ) {
            // SAFETY: descriptor is owned and not converted into a UnixStream.
            unsafe { libc::close(descriptor) };
            return Err("private proxy connection unavailable".into());
        }
        loop {
            if cancelled.load(Ordering::Acquire) || Instant::now() >= deadline {
                // SAFETY: descriptor is owned and not converted into a UnixStream.
                unsafe { libc::close(descriptor) };
                return Err("private proxy connection deadline exceeded".into());
            }
            let mut poll = libc::pollfd {
                fd: descriptor,
                events: libc::POLLOUT,
                revents: 0,
            };
            // SAFETY: poll points to one initialized pollfd for the supplied count.
            let ready = unsafe { libc::poll(&mut poll, 1, 2) };
            if ready < 0 {
                // SAFETY: descriptor is owned and not converted into a UnixStream.
                unsafe { libc::close(descriptor) };
                return Err("private proxy connection unavailable".into());
            }
            if ready == 0 {
                continue;
            }
            let mut socket_error: libc::c_int = 0;
            let mut size = std::mem::size_of_val(&socket_error) as libc::socklen_t;
            // SAFETY: pointers refer to writable initialized storage with exact size.
            let status = unsafe {
                libc::getsockopt(
                    descriptor,
                    libc::SOL_SOCKET,
                    libc::SO_ERROR,
                    (&mut socket_error as *mut libc::c_int).cast(),
                    &mut size,
                )
            };
            if status != 0 || socket_error != 0 {
                // SAFETY: descriptor is owned and not converted into a UnixStream.
                unsafe { libc::close(descriptor) };
                return Err("private proxy connection unavailable".into());
            }
            break;
        }
    }
    // SAFETY: descriptor is uniquely owned and successful connect completed above.
    Ok(unsafe { UnixStream::from_raw_fd(descriptor) })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn required_frame_rejects_boundary_eof_and_partial_frames() {
        for partial in [&[][..], &[0, 0][..], &[0, 0, 0, 2, b'{'][..]] {
            let (mut sender, mut receiver) = UnixStream::pair().unwrap();
            sender.write_all(partial).unwrap();
            drop(sender);
            assert!(read_frame(
                &mut receiver,
                1024,
                Instant::now() + Duration::from_secs(2),
                &AtomicBool::new(false)
            )
            .is_err());
        }
    }
}
