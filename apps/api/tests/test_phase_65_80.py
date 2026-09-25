from nexus.core.platform2 import (
 ResourceGraphStore,ResourceLink,IdentityStore,SecretVault,InfrastructurePlan,infrastructure_plan,
 AdaptivePlanner,SpecialistRegistry,Specialist,ConnectorRegistry,Connector,AnalyticsEngine,
 CostLedger,SecurityPolicyEngine,MultimodalRegistry,DeveloperWorkflow,PlatformReleaseChecker)
from nexus.core.events import EventStore

def test_phase65_resource_graph(tmp_path):
 s=ResourceGraphStore(tmp_path/"r.sqlite3"); s.upsert(ResourceLink("a","w","dataset",owner_id="u"))
 assert s.summary("w")=={"dataset":1}

def test_phase67_identity(tmp_path):
 s=IdentityStore(tmp_path/"i.sqlite3"); p=s.create("t","Naveed",("admin",)); assert s.get(p.principal_id).tenant_id=="t"

def test_phase68_secret_vault(tmp_path):
 from cryptography.fernet import Fernet
 s=SecretVault(tmp_path/"s.sqlite3",Fernet.generate_key()); sid=s.put("t","openai","secret")
 assert s.get(sid)=="secret"

def test_phase70_71_planning():
 plan=AdaptivePlanner().plan("analyze this CSV dataset"); assert plan.specialist=="data-scientist"
 reg=SpecialistRegistry(); reg.register(Specialist("data","Data",("csv","ml"))); assert reg.match(("csv",))[0].specialist_id=="data"

def test_phase72_connector():
 r=ConnectorRegistry(); r.register(Connector("github","GitHub",("read_repo","write_pr"),"oauth")); assert r.get("github").name=="GitHub"

def test_phase73_analytics(tmp_path):
 e=EventStore(str(tmp_path/"e.sqlite3")); a=AnalyticsEngine(e); assert a.execution()["event_count"]==0

def test_phase75_cost(tmp_path):
 s=CostLedger(tmp_path/"c.sqlite3"); s.record("t",10,1.5,"model"); assert s.usage("t")["cost"]==1.5

def test_phase76_security():
 assert not SecurityPolicyEngine().check("delete",risk_level="critical",roles=())["allowed"]
 assert SecurityPolicyEngine().check("delete",risk_level="critical",roles=("admin",))["allowed"]

def test_phase77_asset():
 a=MultimodalRegistry().register(b"abc","image"); assert len(a.sha256)==64 and a.size_bytes==3

def test_phase78_developer():
 p=DeveloperWorkflow().inspect("fix bug",["b.py","a.py"]); assert p["files"]==["a.py","b.py"]

def test_phase80_release():
 class S: deployment_mode="single"; state_backend="sqlite"; queue_backend="sqlite"; cache_backend="memory"; object_storage_backend="filesystem"
 assert PlatformReleaseChecker().check(S())["ready"]


def test_groq_models_are_executable():
    from nexus.core.models import model_registry, provider_model_specs
    assert all(m.provider == "openai" for m in model_registry.all())
    assert provider_model_specs("groq")
    assert all(m.provider == "groq" and m.supports_tools for m in provider_model_specs("groq"))


def test_persistent_byok_survives_manager_restart(tmp_path, monkeypatch):
    key_path = tmp_path / "credentials.key"
    db_path = tmp_path / "credentials.sqlite3"
    monkeypatch.setenv("NEXUS_CREDENTIAL_KEY_PATH", str(key_path))
    from nexus.core.models import PersistentCredentialStore, BYOKProviderManager
    first = BYOKProviderManager(PersistentCredentialStore(db_path))
    first.configure("user-1", "groq", "gsk-test-credential")
    second = BYOKProviderManager(PersistentCredentialStore(db_path))
    assert second.configured("user-1") == ("groq",)
    assert second.preferred("user-1") == "groq"
    assert second.credential("user-1", "groq").key == "gsk-test-credential"
