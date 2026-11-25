import json

import pytest

from f1_explorer.config import Config, load_config
from f1_explorer.separator_estimator import SeparatorBoundary


def test_active_separators_keep_structured_boundaries_and_fractional_distances():
    config = Config(2026, 15, "FP1", {"1": [10.5]}, [100.5], [])
    boundary = SeparatorBoundary(100.5, 0, 1)
    config.set_separator([100.5], (boundary,))
    assert config.get_separator() == [100.5]
    assert config.get_separator_boundaries() == [boundary]
    config.set_separator([200.5], ({"distance": 200.5, "sector": 1, "segment": 2},))
    assert config.get_separator_boundaries() == [{"distance": 200.5, "sector": 1, "segment": 2}]


@pytest.mark.parametrize(("settings", "expected"), [
    ({"separator": [100], "Separator": {"2025": {"Elsewhere": [300]}}}, [100]),
    ({"Separator": [100], "separator": {"2025": {"Elsewhere": [300]}}}, [100]),
    ({"separator": [120], "Separator": [100]}, [120]),
    ({"Separator": [100]}, [100]),
    ({"separator": [0, "NaN", "inf", 10 ** 400, None, "120.5"]}, [120.5]),
    ({"separator": [120]}, [120]),
    ({"Separator": {"2025": {"Elsewhere": [300]}}}, []),
])
def test_load_legacy_separator(tmp_path, monkeypatch, settings, expected):
    monkeypatch.chdir(tmp_path)
    config = {"Year": 2025, "Round": 1, "Session": "FP1", **settings}
    (tmp_path / "config.json").write_text(json.dumps(config))
    assert load_config().get_separator() == expected
