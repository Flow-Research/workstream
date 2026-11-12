//! Bounded PRE input delivery. Source bytes never become a host file or tree.
use super::*;
use std::process::{ChildStderr, ChildStdin, ChildStdout};
use workstream_checker_guest::pre_bootstrap::PreBootstrapJob;

pub(super) fn connected(stream: &UnixStream) -> bool {
    let mut descriptor = libc::pollfd {
        fd: stream.as_raw_fd(),
        events: libc::POLLRDHUP,
        revents: 0,
    };
    let result = unsafe { libc::poll(&mut descriptor, 1, 0) };
    result >= 0
        && descriptor.revents & (libc::POLLRDHUP | libc::POLLHUP | libc::POLLERR | libc::POLLNVAL)
            == 0
}

struct Session {
    child: Child,
    input: Option<ChildStdin>,
    output: ChildStdout,
    errors: ChildStderr,
    stdout: Vec<u8>,
    stderr_bytes: usize,
    output_eof: bool,
    errors_eof: bool,
    reaped: bool,
    deadline: Instant,
    maximum_control: usize,
    maximum_log: usize,
}
impl Drop for Session {
    fn drop(&mut self) {
        drop(self.input.take());
        if !self.reaped {
            // This process group belongs to this invocation only. VM recovery
            // remains the persisted guardian's responsibility if stop fails.
            let _ = stop_command_group(&mut self.child, Instant::now() + CLEANUP_TIMEOUT);
        }
    }
}
impl Session {
    fn new(mut child: Child, job: &PreBootstrapJob, deadline: Instant) -> Result<Self, String> {
        let descriptors = (child.stdin.take(), child.stdout.take(), child.stderr.take());
        let (Some(input), Some(output), Some(errors)) = descriptors else {
            let _ = stop_command_group(&mut child, Instant::now() + CLEANUP_TIMEOUT);
            return Err("PRE process descriptors unavailable".into());
        };
        let result = Self {
            child,
            input: Some(input),
            output,
            errors,
            stdout: Vec::new(),
            stderr_bytes: 0,
            output_eof: false,
            errors_eof: false,
            reaped: false,
            deadline,
            maximum_control: job.limits.maximum_control_bytes.saturating_add(4),
            maximum_log: job.limits.maximum_log_bytes,
        };
        job.limits.validate()?;
        set_nonblocking(result.input.as_ref().unwrap())?;
        set_nonblocking(&result.output)?;
        set_nonblocking(&result.errors)?;
        Ok(result)
    }
    fn check_cancelled(&self, client: &UnixStream) -> Result<(), String> {
        if Instant::now() >= self.deadline {
            return Err("deadline_exceeded".into());
        }
        if !connected(client) {
            return Err("cancelled".into());
        }
        Ok(())
    }
    fn check(&mut self, client: &UnixStream) -> Result<(), String> {
        // Drain at most 64 KiB per pipe before yielding to input delivery. Logs
        // are counted and discarded, regardless of the configured allowance.
        // Check cancellation between reads even under continuous guest output.
        let mut buffer = [0_u8; 8192];
        for _ in 0..8 {
            self.check_cancelled(client)?;
            let mut progressed = false;
            if !self.output_eof {
                match self.output.read(&mut buffer) {
                    Ok(0) => self.output_eof = true,
                    Ok(count) => {
                        self.stdout
                            .len()
                            .checked_add(count)
                            .filter(|total| *total <= self.maximum_control)
                            .ok_or("PRE output unbounded")?;
                        self.stdout.extend_from_slice(&buffer[..count]);
                        progressed = true;
                    }
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => (),
                    Err(error) if error.kind() == std::io::ErrorKind::Interrupted => {
                        progressed = true
                    }
                    Err(_) => return Err("PRE output failed".into()),
                }
            }
            self.check_cancelled(client)?;
            if !self.errors_eof {
                match self.errors.read(&mut buffer) {
                    Ok(0) => self.errors_eof = true,
                    Ok(count) => {
                        self.stderr_bytes = self
                            .stderr_bytes
                            .checked_add(count)
                            .filter(|total| *total <= self.maximum_log)
                            .ok_or("PRE logs unbounded")?;
                        progressed = true;
                    }
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => (),
                    Err(error) if error.kind() == std::io::ErrorKind::Interrupted => {
                        progressed = true
                    }
                    Err(_) => return Err("PRE logs failed".into()),
                }
            }
            if !progressed {
                break;
            }
        }
        Ok(())
    }
    fn write(&mut self, client: &UnixStream, mut bytes: &[u8]) -> Result<(), String> {
        while !bytes.is_empty() {
            self.check(client)?;
            match self
                .input
                .as_mut()
                .ok_or("PRE input closed")?
                .write(&bytes[..bytes.len().min(65536)])
            {
                Ok(0) => return Err("PRE input closed".into()),
                Ok(count) => bytes = &bytes[count..],
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    thread::sleep(Duration::from_millis(2))
                }
                Err(error) if error.kind() == std::io::ErrorKind::Interrupted => (),
                Err(_) => return Err("PRE input failed".into()),
            }
        }
        Ok(())
    }
    fn receive(&mut self, client: &mut UnixStream, mut bytes: &mut [u8]) -> Result<(), String> {
        while !bytes.is_empty() {
            self.check(client)?;
            match client.read(bytes) {
                Ok(0) => return Err("cancelled".into()),
                Ok(count) => bytes = &mut bytes[count..],
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    thread::sleep(Duration::from_millis(2))
                }
                Err(error) if error.kind() == std::io::ErrorKind::Interrupted => (),
                Err(_) => return Err("PRE source transport failed".into()),
            }
        }
        Ok(())
    }
    fn finish(mut self, client: &UnixStream) -> Result<Vec<u8>, String> {
        drop(self.input.take());
        loop {
            self.check(client)?;
            if !client_is_connected(client) {
                return Err("PRE source contains trailing bytes".into());
            }
            if self.output_eof && self.errors_eof {
                let Some(status) = self
                    .child
                    .try_wait()
                    .map_err(|_| "PRE process wait failed")?
                else {
                    thread::sleep(Duration::from_millis(2));
                    continue;
                };
                self.reaped = true;
                if !status.success() {
                    return Err("PRE guest failed".into());
                }
                if self.stdout.len() < 4 {
                    return Err("PRE result truncated".into());
                }
                let size = u32::from_be_bytes(self.stdout[..4].try_into().unwrap()) as usize;
                if size == 0 || size.checked_add(4) != Some(self.stdout.len()) {
                    return Err("PRE result frame differs".into());
                }
                return Ok(self.stdout.split_off(4));
            }
            thread::sleep(Duration::from_millis(2));
        }
    }
}

pub(super) fn exchange(
    child: Child,
    client: &mut UnixStream,
    root: &mut File,
    job: &PreBootstrapJob,
    deadline: Instant,
) -> Result<Vec<u8>, String> {
    let mut session = Session::new(child, job, deadline)?;
    let bytes = serde_json::to_vec(job).map_err(|_| "PRE job invalid")?;
    if bytes.is_empty() || bytes.len() > MAX_JOB_BYTES {
        return Err("PRE job unbounded".into());
    }
    session.write(client, &(bytes.len() as u32).to_be_bytes())?;
    session.write(client, &bytes)?;
    let mut buffer = [0_u8; 65536];
    let mut remaining = job.root.bundle_byte_count;
    let mut digest = Sha256::new();
    while remaining > 0 {
        session.check(client)?;
        let size = remaining.min(buffer.len() as u64) as usize;
        root.read_exact(&mut buffer[..size])
            .map_err(|_| "PRE root truncated")?;
        digest.update(&buffer[..size]);
        session.write(client, &buffer[..size])?;
        remaining -= size as u64;
    }
    if root
        .read(&mut buffer[..1])
        .map_err(|_| "PRE root unavailable")?
        != 0
        || format!("sha256:{:x}", digest.finalize()) != job.root.bundle_sha256
    {
        return Err("PRE root identity differs".into());
    }
    let source = &job.startup["request"]["reservation"]["source"];
    let expected = source["raw_byte_count"]
        .as_u64()
        .ok_or("PRE source count invalid")?;
    let expected_digest = source["raw_sha256"]
        .as_str()
        .ok_or("PRE source digest invalid")?;
    let mut count = 0_u64;
    let mut digest = Sha256::new();
    loop {
        let mut header = [0; 4];
        session.receive(client, &mut header)?;
        let size = u32::from_be_bytes(header) as usize;
        if size == 0 {
            break;
        }
        if size > buffer.len() {
            return Err("PRE source chunk unbounded".into());
        }
        count = count
            .checked_add(size as u64)
            .filter(|count| *count <= expected)
            .ok_or("PRE source count differs")?;
        session.receive(client, &mut buffer[..size])?;
        digest.update(&buffer[..size]);
        session.write(client, &buffer[..size])?;
    }
    if count != expected || format!("sha256:{:x}", digest.finalize()) != expected_digest {
        return Err("PRE source identity differs".into());
    }
    session.write(client, &[0; 4])?;
    session.finish(client)
}

#[cfg(test)]
mod tests;
