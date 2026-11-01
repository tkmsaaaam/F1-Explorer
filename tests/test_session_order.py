"""Tests for classification ordering used by interactive figures."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

import pandas

from f1_explorer.visualizations.session_order import driver_order, driver_sort_key


class SessionOrderTest(unittest.TestCase):
    def test_classification_is_preferred_and_missing_drivers_use_fastest_lap(self) -> None:
        session = SimpleNamespace(
            results=pandas.DataFrame({
                "DriverNumber": ["63", "44"],
                "Position": [2, 1],
            }),
            laps=pandas.DataFrame({
                "DriverNumber": ["1", "63", "44"],
                "LapTime": pandas.to_timedelta([90, 92, 91], unit="s"),
            }),
        )
        ranks = driver_order(session)
        self.assertEqual(ranks["44"], 1)
        self.assertEqual(ranks["63"], 2)
        self.assertEqual(ranks["1"], 3)
        self.assertLess(driver_sort_key("44", ranks), driver_sort_key("63", ranks))

    def test_unclassified_driver_is_sorted_last(self) -> None:
        ranks = {"44": 1}
        self.assertGreater(driver_sort_key("999", ranks), driver_sort_key("44", ranks))

    def test_numeric_results_survive_float_upcast(self) -> None:
        session = SimpleNamespace(
            # A single numeric dtype pair makes row iteration upcast to float,
            # which previously created keys like "2.0" that never matched.
            results=pandas.DataFrame({
                "DriverNumber": [2.0, 10.0],
                "Position": [1.0, 2.0],
            }),
            laps=pandas.DataFrame(),
        )
        ranks = driver_order(session)
        self.assertEqual({"2": 1, "10": 2}, ranks)
        self.assertLess(driver_sort_key(2, ranks), driver_sort_key(10, ranks))

    def test_lap_side_float_numbers_are_normalized(self) -> None:
        session = SimpleNamespace(
            results=pandas.DataFrame(),
            laps=pandas.DataFrame({
                "DriverNumber": [2.0, 2.0, 10.0],
                "LapTime": pandas.to_timedelta([82, 80, 83], unit="s"),
            }),
        )
        ranks = driver_order(session)
        self.assertEqual({"2": 1, "10": 2}, ranks)
        self.assertLess(driver_sort_key(2, ranks), driver_sort_key(10, ranks))

    def test_deleted_laps_do_not_win_the_fallback(self) -> None:
        session = SimpleNamespace(
            results=pandas.DataFrame(),
            laps=pandas.DataFrame({
                "DriverNumber": ["1", "1", "2"],
                "LapTime": pandas.to_timedelta([83, 60, 82], unit="s"),
                "Deleted": [False, True, False],
            }),
        )
        ranks = driver_order(session)
        self.assertEqual({"2": 1, "1": 2}, ranks)

    def test_unknown_deleted_marks_do_not_break_the_fallback(self) -> None:
        session = SimpleNamespace(
            results=pandas.DataFrame(),
            laps=pandas.DataFrame({
                "DriverNumber": ["1", "2"],
                "LapTime": pandas.to_timedelta([83, 82], unit="s"),
                "Deleted": [float("nan"), float("nan")],
            }),
        )
        ranks = driver_order(session)
        self.assertEqual({"2": 1, "1": 2}, ranks)


if __name__ == "__main__":
    unittest.main()
