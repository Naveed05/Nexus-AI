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
