from nexus.core.product import ProductCatalog


def test_product_catalog_defaults_to_local_plan() -> None:
    catalog = ProductCatalog()
    profile = catalog.profile("user-1")
    assert profile.plan_id == "local"


def test_product_usage_is_bounded_by_plan() -> None:
    catalog = ProductCatalog()
    for _ in range(100):
        catalog.consume_run("user-2")
    try:
        catalog.consume_run("user-2")
    except RuntimeError as exc:
        assert "run limit" in str(exc)
    else:
        raise AssertionError("expected run limit")


def test_product_plan_can_change() -> None:
    catalog = ProductCatalog()
    profile = catalog.set_plan("user-3", "pro")
    assert profile.plan_id == "pro"
    assert catalog.usage("user-3").runs_limit == 1000
