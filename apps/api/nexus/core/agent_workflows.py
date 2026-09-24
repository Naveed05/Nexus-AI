from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json, sqlite3
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import UUID, uuid4


class AgentWorkflowStatus(str, Enum):
    DRAFT="draft"
    READY="ready"
    RUNNING="running"
    PAUSED="paused"
    COMPLETED="completed"
    FAILED="failed"
    CANCELLED="cancelled"


class WorkItemStatus(str, Enum):
    PENDING="pending"
    RUNNING="running"
    COMPLETED="completed"
    FAILED="failed"
    BLOCKED="blocked"
    SKIPPED="skipped"


@dataclass
class AgentWorkItem:
    item_id: UUID
    objective: str
    agent_id: str
    depends_on: list[UUID]=field(default_factory=list)
    status: WorkItemStatus=WorkItemStatus.PENDING
    input_refs: list[str]=field(default_factory=list)
    output_refs: list[str]=field(default_factory=list)
    provenance: dict[str,Any]=field(default_factory=dict)
    attempts: int=0
    error: str|None=None


@dataclass
class AgentWorkflow:
    workflow_id: UUID
    objective: str
    owner_id: str
    items: list[AgentWorkItem]
    max_parallel: int=2
    status: AgentWorkflowStatus=AgentWorkflowStatus.DRAFT
    created_at: datetime=field(default_factory=lambda:datetime.now(timezone.utc))
    updated_at: datetime=field(default_factory=lambda:datetime.now(timezone.utc))
    version: int=0


class AgentWorkflowValidationError(ValueError):
    pass


class AgentWorkflowStore:
    def __init__(self,path=".nexus/agent_workflows.sqlite3"):
        self.path=path
        self._lock=RLock()
        if path!=":memory:":
            Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self._connect() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS agent_workflows(
                workflow_id TEXT PRIMARY KEY,objective TEXT NOT NULL,owner_id TEXT NOT NULL,
                items TEXT NOT NULL,max_parallel INTEGER NOT NULL,status TEXT NOT NULL,
                created_at TEXT NOT NULL,updated_at TEXT NOT NULL,version INTEGER NOT NULL)""")
            c.execute("""CREATE TABLE IF NOT EXISTS agent_workflow_events(
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,workflow_id TEXT NOT NULL,event_type TEXT NOT NULL,
                item_id TEXT,detail TEXT NOT NULL,created_at TEXT NOT NULL)""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_agent_wf_events ON agent_workflow_events(workflow_id,sequence)")
            c.commit()

    def _connect(self):
        c=sqlite3.connect(self.path,timeout=10)
        c.row_factory=sqlite3.Row
        return c

    def save(self,w,event_type="workflow.updated",detail="",item_id=None):
        with self._lock,self._connect() as c:
            w.updated_at=datetime.now(timezone.utc); w.version+=1
            payload=[]
            for i in w.items:
                payload.append({"item_id":str(i.item_id),"objective":i.objective,"agent_id":i.agent_id,
                    "depends_on":[str(x) for x in i.depends_on],"status":i.status.value,
                    "input_refs":i.input_refs,"output_refs":i.output_refs,"provenance":i.provenance,
                    "attempts":i.attempts,"error":i.error})
            c.execute("INSERT OR REPLACE INTO agent_workflows VALUES(?,?,?,?,?,?,?,?,?)",
                (str(w.workflow_id),w.objective,w.owner_id,json.dumps(payload),w.max_parallel,w.status.value,
                 w.created_at.isoformat(),w.updated_at.isoformat(),w.version))
            c.execute("INSERT INTO agent_workflow_events(workflow_id,event_type,item_id,detail,created_at) VALUES(?,?,?,?,?)",
                (str(w.workflow_id),event_type,str(item_id) if item_id else None,detail,datetime.now(timezone.utc).isoformat()))
            c.commit()
        return w

    def get(self,wid):
        with self._lock,self._connect() as c:
            r=c.execute("SELECT * FROM agent_workflows WHERE workflow_id=?",(str(wid),)).fetchone()
        return self._row(r) if r else None

    def list(self,limit=100):
        with self._lock,self._connect() as c:
            rows=c.execute("SELECT * FROM agent_workflows ORDER BY updated_at DESC LIMIT ?",(max(1,min(500,limit)),)).fetchall()
        return [self._row(r) for r in rows]

    def events(self,wid,limit=100):
        with self._lock,self._connect() as c:
            return [dict(r) for r in c.execute("SELECT * FROM agent_workflow_events WHERE workflow_id=? ORDER BY sequence DESC LIMIT ?",
                (str(wid),max(1,min(200,limit)))).fetchall()]

    @staticmethod
    def _row(r):
        raw=json.loads(r["items"])
        return AgentWorkflow(UUID(r["workflow_id"]),r["objective"],r["owner_id"],
            [AgentWorkItem(UUID(x["item_id"]),x["objective"],x["agent_id"],[UUID(v) for v in x.get("depends_on",[])],
                WorkItemStatus(x.get("status","pending")),x.get("input_refs",[]),x.get("output_refs",[]),
                x.get("provenance",{}),int(x.get("attempts",0)),x.get("error"))
             for x in raw],int(r["max_parallel"]),AgentWorkflowStatus(r["status"]),
            datetime.fromisoformat(r["created_at"]),datetime.fromisoformat(r["updated_at"]),int(r["version"]))


def validate_agent_workflow(items:list[AgentWorkItem],max_parallel:int=2):
    if not items:
        raise AgentWorkflowValidationError("at least one work item is required")
    if not 1 <= max_parallel <= 16:
        raise AgentWorkflowValidationError("max_parallel must be between 1 and 16")
    ids=[x.item_id for x in items]
    if len(ids)!=len(set(ids)):
        raise AgentWorkflowValidationError("duplicate work item id")
    known=set(ids)
    graph={x.item_id:x.depends_on for x in items}
    for item in items:
        missing=set(item.depends_on)-known
        if missing: raise AgentWorkflowValidationError(f"{item.objective}: unknown dependency")
        if item.item_id in item.depends_on: raise AgentWorkflowValidationError("work item cannot depend on itself")
    visiting=set(); visited=set()
    def visit(n):
        if n in visiting: raise AgentWorkflowValidationError("agent workflow contains a dependency cycle")
        if n in visited:return
        visiting.add(n)
        for d in graph[n]:visit(d)
        visiting.remove(n);visited.add(n)
    for n in ids:visit(n)
    return True


def agent_workflow_payload(w:AgentWorkflow):
    return {"workflow_id":str(w.workflow_id),"objective":w.objective,"owner_id":w.owner_id,"status":w.status.value,
        "max_parallel":w.max_parallel,"version":w.version,"created_at":w.created_at.isoformat(),"updated_at":w.updated_at.isoformat(),
        "items":[{"item_id":str(i.item_id),"objective":i.objective,"agent_id":i.agent_id,
            "depends_on":[str(x) for x in i.depends_on],"status":i.status.value,"input_refs":i.input_refs,
            "output_refs":i.output_refs,"provenance":i.provenance,"attempts":i.attempts,"error":i.error} for i in w.items]}


class AgentWorkflowOrchestrationError(ValueError): pass


class AgentWorkflowOrchestrator:
    """Durable, bounded multi-agent DAG orchestration. It schedules declared work only."""
    def __init__(self,store:AgentWorkflowStore,max_parallel=4):
        self.store=store
        self.max_parallel=max(1,min(16,max_parallel))

    def create(self,objective,items,owner_id="local-user",max_parallel=2):
        validate_agent_workflow(items,max_parallel)
        w=AgentWorkflow(uuid4(),objective.strip(),owner_id.strip() or "local-user",items,max_parallel,AgentWorkflowStatus.READY)
        self.store.save(w,"workflow.created","agent workflow created")
        return w

    def ready(self,w):
        by_id={i.item_id:i for i in w.items}
        return [i for i in w.items if i.status==WorkItemStatus.PENDING and
                all(by_id[d].status==WorkItemStatus.COMPLETED for d in i.depends_on)]

    def health(self,w):
        blocked=[str(i.item_id) for i in w.items if i.status==WorkItemStatus.PENDING and any(
            next((d for d in w.items if d.item_id==dep),i).status in {WorkItemStatus.FAILED,WorkItemStatus.BLOCKED,WorkItemStatus.SKIPPED} for dep in i.depends_on)]
        running=[str(i.item_id) for i in w.items if i.status==WorkItemStatus.RUNNING]
        failed=[str(i.item_id) for i in w.items if i.status==WorkItemStatus.FAILED]
        ready=[str(i.item_id) for i in self.ready(w)]
        return {"workflow_id":str(w.workflow_id),"status":w.status.value,"ready_items":ready,
                "running_items":running,"blocked_items":blocked,"failed_items":failed,
                "active_count":len(running),"ready_count":len(ready),"needs_operator":bool(failed) or w.status in {AgentWorkflowStatus.PAUSED,AgentWorkflowStatus.FAILED}}

    def dispatch(self,wid):
        w=self.store.get(wid)
        if not w: raise KeyError("unknown agent workflow")
        if w.status in {AgentWorkflowStatus.PAUSED,AgentWorkflowStatus.CANCELLED,AgentWorkflowStatus.COMPLETED,AgentWorkflowStatus.FAILED}:
            raise AgentWorkflowOrchestrationError(f"cannot dispatch from {w.status.value}")
        if w.status==AgentWorkflowStatus.DRAFT:w.status=AgentWorkflowStatus.READY
        active=sum(i.status==WorkItemStatus.RUNNING for i in w.items)
        slots=max(0,w.max_parallel-active)
        selected=self.ready(w)[:slots]
        for item in selected:
            item.status=WorkItemStatus.RUNNING
            item.attempts+=1
            item.provenance={**item.provenance,"assigned_at":datetime.now(timezone.utc).isoformat(),
                             "workflow_version":w.version+1,"agent_id":item.agent_id}
        if selected:
            w.status=AgentWorkflowStatus.RUNNING
            self.store.save(w,"workstream.dispatched",f"dispatched {len(selected)} bounded workstream(s)")
        return selected

    def complete(self,wid,item_id,output_refs=(),provenance=None):
        w=self.store.get(wid)
        if not w: raise KeyError("unknown agent workflow")
        item=next((i for i in w.items if i.item_id==item_id),None)
        if not item: raise KeyError("unknown work item")
        if item.status!=WorkItemStatus.RUNNING: raise AgentWorkflowOrchestrationError("only running work items can complete")
        item.status=WorkItemStatus.COMPLETED; item.output_refs=list(output_refs)
        item.provenance={**item.provenance,**(provenance or {}),"completed_at":datetime.now(timezone.utc).isoformat()}
        if all(i.status in {WorkItemStatus.COMPLETED,WorkItemStatus.SKIPPED} for i in w.items):w.status=AgentWorkflowStatus.COMPLETED
        self.store.save(w,"workstream.completed","workstream completed",item_id)
        return w

    def fail(self,wid,item_id,error):
        w=self.store.get(wid)
        if not w: raise KeyError("unknown agent workflow")
        item=next((i for i in w.items if i.item_id==item_id),None)
        if not item: raise KeyError("unknown work item")
        if item.status!=WorkItemStatus.RUNNING: raise AgentWorkflowOrchestrationError("only running work items can fail")
        item.status=WorkItemStatus.FAILED; item.error=str(error)[:2000]; w.status=AgentWorkflowStatus.FAILED
        self.store.save(w,"workstream.failed","workstream failed",item_id)
        return w

    def retry(self,wid,item_id):
        w=self.store.get(wid)
        if not w: raise KeyError("unknown agent workflow")
        item=next((i for i in w.items if i.item_id==item_id),None)
        if not item or item.status!=WorkItemStatus.FAILED: raise AgentWorkflowOrchestrationError("only failed work items can retry")
        item.status=WorkItemStatus.PENDING; item.error=None; w.status=AgentWorkflowStatus.READY
        self.store.save(w,"workstream.retry","failed workstream queued for retry",item_id)
        return w

    def pause(self,wid):
        w=self.store.get(wid)
        if not w: raise KeyError("unknown agent workflow")
        if w.status in {AgentWorkflowStatus.COMPLETED,AgentWorkflowStatus.CANCELLED}: raise AgentWorkflowOrchestrationError("workflow is terminal")
        w.status=AgentWorkflowStatus.PAUSED; self.store.save(w,"workflow.paused","agent workflow paused"); return w

    def resume(self,wid):
        w=self.store.get(wid)
        if not w: raise KeyError("unknown agent workflow")
        if w.status!=AgentWorkflowStatus.PAUSED: raise AgentWorkflowOrchestrationError("workflow is not paused")
        w.status=AgentWorkflowStatus.READY; self.store.save(w,"workflow.resumed","agent workflow resumed"); return w

    def cancel(self,wid):
        w=self.store.get(wid)
        if not w: raise KeyError("unknown agent workflow")
        if w.status in {AgentWorkflowStatus.COMPLETED,AgentWorkflowStatus.CANCELLED}: raise AgentWorkflowOrchestrationError("workflow is terminal")
        for i in w.items:
            if i.status in {WorkItemStatus.PENDING,WorkItemStatus.RUNNING}:i.status=WorkItemStatus.SKIPPED;i.error="Cancelled by operator"
        w.status=AgentWorkflowStatus.CANCELLED; self.store.save(w,"workflow.cancelled","agent workflow cancelled"); return w

    def recover_blocked(self,wid):
        w=self.store.get(wid)
        if not w: raise KeyError("unknown agent workflow")
        by_id={i.item_id:i for i in w.items}; recovered=[]
        for item in w.items:
            if item.status==WorkItemStatus.BLOCKED:
                deps=[by_id[d] for d in item.depends_on]
                if all(d.status==WorkItemStatus.COMPLETED for d in deps):
                    item.status=WorkItemStatus.PENDING; item.error=None; recovered.append(item.item_id)
        if recovered:
            w.status=AgentWorkflowStatus.READY; self.store.save(w,"workflow.recovered",f"recovered {len(recovered)} blocked workstream(s)")
        return w

    def metrics(self,workflows):
        statuses={x.value:0 for x in AgentWorkflowStatus}
        items={x.value:0 for x in WorkItemStatus}
        for w in workflows:
            statuses[w.status.value]=statuses.get(w.status.value,0)+1
            for i in w.items:items[i.status.value]=items.get(i.status.value,0)+1
        total=len(workflows); terminal=statuses["completed"]+statuses["failed"]+statuses["cancelled"]
        return {"workflow_count":total,"status_counts":statuses,"item_status_counts":items,
                "active_workflow_count":max(0,total-terminal),"terminal_workflow_count":terminal,
                "completion_rate":statuses["completed"]/terminal if terminal else 0.0,
                "failure_rate":statuses["failed"]/terminal if terminal else 0.0}
