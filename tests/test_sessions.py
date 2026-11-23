"""Session codes, FastF1 names, and legacy names share one identity."""

from types import SimpleNamespace

import pandas as pd
import pytest

from f1_explorer.config import Config, SessionCategory
from f1_explorer.sessions import (
    SESSION_TABLE, fastf1_identifier, is_race_session, session_code, session_start_at,
)
from f1_explorer.visualizations.report_layout import layout_for_session


@pytest.mark.parametrize("code,name,category,prefix", [
    ("FP1", "Practice 1", SessionCategory.FreePractice, "P"),
    ("FP2", "Practice 2", SessionCategory.FreePractice, "P"),
    ("FP3", "Practice 3", SessionCategory.FreePractice, "P"),
    ("SQ", "Sprint Qualifying", SessionCategory.Qualifying, "Q"),
    ("Q", "Qualifying", SessionCategory.Qualifying, "Q"),
    ("S", "Sprint", SessionCategory.Race, "R"),
    ("R", "Race", SessionCategory.Race, "R"),
])
def test_identity_across_config_start_and_layout(code, name, category, prefix):
    assert Config(2026, 1, code, {}, [], []).get_session_category() is category
    date = pd.Timestamp("2023-04-28 13:00")
    for label in (code, name, f" {name.upper()} ", *SESSION_TABLE[code].aliases):
        assert session_code(label) == code
        assert session_start_at(SimpleNamespace(name=label, date=date), category) == date.tz_localize("UTC")
        assert layout_for_session(label)[0] == prefix
        assert is_race_session(label) is (category is SessionCategory.Race)
    other = SessionCategory.Qualifying if category is SessionCategory.Race else SessionCategory.Race
    assert session_start_at(SimpleNamespace(name=name, date=date), other) is None


@pytest.mark.parametrize("year,code,expected", [
    (2023, "SQ", "SS"),   # FastF1 renamed 2023 Sprint Qualifying to Sprint Shootout.
    (2022, "SQ", "SQ"),
    (2024, "SQ", "SQ"),
    (2023, "Q", "Q"),
    ("2023", "SQ", "SS"),  # config.json years may be strings.
])
def test_fastf1_identifier(year, code, expected):
    assert fastf1_identifier(year, code) == expected


@pytest.mark.parametrize("name", ["Unknown", "Not Practice 1", "Sprint Qualifying extra", "", "Shootout"])
def test_unknown_names_are_not_recognized_by_substring(name):
    assert session_code(name) is None
    assert layout_for_session(name) is None
    assert not is_race_session(name)
