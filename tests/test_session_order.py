"""Tests for classification ordering used by interactive figures."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

import pandas

from visualizations.session_order import driver_order, driver_sort_key


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


if __name__ == "__main__":
    unittest.main()
