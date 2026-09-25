"""NEXUS Platform 2.0 foundations: phases 65–80.

The module deliberately keeps external infrastructure behind small contracts so
local SQLite/filesystem operation remains deterministic while production
deployments can substitute PostgreSQL, queues, caches, object stores, identity
providers, secret managers, and connectors.
"""
from __future__ import annotations
import hashlib, hmac, json, os, secrets, sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, Mapping
from uuid import UUID, uuid4

def now() -> str: return datetime.now(timezone.utc).isoformat()

class SQLiteStore:
    def __init__(self,path:str|Path):
        self.path=str(path); Path(self.path).parent.mkdir(parents=True,exist_ok=True); self.lock=RLock()
    def connect(self):
        return sqlite3.connect(self.path,check_same_thread=False)

@dataclass(frozen=True)
class ResourceLink:
    resource_id: str
    workspace_id: str
    resource_type: str
    owner_id: str|None=None
    parent_id: str|None=None
    created_at: str= ""
    metadata: dict[str,Any]|None=None

class ResourceGraphStore(SQLiteStore):
    """Phase 65: one durable relationship graph for all NEXUS resources."""
    def __init__(self,path):
        super().__init__(path)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS resource_links(
              resource_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,resource_type TEXT NOT NULL,
              owner_id TEXT,parent_id TEXT,created_at TEXT NOT NULL,metadata TEXT NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_resource_workspace ON resource_links(workspace_id,resource_type)")
            db.commit()
    def upsert(self,link:ResourceLink)->ResourceLink:
        link=ResourceLink(link.resource_id,link.workspace_id,link.resource_type,link.owner_id,link.parent_id,link.created_at or now(),dict(link.metadata or {}))
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO resource_links VALUES(?,?,?,?,?,?,?)",
                (link.resource_id,link.workspace_id,link.resource_type,link.owner_id,link.parent_id,link.created_at,json.dumps(link.metadata,sort_keys=True,default=str))); db.commit()
        return link
    def list(self,workspace_id:str,resource_type:str|None=None)->list[ResourceLink]:
        q="SELECT * FROM resource_links WHERE workspace_id=?"; p=[workspace_id]
        if resource_type: q+=" AND resource_type=?"; p.append(resource_type)
        q+=" ORDER BY created_at"
        with self.connect() as db: rows=db.execute(q,p).fetchall()
        return [ResourceLink(r[0],r[1],r[2],r[3],r[4],r[5],json.loads(r[6] or "{}")) for r in rows]
    def summary(self,workspace_id:str)->dict[str,int]:
        out={}
        for x in self.list(workspace_id): out[x.resource_type]=out.get(x.resource_type,0)+1
        return out

class ExecutionTrace:
    """Phase 66: normalized trace query over the durable execution event spine."""
    def __init__(self,event_store): self.events=event_store
    def timeline(self,task_id:UUID|None=None,limit:int=500)->dict[str,Any]:
        rows=self.events.list(task_id=task_id,limit=limit)
        return {"task_id":str(task_id) if task_id else None,"events":[r.as_dict() for r in rows],"count":len(rows),
                "complete": bool(rows and rows[-1].event_type in {"task_completed","task_failed"})}
    def event_types(self,limit:int=5000)->dict[str,int]:
        return self.events.summary().get("event_types",{})

@dataclass(frozen=True)
class Principal:
    principal_id:str
    tenant_id:str
    name:str
    roles:tuple[str,...]=("member",)
    active:bool=True
    created_at:str=""
class IdentityStore(SQLiteStore):
    """Phase 67: durable tenant/user/service identity foundation."""
    def __init__(self,path):
        super().__init__(path)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS principals(
             principal_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,name TEXT NOT NULL,
             roles TEXT NOT NULL,active INTEGER NOT NULL,created_at TEXT NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_principal_tenant ON principals(tenant_id)")
            db.commit()
    def create(self,tenant_id:str,name:str,roles:Iterable[str]=("member",),principal_id:str|None=None)->Principal:
        p=Principal(principal_id or str(uuid4()),tenant_id,name,tuple(roles),True,now())
        with self.connect() as db:
            db.execute("INSERT INTO principals VALUES(?,?,?,?,?,?)",(p.principal_id,p.tenant_id,p.name,json.dumps(p.roles),1,p.created_at)); db.commit()
        return p
    def get(self,principal_id:str)->Principal|None:
        with self.connect() as db: r=db.execute("SELECT * FROM principals WHERE principal_id=?",(principal_id,)).fetchone()
        return Principal(r[0],r[1],r[2],tuple(json.loads(r[3])),bool(r[4]),r[5]) if r else None
    def list_tenant(self,tenant_id:str)->list[Principal]:
        with self.connect() as db: rows=db.execute("SELECT * FROM principals WHERE tenant_id=? ORDER BY created_at",(tenant_id,)).fetchall()
        return [Principal(r[0],r[1],r[2],tuple(json.loads(r[3])),bool(r[4]),r[5]) for r in rows]

class SecretVault(SQLiteStore):
    """Phase 68: encrypted-at-rest secret envelope using Fernet."""
    def __init__(self,path,key:bytes|None=None):
        super().__init__(path)
        try:
            from cryptography.fernet import Fernet
        except ImportError as exc: raise RuntimeError("cryptography package is required for SecretVault") from exc
        self._fernet=Fernet(key or Fernet.generate_key())
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS secrets(
             secret_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,name TEXT NOT NULL,
             ciphertext BLOB NOT NULL,version INTEGER NOT NULL,created_at TEXT NOT NULL)"""); db.commit()
    def put(self,tenant_id:str,name:str,value:str,secret_id:str|None=None)->str:
        sid=secret_id or str(uuid4()); blob=self._fernet.encrypt(value.encode())
        with self.connect() as db:
            old=db.execute("SELECT COALESCE(MAX(version),0) FROM secrets WHERE tenant_id=? AND name=?",(tenant_id,name)).fetchone()[0]
            db.execute("INSERT INTO secrets VALUES(?,?,?,?,?,?)",(sid,tenant_id,name,blob,int(old)+1,now())); db.commit()
        return sid
    def get(self,secret_id:str)->str:
        with self.connect() as db: r=db.execute("SELECT ciphertext FROM secrets WHERE secret_id=?",(secret_id,)).fetchone()
        if not r: raise KeyError(secret_id)
        return self._fernet.decrypt(r[0]).decode()

@dataclass(frozen=True)
class InfrastructurePlan:
    state_backend:str; queue_backend:str; cache_backend:str; object_storage_backend:str
    distributed:bool; blockers:tuple[str,...]
    def as_dict(self): return asdict(self)
def infrastructure_plan(settings)->InfrastructurePlan:
    fields={"state_backend":settings.state_backend,"queue_backend":settings.queue_backend,"cache_backend":settings.cache_backend,"object_storage_backend":settings.object_storage_backend}
    blockers=[]
    if settings.deployment_mode=="distributed":
        for key,val in fields.items():
            if val in {"sqlite","memory","filesystem"}: blockers.append(f"{key}:{val} is not shared")
    return InfrastructurePlan(**fields,distributed=settings.deployment_mode=="distributed",blockers=tuple(blockers))

@dataclass(frozen=True)
class AgentPlan:
    specialist:str; model_requirements:dict[str,Any]; tools:tuple[str,...]; rationale:str
class AdaptivePlanner:
    """Phase 70: deterministic adaptive specialist/tool plan selection."""
    def plan(self,objective:str,capabilities:Iterable[str]=(),risk_level:str="low")->AgentPlan:
        text=objective.lower(); caps=set(capabilities)
        specialist="general"
        if any(k in text for k in ("csv","dataset","sql","data","forecast","model")): specialist="data-scientist"
        elif any(k in text for k in ("code","bug","repository","github","python")): specialist="developer"
        elif any(k in text for k in ("research","paper","source","citation")): specialist="researcher"
        elif any(k in text for k in ("pdf","document","contract")): specialist="document-analyst"
        tools=tuple(sorted(caps))
        return AgentPlan(specialist,{"risk_level":risk_level,"requires_verification":True},tools,f"matched objective signals to {specialist}")

@dataclass(frozen=True)
class Specialist:
    specialist_id:str; name:str; capabilities:tuple[str,...]; risk_level:str="low"
class SpecialistRegistry:
    """Phase 71: versionable specialist catalog."""
    def __init__(self): self._items:dict[str,Specialist]={}
    def register(self,item:Specialist): self._items[item.specialist_id]=item; return item
    def list(self): return tuple(self._items.values())
    def match(self,capabilities:Iterable[str])->list[Specialist]:
        required=set(capabilities); return [x for x in self._items.values() if required.issubset(x.capabilities)]

@dataclass(frozen=True)
class Connector:
    connector_id:str; name:str; capabilities:tuple[str,...]; auth_mode:str
class ConnectorRegistry:
    """Phase 72: safe connector contracts; transport is intentionally injected."""
    def __init__(self): self._items={}
    def register(self,c:Connector): self._items[c.connector_id]=c; return c
    def list(self): return tuple(self._items.values())
    def get(self,cid): return self._items[cid]

class AnalyticsEngine:
    """Phase 73: operational analytics derived from durable execution events."""
    def __init__(self,event_store): self.events=event_store
    def execution(self,limit=5000)->dict[str,Any]:
        summary=self.events.summary(); types=summary["event_types"]
        return {"event_count":summary["event_count"],"event_types":types,
                "tasks_started":types.get("task_started",0),"tasks_completed":types.get("task_completed",0),
                "tasks_failed":types.get("task_failed",0),"tool_calls":types.get("tool_called",0),
                "verification_failures":types.get("step_failed",0)}

class ContinuousEvaluationGate:
    """Phase 74: release gate combining quality and regression decisions."""
    def __init__(self,evaluation_control): self.control=evaluation_control
    def evaluate(self,run_id:str,baseline_run_id:str|None=None)->dict[str,Any]:
        return self.control.gate(run_id,baseline_run_id=baseline_run_id).as_dict()

class CostLedger(SQLiteStore):
    """Phase 75: durable usage/cost accounting with budgets."""
    def __init__(self,path):
        super().__init__(path)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS cost_entries(
             entry_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,run_id TEXT,units REAL NOT NULL,cost REAL NOT NULL,
             category TEXT NOT NULL,created_at TEXT NOT NULL)""")
            db.commit()
    def record(self,tenant_id:str,units:float,cost:float,category:str,run_id:str|None=None)->str:
        eid=str(uuid4())
        with self.connect() as db: db.execute("INSERT INTO cost_entries VALUES(?,?,?,?,?,?,?)",(eid,tenant_id,run_id,units,cost,category,now())); db.commit()
        return eid
    def usage(self,tenant_id:str)->dict[str,float]:
        with self.connect() as db: r=db.execute("SELECT COALESCE(SUM(units),0),COALESCE(SUM(cost),0) FROM cost_entries WHERE tenant_id=?",(tenant_id,)).fetchone()
        return {"units":float(r[0]),"cost":float(r[1])}

class SecurityPolicyEngine:
    """Phase 76: explicit data/security policy checks."""
    def check(self,action:str,*,risk_level:str="low",roles:Iterable[str]=())->dict[str,Any]:
        roles=set(roles); privileged=risk_level in {"high","critical"}
        allowed=not privileged or bool({"admin","operator"} & roles)
        return {"allowed":allowed,"action":action,"risk_level":risk_level,"required_roles":["operator"] if privileged else []}

@dataclass(frozen=True)
class MultimodalAsset:
    asset_id:str; workspace_id:str|None; modality:str; sha256:str; size_bytes:int; mime_type:str|None; created_at:str
class MultimodalRegistry:
    """Phase 77: content-addressed multimodal asset descriptors."""
    def register(self,data:bytes,modality:str,workspace_id:str|None=None,mime_type:str|None=None)->MultimodalAsset:
        return MultimodalAsset(str(uuid4()),workspace_id,modality,hashlib.sha256(data).hexdigest(),len(data),mime_type,now())

class DeveloperWorkflow:
    """Phase 78: bounded developer-workflow contract around the existing tool system."""
    def inspect(self,objective:str,files:Iterable[str]=())->dict[str,Any]:
        paths=tuple(sorted(set(files)))
        return {"objective":objective,"files":list(paths),"verification_required":True,
                "approval_required":True,"plan_id":hashlib.sha256((objective+"|"+"|".join(paths)).encode()).hexdigest()[:16]}

class PlatformReleaseChecker:
    """Phase 80: deterministic platform readiness summary."""
    def check(self,settings,tests_green:bool=True)->dict[str,Any]:
        infra=infrastructure_plan(settings)
        return {"ready":tests_green and not infra.blockers,"tests_green":tests_green,
                "infrastructure":infra.as_dict(),"checked_at":now()}
