//! One atomic node reservation for a checker and its sequential child trials.
use serde::Deserialize;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex,
};

#[derive(Clone, Copy, Debug, Default, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct Capacity {
    pub(crate) slots: usize,
    pub(crate) memory_bytes: u64,
    pub(crate) storage_bytes: u64,
}

impl Capacity {
    fn checked_add(self, other: Self) -> Option<Self> {
        Some(Self {
            slots: self.slots.checked_add(other.slots)?,
            memory_bytes: self.memory_bytes.checked_add(other.memory_bytes)?,
            storage_bytes: self.storage_bytes.checked_add(other.storage_bytes)?,
        })
    }

    fn checked_sub(self, other: Self) -> Option<Self> {
        Some(Self {
            slots: self.slots.checked_sub(other.slots)?,
            memory_bytes: self.memory_bytes.checked_sub(other.memory_bytes)?,
            storage_bytes: self.storage_bytes.checked_sub(other.storage_bytes)?,
        })
    }

    pub(super) fn fits(self, maximum: Self) -> bool {
        self.slots <= maximum.slots
            && self.memory_bytes <= maximum.memory_bytes
            && self.storage_bytes <= maximum.storage_bytes
    }

    fn bounded(self) -> bool {
        self.slots > 0 && self.memory_bytes > 0 && self.storage_bytes > 0
    }
}

#[derive(Clone, Copy, Debug)]
pub(crate) enum Phase {
    Pre,
    Background,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
struct Usage {
    pre: Capacity,
    background: Capacity,
}

impl Usage {
    fn for_phase(&mut self, phase: Phase) -> &mut Capacity {
        match phase {
            Phase::Pre => &mut self.pre,
            Phase::Background => &mut self.background,
        }
    }
}

#[derive(Debug)]
pub(crate) struct Admission {
    used: Mutex<Usage>,
    pre_maximum: Capacity,
    background_maximum: Capacity,
    pub(crate) epoch: String,
    poisoned: AtomicBool,
}

impl Admission {
    pub(crate) fn quarantine(&self) {
        self.poisoned.store(true, Ordering::SeqCst);
    }

    pub(crate) fn reserved_storage_bytes(&self) -> Result<u64, String> {
        let used = self.used.lock().map_err(|_| "node admission unavailable")?;
        if self.poisoned.load(Ordering::SeqCst) {
            return Err("node admission quarantined".into());
        }
        Ok(used.pre.storage_bytes + used.background.storage_bytes)
    }

    pub(crate) fn drain_state(
        &self,
        marker: impl FnOnce() -> Result<bool, String>,
    ) -> Result<(bool, bool), String> {
        let used = self.used.lock().map_err(|_| "node admission unavailable")?;
        if self.poisoned.load(Ordering::SeqCst) {
            return Err("node admission quarantined".into());
        }
        let draining = marker()?;
        Ok((draining, draining && *used == Usage::default()))
    }

    fn required_storage_bytes(&self, phase: Phase, used: Usage) -> Result<u64, String> {
        match phase {
            Phase::Pre => Ok(used.pre.storage_bytes + used.background.storage_bytes),
            Phase::Background => {
                if self.pre_maximum.slots == 0 {
                    return Ok(used.background.storage_bytes);
                }
                // The free-space sample falls as active disks are physically allocated.
                // Leave PRE sufficient free space for the conservative live-peak check
                // even after all declared foreground and background bytes materialize.
                (self.pre_maximum.storage_bytes + used.background.storage_bytes)
                    .checked_mul(2)
                    .ok_or_else(|| "node storage capacity overflow".into())
            }
        }
    }

    pub(crate) fn new(
        maximum: Capacity,
        pre: Option<Capacity>,
        epoch: String,
    ) -> Result<Self, String> {
        if !maximum.bounded() {
            return Err("node capacity must be bounded".into());
        }
        if pre.is_some_and(|capacity| !capacity.bounded()) {
            return Err("PRE reserve must be bounded".into());
        }
        let pre_maximum = pre.unwrap_or_default();
        let background_maximum = maximum
            .checked_sub(pre_maximum)
            .filter(|capacity| capacity.bounded())
            .ok_or("background capacity must remain bounded after PRE reserve")?;
        Ok(Self {
            used: Mutex::new(Usage::default()),
            pre_maximum,
            background_maximum,
            epoch,
            poisoned: AtomicBool::new(false),
        })
    }

    pub(super) fn reserve_with_storage(
        self: &Arc<Self>,
        phase: Phase,
        outer: Capacity,
        child: Option<Capacity>,
        available_storage: impl FnOnce() -> Result<u64, String>,
    ) -> Result<Arc<Reservation>, String> {
        let mut used = self.used.lock().map_err(|_| "node admission unavailable")?;
        let (proposed, charge) =
            self.proposed_usage(*used, phase, outer, child, available_storage)?;
        *used = proposed;
        Ok(Arc::new(Reservation {
            admission: self.clone(),
            phase,
            charge,
            child,
            child_active: AtomicBool::new(false),
        }))
    }

    pub(super) fn fits_with_storage(
        &self,
        phase: Phase,
        outer: Capacity,
        child: Option<Capacity>,
        available_storage: impl FnOnce() -> Result<u64, String>,
    ) -> Result<bool, String> {
        let used = self.used.lock().map_err(|_| "node admission unavailable")?;
        Ok(self
            .proposed_usage(*used, phase, outer, child, available_storage)
            .is_ok())
    }

    fn proposed_usage(
        &self,
        used: Usage,
        phase: Phase,
        outer: Capacity,
        child: Option<Capacity>,
        available_storage: impl FnOnce() -> Result<u64, String>,
    ) -> Result<(Usage, Capacity), String> {
        if outer.slots != 1
            || outer.memory_bytes == 0
            || outer.storage_bytes == 0
            || child.is_some_and(|c| c.slots != 1 || c.memory_bytes == 0 || c.storage_bytes == 0)
            || (matches!(phase, Phase::Pre) && child.is_some())
        {
            return Err("invalid invocation capacity".into());
        }
        let charge = outer
            .checked_add(child.unwrap_or_default())
            .ok_or("capacity overflow")?;
        if self.poisoned.load(Ordering::SeqCst) {
            return Err("node admission quarantined".into());
        }
        let maximum = match phase {
            Phase::Pre => self.pre_maximum,
            Phase::Background => self.background_maximum,
        };
        // Both ceilings are disjoint partitions of the node maximum. Charging either
        // under this same lock keeps their aggregate within the node maximum.
        let mut proposed = used;
        let phase_usage = proposed.for_phase(phase);
        *phase_usage = phase_usage
            .checked_add(charge)
            .filter(|v| v.fits(maximum))
            .ok_or("capacity unavailable")?;
        // The storage observation and both charges share one admission decision.
        // A refused background request never takes even temporary PRE headroom.
        if available_storage()? < self.required_storage_bytes(phase, proposed)? {
            return Err("node storage unavailable".into());
        }
        if self.poisoned.load(Ordering::SeqCst) {
            return Err("node admission quarantined".into());
        }
        Ok((proposed, charge))
    }

    #[cfg(test)]
    pub(crate) fn reserve(
        self: &Arc<Self>,
        phase: Phase,
        outer: Capacity,
        child: Option<Capacity>,
    ) -> Result<Arc<Reservation>, String> {
        self.reserve_with_storage(phase, outer, child, || Ok(u64::MAX))
    }
}

#[derive(Debug)]
pub(crate) struct Reservation {
    pub(crate) admission: Arc<Admission>,
    phase: Phase,
    charge: Capacity,
    child: Option<Capacity>,
    child_active: AtomicBool,
}

impl Reservation {
    /// Consume reserved child capacity without another global admission wait.
    pub(crate) fn child(self: &Arc<Self>, demand: Capacity) -> Result<ChildReservation, String> {
        let limit = self.child.ok_or("trial capacity was not reserved")?;
        if demand.slots != 1
            || demand.memory_bytes == 0
            || demand.storage_bytes == 0
            || !demand.fits(limit)
        {
            return Err("child exceeds reserved capacity".into());
        }
        let _used = self
            .admission
            .used
            .lock()
            .map_err(|_| "node admission unavailable")?;
        if self.admission.poisoned.load(Ordering::SeqCst) {
            return Err("node admission quarantined".into());
        }
        self.child_active
            .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .map_err(|_| "child capacity already in use")?;
        Ok(ChildReservation {
            parent: self.clone(),
        })
    }
}

impl Drop for Reservation {
    fn drop(&mut self) {
        // Poisoned admission remains closed; never invent capacity after a panic.
        if let Ok(mut used) = self.admission.used.lock() {
            let used = used.for_phase(self.phase);
            used.slots -= self.charge.slots;
            used.memory_bytes -= self.charge.memory_bytes;
            used.storage_bytes -= self.charge.storage_bytes;
        }
    }
}

#[derive(Debug)]
pub(crate) struct ChildReservation {
    parent: Arc<Reservation>,
}

impl ChildReservation {
    /// Keep the full invocation charge and reject new work after uncertain cleanup.
    pub(crate) fn quarantine(self) {
        self.parent.admission.quarantine();
        std::mem::forget(self);
    }
}

impl Drop for ChildReservation {
    fn drop(&mut self) {
        self.parent.child_active.store(false, Ordering::SeqCst);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Barrier;

    fn amount(slots: usize, memory_bytes: u64, storage_bytes: u64) -> Capacity {
        Capacity {
            slots,
            memory_bytes,
            storage_bytes,
        }
    }

    #[test]
    fn one_slot_node_refuses_trial_before_reserving_outer() {
        let node = Arc::new(Admission::new(amount(1, 200, 200), None, "test".into()).unwrap());
        assert!(node
            .reserve(
                Phase::Background,
                amount(1, 10, 10),
                Some(amount(1, 10, 10))
            )
            .is_err());
        assert!(node
            .reserve(Phase::Background, amount(1, 10, 10), None)
            .is_ok());
        assert!(node.reserve(Phase::Pre, amount(1, 10, 10), None).is_err());
    }

    #[test]
    fn pre_reserve_must_leave_bounded_background_capacity() {
        let maximum = amount(2, 20, 20);
        for invalid in [
            amount(0, 10, 10),
            amount(1, 0, 10),
            amount(1, 10, 0),
            amount(2, 10, 10),
            amount(1, 20, 10),
            amount(1, 10, 20),
            amount(3, 21, 21),
        ] {
            assert!(Admission::new(maximum, Some(invalid), "test".into()).is_err());
        }
    }

    #[test]
    fn runner_placement_checks_exact_peak_and_storage_without_claiming() {
        let pre = amount(1, 8, 16);
        let job = amount(1, 6, 7);
        let node = Arc::new(Admission::new(amount(3, 20, 30), Some(pre), "test".into()).unwrap());
        for (outer, child, free) in [
            (amount(1, 7, 7), job, 60),
            (job, amount(1, 6, 8), 60),
            (job, job, 59),
        ] {
            assert!(!node
                .fits_with_storage(Phase::Background, outer, Some(child), || Ok(free))
                .unwrap());
        }
        assert!(node
            .fits_with_storage(Phase::Background, job, Some(job), || Ok(60))
            .unwrap());
        assert_eq!(node.reserved_storage_bytes().unwrap(), 0);
        let _held = node
            .reserve_with_storage(Phase::Background, job, Some(job), || Ok(60))
            .unwrap();
        assert!(!node
            .fits_with_storage(Phase::Background, job, None, || Ok(60))
            .unwrap());
        assert!(node
            .fits_with_storage(Phase::Pre, pre, None, || Ok(30))
            .unwrap());
        assert_eq!(node.reserved_storage_bytes().unwrap(), 14);
    }

    #[test]
    fn saturated_background_trial_leaves_pre_capacity_and_disk_headroom() {
        let pre = amount(1, 8, 16);
        let job = amount(1, 6, 7);
        let node = Arc::new(Admission::new(amount(3, 20, 30), Some(pre), "test".into()).unwrap());
        let post = node
            .reserve_with_storage(Phase::Background, job, Some(job), || Ok(60))
            .unwrap();
        let child = post.child(job).unwrap();
        assert_eq!(node.reserved_storage_bytes().unwrap(), 14);
        assert!(node.reserve(Phase::Background, job, None).is_err());
        let foreground = node
            .reserve_with_storage(Phase::Pre, pre, None, || Ok(30))
            .unwrap();
        assert!(node.reserve(Phase::Pre, pre, None).is_err());

        drop(post);
        assert!(node.reserve(Phase::Background, job, None).is_err());
        drop(child);
        assert_eq!(node.reserved_storage_bytes().unwrap(), 16);
        assert!(node.reserve(Phase::Background, job, Some(job)).is_ok());
        drop(foreground);
        assert_eq!(node.reserved_storage_bytes().unwrap(), 0);
    }

    #[test]
    fn physical_headroom_overflow_refuses_background_without_changing_pre() {
        let pre = amount(1, 10, 1);
        let background = amount(1, 10, u64::MAX / 2);
        let node =
            Arc::new(Admission::new(amount(2, 20, u64::MAX), Some(pre), "test".into()).unwrap());
        assert!(node.reserve(Phase::Background, background, None).is_err());
        assert_eq!(node.reserved_storage_bytes().unwrap(), 0);
        assert!(node
            .reserve_with_storage(Phase::Pre, pre, None, || Ok(pre.storage_bytes))
            .is_ok());
    }

    #[test]
    fn tentative_background_storage_cannot_displace_foreground() {
        let pre = amount(1, 10, 16);
        let post = amount(1, 10, 14);
        let node = Arc::new(Admission::new(amount(2, 20, 30), Some(pre), "test".into()).unwrap());
        let checking_storage = Arc::new(Barrier::new(2));
        let finish_storage_check = Arc::new(Barrier::new(2));
        let background = {
            let node = node.clone();
            let checking_storage = checking_storage.clone();
            let finish_storage_check = finish_storage_check.clone();
            std::thread::spawn(move || {
                node.reserve_with_storage(Phase::Background, post, None, || {
                    checking_storage.wait();
                    finish_storage_check.wait();
                    Ok(30)
                })
            })
        };
        checking_storage.wait();
        let free = 16;
        let storage_and_usage_locked = matches!(
            node.used.try_lock(),
            Err(std::sync::TryLockError::WouldBlock)
        );
        let foreground = {
            let node = node.clone();
            std::thread::spawn(move || {
                node.reserve_with_storage(Phase::Pre, pre, None, || Ok(free))
            })
        };
        finish_storage_check.wait();
        assert!(background.join().unwrap().is_err());
        assert!(foreground.join().unwrap().is_ok());
        assert!(storage_and_usage_locked);
    }

    #[test]
    fn every_limit_is_atomic_and_failed_admission_leaks_nothing() {
        for limit in [amount(1, 200, 200), amount(2, 19, 200), amount(2, 200, 19)] {
            let node = Arc::new(Admission::new(limit, None, "test".into()).unwrap());
            assert!(node
                .reserve(
                    Phase::Background,
                    amount(1, 10, 10),
                    Some(amount(1, 10, 10))
                )
                .is_err());
            assert_eq!(*node.used.lock().unwrap(), Usage::default());
        }
    }

    #[test]
    fn child_keeps_peak_reservation_alive_and_is_exclusive() {
        let node = Arc::new(Admission::new(amount(2, 20, 20), None, "test".into()).unwrap());
        let held = node
            .reserve(
                Phase::Background,
                amount(1, 10, 10),
                Some(amount(1, 10, 10)),
            )
            .unwrap();
        assert!(held.child(amount(1, 11, 10)).is_err());
        let child = held.child(amount(1, 10, 10)).unwrap();
        assert!(held.child(amount(1, 10, 10)).is_err());
        drop(held);
        assert!(node
            .reserve(Phase::Background, amount(1, 1, 1), None)
            .is_err());
        drop(child);
        assert_eq!(*node.used.lock().unwrap(), Usage::default());
        assert!(node
            .reserve(Phase::Background, amount(1, 10, 10), None)
            .is_ok());
    }

    #[test]
    fn competing_invocations_cannot_split_peak_capacity() {
        let node = Arc::new(Admission::new(amount(2, 20, 20), None, "test".into()).unwrap());
        let barrier = Arc::new(Barrier::new(3));
        let workers: Vec<_> = (0..2)
            .map(|_| {
                let node = node.clone();
                let barrier = barrier.clone();
                std::thread::spawn(move || {
                    barrier.wait();
                    let held = node.reserve(
                        Phase::Background,
                        amount(1, 10, 10),
                        Some(amount(1, 10, 10)),
                    );
                    barrier.wait();
                    held
                })
            })
            .collect();
        barrier.wait();
        barrier.wait();
        let held: Vec<_> = workers.into_iter().map(|w| w.join().unwrap()).collect();
        assert_eq!(held.iter().filter(|v| v.is_ok()).count(), 1);
        drop(held);
        assert_eq!(*node.used.lock().unwrap(), Usage::default());
    }

    #[test]
    fn unsettled_child_quarantines_the_node_until_restart() {
        let node = Arc::new(
            Admission::new(amount(3, 30, 30), Some(amount(1, 10, 10)), "test".into()).unwrap(),
        );
        let held = node
            .reserve(
                Phase::Background,
                amount(1, 10, 10),
                Some(amount(1, 10, 10)),
            )
            .unwrap();
        held.child(amount(1, 10, 10)).unwrap().quarantine();
        drop(held);
        assert!(node.reserve(Phase::Pre, amount(1, 1, 1), None).is_err());
        assert!(node
            .reserve(Phase::Background, amount(1, 1, 1), None)
            .is_err());
        assert!(node.reserved_storage_bytes().is_err());
        assert_eq!(node.used.lock().unwrap().background.storage_bytes, 20);
    }

    #[test]
    fn uncertain_scratch_cleanup_closes_admission_after_credit_release() {
        let node = Arc::new(Admission::new(amount(2, 20, 20), None, "test".into()).unwrap());
        let held = node
            .reserve(
                Phase::Background,
                amount(1, 10, 10),
                Some(amount(1, 10, 10)),
            )
            .unwrap();
        node.quarantine();
        drop(held);
        assert_eq!(*node.used.lock().unwrap(), Usage::default());
        assert!(node
            .reserve(Phase::Background, amount(1, 1, 1), None)
            .is_err());
        assert!(node.reserved_storage_bytes().is_err());
    }
}
