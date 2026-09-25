from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import json
import sqlite3
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4


class WorkerStatus(str, Enum):
    ONLINE="online"
    DRAINING="draining"
    OFFLINE="offline"


@dataclass
class Worker:
    worker_id: UUID
    name: str
    capabilities: list[str]
    status: WorkerStatus = WorkerStatus.ONLINE
    registered_at: datetime | None = None
    last_heartbeat: datetime | None = None
    current_job_id: UUID | None = None
    lease_until: datetime | None = None


class WorkerCoordinator:
    """SQLite-backed worker registry and lease coordinator.

    Claims are short-lived leases. A worker must heartbeat to retain ownership;
    stale leases are recoverable after the configured timeout.
    """

    def __init__(self, path=".nexus/workers.sqlite3", lease_seconds=30):
        if lease_seconds < 5:
            raise ValueError("lease_seconds must be at least 5")
        self.path=path
        self.lease_seconds=lease_seconds
        self._lock=RLock()
        if path!=":memory:": Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self._connect() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS workers(
                worker_id TEXT PRIMARY KEY,name TEXT NOT NULL,capabilities TEXT NOT NULL,
                status TEXT NOT NULL,registered_at TEXT NOT NULL,last_heartbeat TEXT NOT NULL,
                current_job_id TEXT,lease_until TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS worker_leases(
                lease_id TEXT PRIMARY KEY,worker_id TEXT NOT NULL,job_id TEXT NOT NULL,
                claimed_at TEXT NOT NULL,heartbeat_at TEXT NOT NULL,lease_until TEXT NOT NULL,
                released_at TEXT)""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_worker_leases_job ON worker_leases(job_id,lease_until)")
            c.commit()

    def _connect(self):
        c=sqlite3.connect(self.path,timeout=10)
        c.row_factory=sqlite3.Row
        return c

    @staticmethod
    def _now(): return datetime.now(timezone.utc)

    def register(self,name,capabilities=(),worker_id=None):
        now=self._now(); wid=worker_id or uuid4()
        worker=Worker(wid,name.strip(),sorted(set(str(x).strip() for x in capabilities if str(x).strip())),
                      WorkerStatus.ONLINE,now,now)
        if not worker.name: raise ValueError("worker name cannot be empty")
        with self._lock,self._connect() as c:
            c.execute("INSERT OR REPLACE INTO workers VALUES(?,?,?,?,?,?,?,?)",
                      (str(wid),worker.name,json.dumps(worker.capabilities),worker.status.value,
                       now.isoformat(),now.isoformat(),None,None))
            c.commit()
        return worker

    def get(self,worker_id):
        with self._lock,self._connect() as c:
            r=c.execute("SELECT * FROM workers WHERE worker_id=?",(str(worker_id),)).fetchone()
        return self._row(r) if r else None

    def list(self,limit=100):
        if limit<1 or limit>500: raise ValueError("limit must be between 1 and 500")
        with self._lock,self._connect() as c:
            rows=c.execute("SELECT * FROM workers ORDER BY registered_at DESC LIMIT ?",(limit,)).fetchall()
        return [self._row(r) for r in rows]

    def heartbeat(self,worker_id,*,preserve_status=False):
        now=self._now()
        with self._lock,self._connect() as c:
            r=c.execute("SELECT * FROM workers WHERE worker_id=?",(str(worker_id),)).fetchone()
            if not r: raise KeyError("unknown worker")
            if r["status"]==WorkerStatus.OFFLINE.value: raise ValueError("offline workers cannot heartbeat")
            if preserve_status:
                c.execute("UPDATE workers SET last_heartbeat=? WHERE worker_id=?",
                          (now.isoformat(),str(worker_id)))
            else:
                c.execute("UPDATE workers SET last_heartbeat=?,status=? WHERE worker_id=?",
                          (now.isoformat(),WorkerStatus.ONLINE.value,str(worker_id)))
            c.execute("UPDATE worker_leases SET heartbeat_at=?,lease_until=? WHERE worker_id=? AND released_at IS NULL",
                      (now.isoformat(),(now+timedelta(seconds=self.lease_seconds)).isoformat(),str(worker_id)))
            c.commit()
        return self.get(worker_id)

    def drain(self,worker_id):
        with self._lock,self._connect() as c:
            if not c.execute("SELECT 1 FROM workers WHERE worker_id=?",(str(worker_id),)).fetchone():
                raise KeyError("unknown worker")
            c.execute("UPDATE workers SET status=? WHERE worker_id=?",(WorkerStatus.DRAINING.value,str(worker_id)))
            c.commit()
        return self.get(worker_id)

    def claim(self,worker_id,job_id):
        now=self._now(); expiry=now+timedelta(seconds=self.lease_seconds)
        with self._lock,self._connect() as c:
            worker=c.execute("SELECT * FROM workers WHERE worker_id=?",(str(worker_id),)).fetchone()
            if not worker: raise KeyError("unknown worker")
            if worker["status"]!=WorkerStatus.ONLINE.value: raise ValueError("worker is not accepting jobs")
            active=c.execute("SELECT lease_id FROM worker_leases WHERE job_id=? AND released_at IS NULL AND lease_until>?",
                             (str(job_id),now.isoformat())).fetchone()
            if active: raise ValueError("job already has an active lease")
            lease_id=uuid4()
            c.execute("INSERT INTO worker_leases VALUES(?,?,?,?,?,?,?)",
                      (str(lease_id),str(worker_id),str(job_id),now.isoformat(),now.isoformat(),expiry.isoformat(),None))
            c.execute("UPDATE workers SET current_job_id=?,lease_until=? WHERE worker_id=?",
                      (str(job_id),expiry.isoformat(),str(worker_id)))
            c.commit()
        return {"lease_id":str(lease_id),"worker_id":str(worker_id),"job_id":str(job_id),
                "claimed_at":now.isoformat(),"lease_until":expiry.isoformat()}

    def release(self,lease_id):
        now=self._now()
        with self._lock,self._connect() as c:
            r=c.execute("SELECT * FROM worker_leases WHERE lease_id=?",(str(lease_id),)).fetchone()
            if not r: raise KeyError("unknown lease")
            if r["released_at"]: return dict(r)
            c.execute("UPDATE worker_leases SET released_at=? WHERE lease_id=?",(now.isoformat(),str(lease_id)))
            c.execute("UPDATE workers SET current_job_id=NULL,lease_until=NULL WHERE worker_id=? AND current_job_id=?",
                      (r["worker_id"],r["job_id"]))
            c.commit()
        with self._connect() as verify:
            row = verify.execute("SELECT * FROM worker_leases WHERE lease_id=?", (str(lease_id),)).fetchone()
        return dict(row)

    def recover_stale(self):
        now=self._now(); count=0
        with self._lock,self._connect() as c:
            stale=c.execute("SELECT * FROM worker_leases WHERE released_at IS NULL AND lease_until<=?",(now.isoformat(),)).fetchall()
            for r in stale:
                c.execute("UPDATE worker_leases SET released_at=? WHERE lease_id=?",(now.isoformat(),r["lease_id"]))
                c.execute("UPDATE workers SET current_job_id=NULL,lease_until=NULL WHERE worker_id=? AND current_job_id=?",
                          (r["worker_id"],r["job_id"]))
                count+=1
            c.execute("UPDATE workers SET status=? WHERE status=? AND last_heartbeat<?",
                      (WorkerStatus.OFFLINE.value,WorkerStatus.ONLINE.value,
                       (now-timedelta(seconds=self.lease_seconds*2)).isoformat()))
            c.commit()
        return count

    def metrics(self):
        self.recover_stale()
        workers=self.list(500)
        now=self._now()
        active=sum(w.current_job_id is not None for w in workers)
        return {"worker_count":len(workers),"online_count":sum(w.status is WorkerStatus.ONLINE for w in workers),
                "draining_count":sum(w.status is WorkerStatus.DRAINING for w in workers),
                "offline_count":sum(w.status is WorkerStatus.OFFLINE for w in workers),
                "busy_count":active,"idle_count":len(workers)-active,
                "lease_seconds":self.lease_seconds,
                "heartbeat_age_seconds":{str(w.worker_id):max(0,(now-(w.last_heartbeat or now)).total_seconds()) for w in workers}}

    @staticmethod
    def _row(r):
        return Worker(UUID(r["worker_id"]),r["name"],json.loads(r["capabilities"] or "[]"),WorkerStatus(r["status"]),
                      datetime.fromisoformat(r["registered_at"]),datetime.fromisoformat(r["last_heartbeat"]),
                      UUID(r["current_job_id"]) if r["current_job_id"] else None,
                      datetime.fromisoformat(r["lease_until"]) if r["lease_until"] else None)


def worker_payload(w):
    return {"worker_id":str(w.worker_id),"name":w.name,"capabilities":w.capabilities,"status":w.status.value,
            "registered_at":w.registered_at.isoformat() if w.registered_at else None,
            "last_heartbeat":w.last_heartbeat.isoformat() if w.last_heartbeat else None,
            "current_job_id":str(w.current_job_id) if w.current_job_id else None,
            "lease_until":w.lease_until.isoformat() if w.lease_until else None}
