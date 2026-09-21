from nexus.core.scale import build_scale_topology, topology_payload


def test_default_single_instance_topology_is_explicit():
    topology = build_scale_topology(
        state_backend="sqlite",
        queue_backend="sqlite",
        cache_backend="memory",
        object_storage_backend="filesystem",
    )
    assert topology.horizontal_scaling_ready is False
    assert len(topology.blockers) == 4
    assert topology_payload(topology)["horizontal_scaling_ready"] is False


def test_shared_backends_clear_scale_blockers():
    topology = build_scale_topology(
        state_backend="postgres",
        queue_backend="redis",
        cache_backend="redis",
        object_storage_backend="s3",
    )
    assert topology.horizontal_scaling_ready is True
    assert topology.blockers == ()
