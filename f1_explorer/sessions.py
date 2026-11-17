"""Session identities shared by configuration, entrypoints, and reports."""

from dataclasses import dataclass
from enum import Enum


class SessionCategory(Enum):
    FreePractice = "FreePractice"
    Qualifying = "Qualifying"
    Race = "Race"


@dataclass(frozen=True)
class SessionDefinition:
    fastf1_name: str
    date_slot: str
    category: SessionCategory
    entrypoint: str
    uses_separators: bool
    aliases: tuple[str, ...] = ()


SESSION_TABLE = {
    "FP1": SessionDefinition("Practice 1", "Session1Date", SessionCategory.FreePractice, "analyze_practice.py", True),
    "FP2": SessionDefinition("Practice 2", "Session2Date", SessionCategory.FreePractice, "analyze_practice.py", True),
    "FP3": SessionDefinition("Practice 3", "Session3Date", SessionCategory.FreePractice, "analyze_practice.py", True),
    "SQ": SessionDefinition("Sprint Qualifying", "Session2Date", SessionCategory.Qualifying, "analyze_qualifying.py", True,
                            ("Sprint Shootout",)),
    "S": SessionDefinition("Sprint", "Session3Date", SessionCategory.Race, "analyze_race.py", False, ("Sprint Race",)),
    "Q": SessionDefinition("Qualifying", "Session4Date", SessionCategory.Qualifying, "analyze_qualifying.py", True),
    "R": SessionDefinition("Race", "Session5Date", SessionCategory.Race, "analyze_race.py", False),
}


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


def session_start_at(session, category: SessionCategory):
    definition = session_definition(session.name)
    if definition is None or definition.category != category:
        return None
    return getattr(session.event, definition.date_slot)
