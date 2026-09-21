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

    completed = queue.complete(job.job_id)
    assert completed.status is JobStatus.COMPLETED
