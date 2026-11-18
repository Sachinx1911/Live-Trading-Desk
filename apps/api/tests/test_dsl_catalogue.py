from api.routers.dsl import build_catalogue


def test_catalogue_matches_registry_and_schema() -> None:
    from strategy.indicators import REGISTRY

    c = build_catalogue()
    assert {i.type for i in c.indicators} == set(REGISTRY)
    for i in c.indicators:
        assert i.outputs == list(REGISTRY[i.type].outputs)
        for p in i.params:
            assert p.type in ("int", "float", "string", "enum")
    assert "crosses_above" in c.cross_directions
    assert set(c.compare_ops) == {"gt", "gte", "lt", "lte", "eq"}
    assert "risk_percent" in c.sizing_methods and "atr" in c.level_units
    assert "INTRADAY" in c.products and "5m" in c.timeframes
