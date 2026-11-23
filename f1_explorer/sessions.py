"""Session identities shared by configuration, entrypoints, and reports."""

import datetime
from dataclasses import dataclass
from enum import Enum


class SessionCategory(Enum):
    FreePractice = "FreePractice"
    Qualifying = "Qualifying"
    Race = "Race"


@dataclass(frozen=True)
class SessionDefinition:
    fastf1_name: str
    category: SessionCategory
    entrypoint: str
    uses_separators: bool
    aliases: tuple[str, ...] = ()


SESSION_TABLE = {
    "FP1": SessionDefinition("Practice 1", SessionCategory.FreePractice, "analyze_practice.py", True),
    "FP2": SessionDefinition("Practice 2", SessionCategory.FreePractice, "analyze_practice.py", True),
    "FP3": SessionDefinition("Practice 3", SessionCategory.FreePractice, "analyze_practice.py", True),
    "SQ": SessionDefinition("Sprint Qualifying", SessionCategory.Qualifying, "analyze_qualifying.py", True,
                            ("Sprint Shootout",)),
    "S": SessionDefinition("Sprint", SessionCategory.Race, "analyze_race.py", False, ("Sprint Race",)),
    "Q": SessionDefinition("Qualifying", SessionCategory.Qualifying, "analyze_qualifying.py", True),
    "R": SessionDefinition("Race", SessionCategory.Race, "analyze_race.py", False),
}

# FastF1 calls the 2023 sprint qualifying session "Sprint Shootout" ("SS").
_FASTF1_IDENTIFIER_OVERRIDES = {(2023, "SQ"): "SS"}


def fastf1_identifier(year: int, code: str) -> str:
    """Return the identifier FastF1 expects for a configured session code."""
    return _FASTF1_IDENTIFIER_OVERRIDES.get((int(year), code), code)


def session_code(name: str) -> str | None:
    normalized = str(name).strip().casefold()
    for code, definition in SESSION_TABLE.items():
        if normalized in (code.casefold(), definition.fastf1_name.casefold(),
                          *(alias.casefold() for alias in definition.aliases)):
            return code
    return None


def session_definition(name: str) -> SessionDefinition | None:
    code = session_code(name)
    return SESSION_TABLE.get(code)


def is_race_session(name: str) -> bool:
    definition = session_definition(name)
    return definition is not None and definition.category == SessionCategory.Race


def session_start_at(session, category: SessionCategory) -> datetime.datetime | None:
    """Return the scheduled start as a timezone-aware UTC timestamp.

    FastF1 exposes ``session.date`` as a timezone-naive UTC timestamp, so it
    must not be interpreted as local time. Returns ``None`` when the session
    does not belong to ``category``.
    """
    definition = session_definition(session.name)
    if definition is None or definition.category != category:
        return None
    return session.date.tz_localize("UTC")
