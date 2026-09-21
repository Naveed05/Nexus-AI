from datetime import timedelta
from uuid import uuid4

from nexus.core.execution_queue import ExecutionQueue, JobStatus


def test_queue_claims_and_completes_durable_job(tmp_path):
    queue = ExecutionQueue(str(tmp_path / "jobs.sqlite3"))
    job = queue.enqueue(uuid4())
    claimed = queue.claim("worker-1")
    assert claimed is not None
    assert claimed.job_id == job.job_id
    assert claimed.status is JobStatus.CLAIMED
    assert claimed.attempts == 1
    assert claimed.lease_until is not None
    completed = queue.complete(job.job_id, worker_id="worker-1")
    assert completed.status is JobStatus.COMPLETED


def test_failed_job_retries_then_dead_letters(tmp_path):
    queue = ExecutionQueue(str(tmp_path / "jobs.sqlite3"), max_attempts=2)
    job = queue.enqueue(uuid4())
    first = queue.claim("worker-1")
    assert queue.complete(first.job_id, worker_id="worker-1", failed=True).status is JobStatus.QUEUED
    second = queue.claim("worker-2")
    assert second.attempts == 2
    assert queue.complete(second.job_id, worker_id="worker-2", failed=True).status is JobStatus.DEAD_LETTER


def test_worker_ownership_is_enforced(tmp_path):
    queue = ExecutionQueue(str(tmp_path / "jobs.sqlite3"))
    job = queue.enqueue(uuid4())
    queue.claim("worker-1")
    try:
        queue.complete(job.job_id, worker_id="worker-2")
        assert False, "expected ownership error"
    except ValueError as exc:
        assert "lease" in str(exc)


def test_expired_lease_can_be_recovered(tmp_path):
    queue = ExecutionQueue(str(tmp_path / "jobs.sqlite3"), lease_seconds=1)
    job = queue.enqueue(uuid4())
    claimed = queue.claim("worker-1")
    assert claimed.lease_until is not None
    with queue._connect() as conn:
        conn.execute("UPDATE execution_jobs SET lease_until = ? WHERE job_id = ?",
                     ((claimed.lease_until - timedelta(seconds=2)).isoformat(), str(job.job_id)))
        conn.commit()
    recovered = queue.claim("worker-2")
    assert recovered is not None
    assert recovered.attempts == 2
    assert recovered.worker_id == "worker-2"
