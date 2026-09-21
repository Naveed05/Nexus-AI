from nexus.core.scale_storage import ContentAddressedObjectStore, TTLCache


def test_ttl_cache_round_trip_and_eviction():
    cache = TTLCache(max_entries=1)
    cache.set("a", "one", ttl_seconds=60)
    assert cache.get("a") == "one"
    cache.set("b", "two", ttl_seconds=60)
    assert cache.get("b") == "two"
    assert cache.get("a") is None


def test_content_addressed_object_store_is_deterministic(tmp_path):
    store = ContentAddressedObjectStore(str(tmp_path / "objects"))
    first = store.put(b"hello", namespace="workspace-1")
    second = store.put(b"hello", namespace="workspace-1")
    assert first.object_id == second.object_id
    assert first.sha256 == second.sha256
    assert store.get(first.object_id, namespace="workspace-1") == b"hello"


def test_object_store_enforces_namespace(tmp_path):
    store = ContentAddressedObjectStore(str(tmp_path / "objects"))
    obj = store.put(b"secret", namespace="workspace-1")
    try:
        store.get(obj.object_id, namespace="workspace-2")
        assert False, "expected namespace rejection"
    except ValueError:
        pass
