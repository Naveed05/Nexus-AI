from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json, sqlite3
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import UUID, uuid4


class WorkflowStepStatus(str, Enum):
    PENDING="pending"
    RUNNING="running"
    COMPLETED="completed"
    FAILED="failed"
    SKIPPED="skipped"


@dataclass
class WorkflowStep:
    step_id: str
    objective: str
    depends_on: list[str]=field(default_factory=list)
    condition: str|None=None
    risk_level: str="low"
    status: WorkflowStepStatus=WorkflowStepStatus.PENDING
    job_id: UUID|None=None
    result: dict[str,Any]=field(default_factory=dict)
    error: str|None=None


@dataclass(frozen=True)
class WorkflowEvent:
    sequence: int
    event_id: UUID
    workflow_id: UUID
    event_type: str
    status: str
    step_id: str|None
    detail: str
    created_at: datetime


@dataclass
class Workflow:
    workflow_id: UUID
    name: str
    objective: str
    owner_id: str="local-user"
    workspace_id: UUID|None=None
    status: str="draft"
    steps: list[WorkflowStep]=field(default_factory=list)
    created_at: datetime=field(default_factory=lambda:datetime.now(timezone.utc))
    updated_at: datetime=field(default_factory=lambda:datetime.now(timezone.utc))
    schedule: dict[str,Any]|None=None
    version: int=0
    event_count: int=0
    last_event_sequence: int=0
    last_event_at: str|None=None


class WorkflowStore:
    def __init__(self,path=".nexus/workflows.sqlite3"):
        self.path=path
        self._lock=RLock()
        if path!=":memory:":
            Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self._connect() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS workflows(
                workflow_id TEXT PRIMARY KEY,name TEXT NOT NULL,objective TEXT NOT NULL,owner_id TEXT NOT NULL,
                workspace_id TEXT,status TEXT NOT NULL,steps TEXT NOT NULL,created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,schedule TEXT,version INTEGER NOT NULL)""")
            c.execute("""CREATE TABLE IF NOT EXISTS workflow_events(
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,workflow_id TEXT NOT NULL,event_type TEXT NOT NULL,
                status TEXT NOT NULL,step_id TEXT,detail TEXT NOT NULL,created_at TEXT NOT NULL)""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_workflow_events_workflow ON workflow_events(workflow_id,sequence)")
            c.commit()

    def _connect(self):
        c=sqlite3.connect(self.path,timeout=10)
        c.row_factory=sqlite3.Row
        return c

    def _record_event(self,c,w,event_type,detail,step_id=None):
        c.execute(
            "INSERT INTO workflow_events(event_id,workflow_id,event_type,status,step_id,detail,created_at) VALUES(?,?,?,?,?,?,?)",
            (str(uuid4()),str(w.workflow_id),event_type,w.status,step_id,detail,datetime.now(timezone.utc).isoformat())
        )

    def save(self,w,event_type="workflow.updated",detail=None,step_id=None):
        with self._lock,self._connect() as c:
            w.updated_at=datetime.now(timezone.utc)
            w.version+=1
            steps=[{"step_id":s.step_id,"objective":s.objective,"depends_on":s.depends_on,"condition":s.condition,
                    "risk_level":s.risk_level,"status":s.status.value,"job_id":str(s.job_id) if s.job_id else None,
                    "result":s.result,"error":s.error} for s in w.steps]
            c.execute("INSERT OR REPLACE INTO workflows VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (str(w.workflow_id),w.name,w.objective,w.owner_id,str(w.workspace_id) if w.workspace_id else None,w.status,
                 json.dumps(steps),w.created_at.isoformat(),w.updated_at.isoformat(),json.dumps(w.schedule) if w.schedule else None,w.version))
            self._record_event(c,w,event_type,detail or event_type,step_id)
            row=c.execute("SELECT COUNT(*) AS count, MAX(sequence) AS sequence, MAX(created_at) AS created_at FROM workflow_events WHERE workflow_id=?",(str(w.workflow_id),)).fetchone()
            w.event_count=int(row["count"] or 0); w.last_event_sequence=int(row["sequence"] or 0); w.last_event_at=row["created_at"]
            c.commit()
        return w

    def get(self,wid):
        with self._lock,self._connect() as c:
            r=c.execute("SELECT * FROM workflows WHERE workflow_id=?",(str(wid),)).fetchone()
        if not r:
            return None
        w=self._row(r)
        summary=self.event_summary(w.workflow_id)
        w.event_count=summary["count"]; w.last_event_sequence=summary["last_sequence"]; w.last_event_at=summary["last_event_at"]
        return w

    def list(self,limit=100):
        with self._lock,self._connect() as c:
            rows=c.execute("SELECT * FROM workflows ORDER BY updated_at DESC LIMIT ?",(max(1,min(500,limit)),)).fetchall()
        result=[]
        for r in rows:
            w=self._row(r); summary=self.event_summary(w.workflow_id)
            w.event_count=summary["count"]; w.last_event_sequence=summary["last_sequence"]; w.last_event_at=summary["last_event_at"]
            result.append(w)
        return result

    def events(self,wid,limit=50):
        with self._lock,self._connect() as c:
            rows=c.execute("SELECT * FROM workflow_events WHERE workflow_id=? ORDER BY sequence DESC LIMIT ?",
                           (str(wid),max(1,min(200,limit)))).fetchall()
        return [WorkflowEvent(int(r["sequence"]),UUID(r["event_id"]),UUID(r["workflow_id"]),r["event_type"],
                              r["status"],r["step_id"],r["detail"],datetime.fromisoformat(r["created_at"])) for r in rows]

    def event_summary(self,wid):
        with self._lock,self._connect() as c:
            r=c.execute("SELECT COUNT(*) AS count, MAX(sequence) AS sequence, MAX(created_at) AS created_at "
                        "FROM workflow_events WHERE workflow_id=?",(str(wid),)).fetchone()
        return {"count":int(r["count"] or 0),"last_sequence":int(r["sequence"] or 0),
                "last_event_at":r["created_at"]}

    @staticmethod
    def _row(r):
        return Workflow(UUID(r["workflow_id"]),r["name"],r["objective"],r["owner_id"],
            UUID(r["workspace_id"]) if r["workspace_id"] else None,r["status"],
            [WorkflowStep(x["step_id"],x["objective"],x.get("depends_on",[]),x.get("condition"),
                x.get("risk_level","low"),WorkflowStepStatus(x.get("status","pending")),
                UUID(x["job_id"]) if x.get("job_id") else None,x.get("result",{}),x.get("error"))
             for x in json.loads(r["steps"])],
            datetime.fromisoformat(r["created_at"]),datetime.fromisoformat(r["updated_at"]),
            json.loads(r["schedule"]) if r["schedule"] else None,r["version"])


class WorkflowValidationError(ValueError):
    pass


def validate_workflow(steps:list[WorkflowStep]):
    ids=[s.step_id for s in steps]
    if len(ids)!=len(set(ids)):
        raise WorkflowValidationError("step_id values must be unique")
    known=set(ids)
    for s in steps:
        missing=set(s.depends_on)-known
        if missing:
            raise WorkflowValidationError(f"{s.step_id} depends on unknown steps: {sorted(missing)}")
    visiting=set()
    visited=set()
    graph={s.step_id:s.depends_on for s in steps}
    def visit(n):
        if n in visiting:
            raise WorkflowValidationError("workflow contains a dependency cycle")
        if n in visited:
            return
        visiting.add(n)
        for d in graph[n]:
            visit(d)
        visiting.remove(n)
        visited.add(n)
    for n in ids:
        visit(n)
    return True


def evaluate_condition(condition:str|None, context:dict[str,Any]|None=None)->bool:
    """Evaluate a deliberately small, deterministic workflow condition language.

    Supported forms are: omitted/blank (true), "true", "false", and
    dotted key equality such as "verification.passed == true" or
    "run.status == 'completed'". No Python expressions are evaluated.
    """
    if condition is None or not condition.strip():
        return True
    raw=condition.strip()
    if raw.lower() in {"true","always"}:
        return True
    if raw.lower() in {"false","never"}:
        return False
    if "==" not in raw:
        return False
    key,expected=[x.strip() for x in raw.split("==",1)]
    if not key or not expected or not key.replace("_","").replace(".","").isalnum():
        return False
    value:Any=context or {}
    for part in key.split("."):
        if not isinstance(value,dict) or part not in value:
            return False
        value=value[part]
    if expected.lower() in {"true","false"}:
        wanted=expected.lower()=="true"
    elif (len(expected)>=2 and expected[0]==expected[-1] and expected[0] in {"'","\""}):
        wanted=expected[1:-1]
    else:
        try:
            wanted=float(expected) if "." in expected else int(expected)
        except ValueError:
            wanted=expected
    return value==wanted


def ready_steps(w:Workflow):
    by_id={s.step_id:s for s in w.steps}
    ready=[]
    for s in w.steps:
        if s.status!=WorkflowStepStatus.PENDING:
            continue
        deps=[by_id[d] for d in s.depends_on]
        if any(d.status in {WorkflowStepStatus.FAILED,WorkflowStepStatus.SKIPPED} for d in deps):
            continue
        if all(d.status==WorkflowStepStatus.COMPLETED for d in deps):
            ready.append(s)
    return ready


def workflow_payload(w:Workflow,store:WorkflowStore|None=None):
    summary={"count":w.event_count,"last_sequence":w.last_event_sequence,"last_event_at":w.last_event_at}
    if store and summary["count"]==0:
        summary=store.event_summary(w.workflow_id)
    next_run_at=(w.schedule or {}).get("run_at")
    return {"workflow_id":str(w.workflow_id),"name":w.name,"objective":w.objective,"owner_id":w.owner_id,
      "workspace_id":str(w.workspace_id) if w.workspace_id else None,"status":w.status,
      "created_at":w.created_at.isoformat(),"updated_at":w.updated_at.isoformat(),"version":w.version,
      "schedule":w.schedule,"next_run_at":next_run_at,
      "event_count":summary["count"],"last_event_sequence":summary["last_sequence"],"last_event_at":summary["last_event_at"],
      "steps":[{"step_id":s.step_id,"objective":s.objective,"depends_on":s.depends_on,"condition":s.condition,
      "risk_level":s.risk_level,"status":s.status.value,"job_id":str(s.job_id) if s.job_id else None,"result":s.result,"error":s.error} for s in w.steps]}


WORKFLOW_TEMPLATES={
 "research-report":{"name":"Research → Verify → Report","description":"Research a question, verify the evidence, then produce a report.","steps":[
   {"step_id":"research","objective":"Research the requested topic and gather evidence","capabilities":["research"]},
   {"step_id":"verify","objective":"Verify the research evidence and identify gaps","depends_on":["research"],"capabilities":["verification"]},
   {"step_id":"report","objective":"Write a concise final report from the verified evidence","depends_on":["verify"],"capabilities":["writing"]}]},
 "code-quality":{"name":"Code → Test → Verify","description":"Implement work, test it, then verify the result.","steps":[
   {"step_id":"implement","objective":"Implement the requested code change","capabilities":["coding"]},
   {"step_id":"test","objective":"Run tests and diagnose failures","depends_on":["implement"],"capabilities":["coding"]},
   {"step_id":"verify","objective":"Review the implementation and test evidence","depends_on":["test"],"capabilities":["verification"]}]},
 "analysis-brief":{"name":"Analyze → Validate → Brief","description":"Analyze information, validate assumptions, and deliver a brief.","steps":[
   {"step_id":"analyze","objective":"Analyze the supplied objective and available context","capabilities":["analysis"]},
   {"step_id":"validate","objective":"Validate key findings and assumptions","depends_on":["analyze"],"capabilities":["verification"]},
   {"step_id":"brief","objective":"Produce the final decision-support brief","depends_on":["validate"],"capabilities":["writing"]}]}
}


class WorkflowScheduler:
    def __init__(self, store, tick=1.0):
        from threading import Event
        self.store=store
        self.tick=max(0.2,tick)
        self._stop=Event()
        self._thread=None

    def start(self):
        from threading import Thread
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread=Thread(target=self._loop,name="nexus-workflow-scheduler",daemon=True)
        self._thread.start()

    def stop(self):
        if self._thread:
            self._stop.set()
            self._thread.join(timeout=2)

    def _loop(self):
        import time
        while not self._stop.is_set():
            now=datetime.now(timezone.utc)
            for w in self.store.list(500):
                s=w.schedule or {}
                if w.status=="paused" or not s or s.get("enabled") is False or w.status not in {"scheduled","completed","failed"}:
                    continue
                raw=s.get("run_at")
                if not raw:
                    continue
                try:
                    due=datetime.fromisoformat(raw.replace("Z","+00:00"))
                except ValueError:
                    continue
                if due>now:
                    continue
                for step in w.steps:
                    step.status=WorkflowStepStatus.PENDING
                    step.job_id=None
                    step.result={}
                    step.error=None
                w.status="running"
                interval=s.get("interval_seconds")
                if interval:
                    s["run_at"]=(now+__import__("datetime").timedelta(seconds=max(1,int(interval)))).isoformat()
                    s["enabled"]=True
                else:
                    s["enabled"]=False
                self.store.save(w,event_type="workflow.scheduled",detail="schedule became due")
            self._stop.wait(self.tick)