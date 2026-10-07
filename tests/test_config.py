from f1_explorer.config import Config
from f1_explorer.separator_estimator import SeparatorBoundary


def test_active_separators_keep_structured_boundaries_and_fractional_distances():
    config = Config(2026, 15, "FP1", {"1": [10.5]}, [100.5], [])
    boundary = SeparatorBoundary(100.5, 0, 1)
    config.set_separator([100.5], (boundary,))
    assert config.get_separator() == [100.5]
    assert config.get_separator_boundaries() == [boundary]
    config.set_separator([200.5], ({"distance": 200.5, "sector": 1, "segment": 2},))
    assert config.get_separator_boundaries() == [{"distance": 200.5, "sector": 1, "segment": 2}]
