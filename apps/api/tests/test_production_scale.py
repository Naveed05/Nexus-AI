from nexus.core.production_scale import build_scale_deployment, deployment_payload
from nexus.core.scale import build_scale_topology


def test_single_instance_mode_is_ready_with_local_backends():
    topology = build_scale_topology(state_backend="sqlite", queue_backend="sqlite", cache_backend="memory", object_storage_backend="filesystem")
    deployment = build_scale_deployment(mode="single", region="", instance_id="", topology=topology)
    assert deployment.ready is True
    assert deployment.blockers == ()
    assert deployment_payload(deployment)["mode"] == "single"


def test_global_mode_fails_closed_without_shared_backends():
    topology = build_scale_topology(state_backend="sqlite", queue_backend="sqlite", cache_backend="memory", object_storage_backend="filesystem")
    deployment = build_scale_deployment(mode="global", region="ap-south-1", instance_id="api-1", topology=topology)
    assert deployment.ready is False
    assert deployment.blockers


def test_global_mode_requires_identity_and_region():
    topology = build_scale_topology(state_backend="postgres", queue_backend="redis", cache_backend="redis", object_storage_backend="s3")
    deployment = build_scale_deployment(mode="global", region="", instance_id="", topology=topology)
    assert deployment.ready is False
    assert "deployment region is required for distributed runtime" in deployment.blockers
    assert "instance identity is required for distributed runtime" in deployment.blockers


def test_horizontal_shared_deployment_is_ready():
    topology = build_scale_topology(state_backend="postgres", queue_backend="redis", cache_backend="redis", object_storage_backend="s3")
    deployment = build_scale_deployment(mode="horizontal", region="ap-south-1", instance_id="api-1", topology=topology)
    assert deployment.ready is True


def test_scale_deployment_has_stable_identity():
    topology = build_scale_topology(state_backend="postgres", queue_backend="redis", cache_backend="redis", object_storage_backend="s3")
    first = build_scale_deployment(mode="global", region="ap-south-1", instance_id="api-1", topology=topology)
    second = build_scale_deployment(mode="global", region="ap-south-1", instance_id="api-1", topology=topology)
    assert first.contract_version == "phase-35.v1"
    assert len(first.deployment_fingerprint) == 64
    assert first.deployment_fingerprint == second.deployment_fingerprint
    assert deployment_payload(first)["deployment_fingerprint"] == first.deployment_fingerprint


def test_scale_deployment_identity_changes_with_instance():
    topology = build_scale_topology(state_backend="postgres", queue_backend="redis", cache_backend="redis", object_storage_backend="s3")
    first = build_scale_deployment(mode="horizontal", region="ap-south-1", instance_id="api-1", topology=topology)
    second = build_scale_deployment(mode="horizontal", region="ap-south-1", instance_id="api-2", topology=topology)
    assert first.deployment_fingerprint != second.deployment_fingerprint
