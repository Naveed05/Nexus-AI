from pathlib import Path
from uuid import uuid4

from nexus.core.distributed_execution import DistributedExecutionBridge
from nexus.core.distributed_workers import WorkerCoordinator
from nexus.core.jobs import DurableJob, JobStatus, JobStore


def test_distributed_bridge_claims_and_completes_a_job(tmp_path: Path) -> None:
    jobs = JobStore(tmp_path / "jobs.sqlite3")
    workers = WorkerCoordinator(tmp_path / "workers.sqlite3")
    worker = workers.register("worker-1", ["analysis"])
    job = DurableJob(uuid4(), "analyze dataset")
    job.checkpoint = {"required_capabilities": ["analysis"]}
    jobs.save(job)

    bridge = DistributedExecutionBridge(jobs, workers)
    lease = bridge.claim_next(worker.worker_id)
    assert lease is not None
    assert lease.job.status is JobStatus.RUNNING
    assert lease.payload()["job"]["job_id"] == str(job.job_id)

    completed = bridge.complete(lease.lease_id, worker.worker_id, {"output": "done"})
    assert completed.status is JobStatus.COMPLETED
    assert workers.get(worker.worker_id).current_job_id is None


def test_distributed_bridge_rejects_capability_mismatch(tmp_path: Path) -> None:
    jobs = JobStore(tmp_path / "jobs.sqlite3")
    workers = WorkerCoordinator(tmp_path / "workers.sqlite3")
    worker = workers.register("worker-1", ["research"])
    job = DurableJob(uuid4(), "train model")
    job.checkpoint = {"required_capabilities": ["ml"]}
    jobs.save(job)

    assert DistributedExecutionBridge(jobs, workers).claim_next(worker.worker_id) is None
    assert jobs.get(job.job_id).status is JobStatus.QUEUED
