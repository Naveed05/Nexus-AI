from uuid import uuid4
import pytest
from nexus.core.distributed_workers import WorkerCoordinator, WorkerStatus


def test_register_persist_and_heartbeat(tmp_path):
    path=str(tmp_path/"workers.sqlite3")
    c=WorkerCoordinator(path,lease_seconds=5)
    w=c.register("worker-a",["python","research"])
    assert w.status is WorkerStatus.ONLINE
    restored=WorkerCoordinator(path).get(w.worker_id)
    assert restored and restored.capabilities==["python","research"]
    c.drain(w.worker_id)
    assert c.heartbeat(w.worker_id).status is WorkerStatus.ONLINE


def test_claim_is_exclusive_and_release_is_idempotent(tmp_path):
    c=WorkerCoordinator(str(tmp_path/"workers.sqlite3"),lease_seconds=5)
    a=c.register("a",["python"]); b=c.register("b",["python"]); job=uuid4()
    lease=c.claim(a.worker_id,job)
    with pytest.raises(ValueError,match="active lease"):
        c.claim(b.worker_id,job)
    released=c.release(lease["lease_id"])
    assert released["released_at"] is not None
    assert c.release(lease["lease_id"])["released_at"] is not None
    assert c.claim(b.worker_id,job)["worker_id"]==str(b.worker_id)


def test_draining_worker_cannot_claim(tmp_path):
    c=WorkerCoordinator(str(tmp_path/"workers.sqlite3"),lease_seconds=5)
    w=c.register("draining",[])
    c.drain(w.worker_id)
    with pytest.raises(ValueError,match="not accepting"):
        c.claim(w.worker_id,uuid4())


def test_metrics_report_capacity(tmp_path):
    c=WorkerCoordinator(str(tmp_path/"workers.sqlite3"),lease_seconds=5)
    a=c.register("a",[]); b=c.register("b",[])
    c.claim(a.worker_id,uuid4())
    m=c.metrics()
    assert m["worker_count"]==2
    assert m["online_count"]==2
    assert m["busy_count"]==1
    assert m["idle_count"]==1


def test_stale_lease_recovery(tmp_path):
    c=WorkerCoordinator(str(tmp_path/"workers.sqlite3"),lease_seconds=5)
    w=c.register("a",[])
    lease=c.claim(w.worker_id,uuid4())
    import sqlite3
    from datetime import datetime,timezone,timedelta
    with sqlite3.connect(c.path) as db:
        old=(datetime.now(timezone.utc)-timedelta(seconds=20)).isoformat()
        db.execute("UPDATE worker_leases SET lease_until=? WHERE lease_id=?",(old,lease["lease_id"]))
        db.commit()
    assert c.recover_stale()==1
    assert c.get(w.worker_id).current_job_id is None
