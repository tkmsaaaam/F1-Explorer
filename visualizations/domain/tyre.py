"""Tyre value object."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Tyre:
    compound: str
    new: bool

    def get_compound(self) -> str:
        return self.compound

    def get_new(self) -> bool:
        return self.new
