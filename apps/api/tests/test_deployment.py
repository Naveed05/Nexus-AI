from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_container_deployment_files_exist() -> None:
    assert (ROOT / "apps/api/Dockerfile").exists()
    assert (ROOT / "docker-compose.yml").exists()
    assert (ROOT / ".dockerignore").exists()


def test_dockerfile_runs_as_non_root_and_has_healthcheck() -> None:
    dockerfile = (ROOT / "apps/api/Dockerfile").read_text()
    assert "USER nexus" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert 'uvicorn", "nexus.api.main:app"' in dockerfile


def test_deployment_docs_define_single_instance_scaling_boundary() -> None:
    docs = (ROOT / "DEPLOYMENT.md").read_text()
    assert "horizontal scaling" in docs
    assert "transactional database" in docs
