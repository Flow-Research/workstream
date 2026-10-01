"""Pre-0010 running-row fixture for material-migration preservation/refusal only."""
from datetime import timedelta
from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import ExecutionLease
from app.modules.checkers.execution_repository import ExecutionRepository, reservation


async def predecessor_lease(h):
    """Seed the exact older schema's persisted shape without simulating live AUTH."""
    async with h.factory() as session, session.begin():
        repo = ExecutionRepository(session)
        run = await repo.lock_current(h.request)
        now = await repo.now()
        lease = ExecutionLease(reservation=reservation(run), lease_id=new_record_id(),
            lease_generation=1, expires_at=now + timedelta(seconds=300))
        run.worker_lease_id = str(lease.lease_id)
        run.worker_lease_generation = lease.lease_generation
        run.worker_lease_expires_at = lease.expires_at
        run.execute_evidence_id = str(new_record_id())
        run.started_at = now
        run.status = "running"
        await session.flush()
        return lease
