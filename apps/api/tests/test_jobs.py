import tempfile
from pathlib import Path
from threading import Event
from time import sleep

from nexus.core.jobs import DurableJobManager, JobStatus, JobStore


def test_job_store_persists_and_recovers_interrupted_jobs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "jobs.sqlite3")
        store = JobStore(path)
        job = store.list(limit=1)
        assert job == []
        created = DurableJobManager(store, lambda _: {"ok": True}, auto_start=False).submit("persist me")
        loaded = JobStore(path).get(created.job_id)
        assert loaded is not None
        assert loaded.objective == "persist me"
        loaded.status = JobStatus.RUNNING
        JobStore(path).save(loaded)
        recovered = JobStore(path)
        assert recovered.recover_interrupted() == 1
        assert recovered.get(created.job_id).status == JobStatus.QUEUED


def test_job_manager_executes_and_records_result() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        done = Event()
        def execute(job):
            done.set()
            return {"job_id": str(job.job_id), "verified": True}
        manager = DurableJobManager(JobStore(str(Path(tmp) / "jobs.sqlite3")), execute, poll_interval=0.05)
        try:
            job = manager.submit("run this")
            assert done.wait(2)
            deadline = 2
            while deadline > 0 and manager.get(job.job_id).status != JobStatus.COMPLETED:
                sleep(0.05)
                deadline -= 0.05
            final = manager.get(job.job_id)
            assert final.status == JobStatus.COMPLETED
            assert final.result["verified"] is True
            assert final.version > job.version
        finally:
            manager.stop()


def test_job_manager_retry_is_bounded() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        manager = DurableJobManager(JobStore(str(Path(tmp) / "jobs.sqlite3")), lambda _: (_ for _ in ()).throw(RuntimeError("boom")), auto_start=False)
        job = manager.submit("will fail", max_retries=1)
        failed = manager.retry(job.job_id)
        assert failed.status == JobStatus.RETRYING
        assert failed.retries == 1
        try:
            manager.retry(job.job_id)
        except ValueError:
            pass
        else:
            raise AssertionError("retry budget should be enforced")


def test_job_manager_pause_resume_and_cancel() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        manager = DurableJobManager(JobStore(str(Path(tmp) / "jobs.sqlite3")), lambda _: {"ok": True}, auto_start=False)
        job = manager.submit("pause me")
        paused = manager.pause(job.job_id)
        assert paused.status == JobStatus.PAUSED
        resumed = manager.resume(job.job_id)
        assert resumed.status == JobStatus.QUEUED
        cancelled = manager.cancel(job.job_id)
        assert cancelled.status == JobStatus.CANCELLED
