//! Qualification of request-scoped preparation. No product policy or admission.

use serde::Serialize;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc,
};
use std::time::{Duration, Instant};

#[derive(Clone)]
pub struct Control {
    deadline: Instant,
    cancelled: Arc<AtomicBool>,
}

impl Control {
    pub fn new(budget: Duration) -> Self {
        Self {
            deadline: Instant::now() + budget,
            cancelled: Arc::new(AtomicBool::new(false)),
        }
    }

    pub fn remaining(&self) -> Result<Duration, &'static str> {
        if self.cancelled.load(Ordering::Acquire) {
            return Err("cancelled");
        }
        self.deadline
            .checked_duration_since(Instant::now())
            .ok_or("deadline_exceeded")
    }

    pub fn cancel(&self) {
        self.cancelled.store(true, Ordering::Release);
    }
}

/// All calls must honor Control. A runtime allocates its owned identity before
/// preparation, so cleanup also covers partial and late creation failures.
pub trait Runtime: Sync {
    fn prepare(&self, control: &Control) -> Result<(), &'static str>;
    fn execute(&self, control: &Control) -> Result<(), &'static str>;
    /// Success requires verified absence, not just a successful delete request.
    fn cleanup(&self, control: &Control) -> Result<(), &'static str>;
}

#[derive(Debug, Serialize)]
pub struct Report {
    pub outcome: &'static str,
    pub failure: Option<&'static str>,
    pub cleanup_confirmed: bool,
    pub upload_ms: u128,
    pub preparation_ms: u128,
    pub post_upload_wait_ms: u128,
    pub execution_ms: u128,
    pub cleanup_ms: u128,
    pub total_ms: u128,
    pub preparation_attempts: usize,
}

/// Prepare while receiving bytes. Retries never renew the request deadline.
/// Upload rejection stops preparation; failed preparation stops a stalled upload.
pub fn run<R, U>(runtime: &R, control: Control, cleanup_budget: Duration, upload: U) -> Report
where
    R: Runtime,
    U: FnOnce(&Control) -> Result<(), &'static str>,
{
    let started = Instant::now();
    let (uploaded, upload_ms, prepared, preparation_ms, attempts) = std::thread::scope(|scope| {
        let prep = scope.spawn(|| {
            let mut attempts = 0;
            let result = loop {
                if let Err(error) = control.remaining() {
                    break Err(error);
                }
                attempts += 1;
                match runtime.prepare(&control) {
                    Ok(()) => break Ok(()),
                    Err(error) => {
                        // Only a known preparation failure is retryable. Never
                        // replay a possibly executed checker or failed cleanup.
                        if error != "preparation_unavailable" || attempts == 3 {
                            break Err(error);
                        }
                        if runtime.cleanup(&control).is_err() {
                            break Err("cleanup_unconfirmed");
                        }
                        // Avoid a tight retry loop; this delay spends the same
                        // absolute work budget as upload and preparation.
                        let delay = Duration::from_millis(50 * attempts as u64);
                        if control.remaining().map_or(true, |left| left <= delay) {
                            break Err("deadline_exceeded");
                        }
                        std::thread::sleep(delay);
                    }
                }
            };
            let elapsed = started.elapsed().as_millis();
            if result.is_err() {
                control.cancel();
            }
            (result, elapsed, attempts)
        });
        let uploaded = upload(&control);
        let upload_ms = started.elapsed().as_millis();
        if uploaded.is_err() {
            control.cancel();
        }
        let (prepared, preparation_ms, attempts) = prep.join().unwrap_or_else(|_| {
            control.cancel();
            (
                Err("preparation_panicked"),
                started.elapsed().as_millis(),
                0,
            )
        });
        (uploaded, upload_ms, prepared, preparation_ms, attempts)
    });
    let ready_ms = started.elapsed().as_millis();
    let outcome = match (uploaded, prepared) {
        // Preserve the cause of cancellation, not its consequence in the peer.
        (Err("cancelled"), Err(error)) => Err(error),
        (Err(error), _) => Err(error),
        (_, Err(error)) => Err(error),
        (Ok(()), Ok(())) => control.remaining().and_then(|_| runtime.execute(&control)),
    };
    let execution_ms = started.elapsed().as_millis() - ready_ms;
    // Cleanup gets an explicit separate budget even when work has expired.
    let cleanup_started = Instant::now();
    let cleanup = runtime.cleanup(&Control::new(cleanup_budget));
    let cleanup_ms = cleanup_started.elapsed().as_millis();
    Report {
        outcome: if outcome.is_ok() && cleanup.is_ok() {
            "completed"
        } else {
            "infrastructure_failed"
        },
        failure: cleanup.err().or(outcome.err()),
        cleanup_confirmed: cleanup.is_ok(),
        upload_ms,
        preparation_ms,
        post_upload_wait_ms: ready_ms.saturating_sub(upload_ms),
        execution_ms,
        cleanup_ms,
        total_ms: started.elapsed().as_millis(),
        preparation_attempts: attempts,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{atomic::AtomicUsize, Mutex};

    struct TestRuntime {
        events: Mutex<Vec<&'static str>>,
        uploading: AtomicBool,
        prepared: AtomicBool,
        uploaded: AtomicBool,
        attempts: AtomicUsize,
        fail_first: bool,
        fail_always: bool,
        fail_cleanup: bool,
        wait_until_cancelled: bool,
    }
    impl TestRuntime {
        fn new() -> Self {
            Self {
                events: Mutex::new(vec![]),
                uploading: AtomicBool::new(false),
                prepared: AtomicBool::new(false),
                uploaded: AtomicBool::new(false),
                attempts: AtomicUsize::new(0),
                fail_first: false,
                fail_always: false,
                fail_cleanup: false,
                wait_until_cancelled: false,
            }
        }
    }
    impl Runtime for TestRuntime {
        fn prepare(&self, c: &Control) -> Result<(), &'static str> {
            self.events.lock().unwrap().push("prepare");
            let n = self.attempts.fetch_add(1, Ordering::SeqCst);
            while !self.uploading.load(Ordering::SeqCst) || self.wait_until_cancelled {
                c.remaining()?;
                std::thread::sleep(Duration::from_millis(1));
            }
            if self.fail_always || (self.fail_first && n == 0) {
                Err("preparation_unavailable")
            } else {
                self.prepared.store(true, Ordering::SeqCst);
                Ok(())
            }
        }
        fn execute(&self, _: &Control) -> Result<(), &'static str> {
            assert!(self.uploaded.load(Ordering::SeqCst));
            assert!(self.prepared.load(Ordering::SeqCst));
            self.events.lock().unwrap().push("execute");
            Ok(())
        }
        fn cleanup(&self, _: &Control) -> Result<(), &'static str> {
            self.events.lock().unwrap().push("cleanup");
            if self.fail_cleanup {
                Err("cleanup_unconfirmed")
            } else {
                Ok(())
            }
        }
    }

    fn upload(r: &TestRuntime, c: &Control) -> Result<(), &'static str> {
        r.uploading.store(true, Ordering::SeqCst);
        while r.attempts.load(Ordering::SeqCst) == 0 {
            c.remaining()?;
            std::thread::yield_now();
        }
        r.uploaded.store(true, Ordering::SeqCst);
        Ok(())
    }

    #[test]
    fn prepares_before_upload_finishes_but_executes_afterwards() {
        let r = TestRuntime::new();
        let report = run(
            &r,
            Control::new(Duration::from_secs(1)),
            Duration::from_secs(1),
            |c| {
                r.uploading.store(true, Ordering::SeqCst);
                while !r.prepared.load(Ordering::SeqCst) {
                    c.remaining()?;
                    std::thread::yield_now();
                }
                assert!(!r.events.lock().unwrap().contains(&"execute"));
                r.uploaded.store(true, Ordering::SeqCst);
                Ok(())
            },
        );
        assert_eq!(report.outcome, "completed");
        assert_eq!(*r.events.lock().unwrap(), ["prepare", "execute", "cleanup"]);
    }

    #[test]
    fn upload_failure_cancels_pending_preparation_before_cleanup() {
        let mut r = TestRuntime::new();
        r.wait_until_cancelled = true;
        let report = run(
            &r,
            Control::new(Duration::from_secs(1)),
            Duration::from_secs(1),
            |c| {
                upload(&r, c)?;
                Err("upload_disconnected")
            },
        );
        assert_eq!(report.failure, Some("upload_disconnected"));
        assert_eq!(*r.events.lock().unwrap(), ["prepare", "cleanup"]);
    }

    #[test]
    fn retries_preparation_only_after_confirmed_cleanup() {
        let mut r = TestRuntime::new();
        r.fail_first = true;
        let report = run(
            &r,
            Control::new(Duration::from_secs(1)),
            Duration::from_secs(1),
            |c| upload(&r, c),
        );
        assert_eq!(report.preparation_attempts, 2);
        assert_eq!(
            *r.events.lock().unwrap(),
            ["prepare", "cleanup", "prepare", "execute", "cleanup"]
        );
    }

    #[test]
    fn repeated_preparation_failure_stops_at_three_without_checker_execution() {
        let mut r = TestRuntime::new();
        r.fail_always = true;
        let report = run(
            &r,
            Control::new(Duration::from_secs(2)),
            Duration::from_secs(1),
            |c| upload(&r, c),
        );
        assert_eq!(report.preparation_attempts, 3);
        assert_eq!(report.failure, Some("preparation_unavailable"));
        assert!(report.cleanup_confirmed);
        assert_eq!(
            *r.events.lock().unwrap(),
            ["prepare", "cleanup", "prepare", "cleanup", "prepare", "cleanup"]
        );
    }

    #[test]
    fn uncertain_cleanup_prevents_retry_and_execution() {
        let mut r = TestRuntime::new();
        r.fail_first = true;
        r.fail_cleanup = true;
        let report = run(
            &r,
            Control::new(Duration::from_secs(1)),
            Duration::from_secs(1),
            |c| upload(&r, c),
        );
        assert_eq!(report.preparation_attempts, 1);
        assert_eq!(report.failure, Some("cleanup_unconfirmed"));
        assert!(!report.cleanup_confirmed);
        assert!(!r.events.lock().unwrap().contains(&"execute"));
    }

    #[test]
    fn successful_check_is_not_success_when_final_cleanup_fails() {
        let mut r = TestRuntime::new();
        r.fail_cleanup = true;
        let report = run(
            &r,
            Control::new(Duration::from_secs(2)),
            Duration::from_secs(1),
            |c| upload(&r, c),
        );
        assert_eq!(report.outcome, "infrastructure_failed");
        assert_eq!(report.failure, Some("cleanup_unconfirmed"));
        assert!(!report.cleanup_confirmed);
        assert_eq!(*r.events.lock().unwrap(), ["prepare", "execute", "cleanup"]);
    }

    #[test]
    fn failed_preparation_cancels_upload_before_its_deadline() {
        let mut r = TestRuntime::new();
        r.fail_always = true;
        let report = run(
            &r,
            Control::new(Duration::from_secs(2)),
            Duration::from_secs(1),
            |c| {
                r.uploading.store(true, Ordering::SeqCst);
                loop {
                    if let Err(error) = c.remaining() {
                        // Deadline expiry would mask a missing peer cancellation.
                        assert_eq!(error, "cancelled");
                        return Err(error);
                    }
                    std::thread::sleep(Duration::from_millis(1));
                }
            },
        );
        assert_eq!(report.failure, Some("preparation_unavailable"));
        assert_eq!(report.preparation_attempts, 3);
        assert!(report.cleanup_confirmed);
        assert!(!r.events.lock().unwrap().contains(&"execute"));
    }

    #[test]
    fn abandoned_upload_and_preparation_share_one_deadline() {
        let mut r = TestRuntime::new();
        r.wait_until_cancelled = true;
        let report = run(
            &r,
            Control::new(Duration::from_millis(30)),
            Duration::from_secs(1),
            |c| {
                r.uploading.store(true, Ordering::SeqCst);
                loop {
                    c.remaining()?;
                    std::thread::sleep(Duration::from_millis(1));
                }
            },
        );
        assert_eq!(report.outcome, "infrastructure_failed");
        assert!(report.cleanup_confirmed);
        assert!(!r.events.lock().unwrap().contains(&"execute"));
    }
}
