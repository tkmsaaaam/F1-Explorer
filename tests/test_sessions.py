"""Session codes, FastF1 names, and legacy names share one identity."""

from types import SimpleNamespace

import pytest

from f1_explorer.config import Config, SessionCategory
from f1_explorer.sessions import SESSION_TABLE, session_code, session_start_at, is_race_session
from f1_explorer.visualizations.report_layout import layout_for_session


@pytest.mark.parametrize("code,name,slot,category,prefix", [
    ("FP1", "Practice 1", 1, SessionCategory.FreePractice, "P"),
    ("FP2", "Practice 2", 2, SessionCategory.FreePractice, "P"),
    ("FP3", "Practice 3", 3, SessionCategory.FreePractice, "P"),
    ("SQ", "Sprint Qualifying", 2, SessionCategory.Qualifying, "Q"),
    ("Q", "Qualifying", 4, SessionCategory.Qualifying, "Q"),
    ("S", "Sprint", 3, SessionCategory.Race, "R"),
    ("R", "Race", 5, SessionCategory.Race, "R"),
])
def test_identity_across_config_start_and_layout(code, name, slot, category, prefix):
    assert Config(2026, 1, code, {}, [], []).get_session_category() is category
    event = SimpleNamespace(**{f"Session{i}Date": i for i in range(1, 6)})
    for label in (code, name, f" {name.upper()} ", *SESSION_TABLE[code].aliases):
        assert session_code(label) == code
        assert session_start_at(SimpleNamespace(name=label, event=event), category) == slot
        assert layout_for_session(label)[0] == prefix
        assert is_race_session(label) is (category is SessionCategory.Race)
    other = SessionCategory.Qualifying if category is SessionCategory.Race else SessionCategory.Race
    assert session_start_at(SimpleNamespace(name=name, event=event), other) is None


@pytest.mark.parametrize("name", ["Unknown", "Not Practice 1", "Sprint Qualifying extra", "", "Shootout"])
def test_unknown_names_are_not_recognized_by_substring(name):
    assert session_code(name) is None
    assert layout_for_session(name) is None
    assert not is_race_session(name)
