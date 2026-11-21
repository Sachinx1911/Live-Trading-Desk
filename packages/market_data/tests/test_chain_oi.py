from market_data.repo.chains import oi_totals


def test_oi_totals_sums_each_side_and_ignores_bad_rows() -> None:
    rows = [
        {"option_type": "PE", "oi": 1000, "strike": "25000"},
        {"option_type": "PE", "oi": 500},
        {"option_type": "CE", "oi": 600},
        {"option_type": "CE", "oi": None},
        {"option_type": "CE", "oi": -5},
        {"option_type": "XX", "oi": 99},
        {"oi": 10},
    ]
    assert oi_totals(rows) == (1500, 600)
    assert oi_totals([]) == (0, 0)
