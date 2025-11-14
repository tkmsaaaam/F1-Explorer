import unittest

import pandas
from fastf1.core import Laps

from visualizations.long_runs import make_stint_set, Stint


class LongRuns(unittest.TestCase):
    def test_make_stint_set_no_same_compound(self):
        data = {
            "DriverNumber": ["1", "1", "1"],
            "Driver": ["Max", "Max", "Max"],
            "Stint": [1, 1, 1],
            "Team": ["Red Bull", "Red Bull", "Red Bull"],
            "LapTime": pandas.to_timedelta(["83.456s", "82.789s", "83.000s"]),
            "TyreLife": [1, 2, 3],
            "Compound": ["HARD", "HARD", "HARD"]
        }

        laps = Laps(pandas.DataFrame(data))
        stint_set: set[Stint] = make_stint_set(2, laps, "SOFT")
        self.assertEqual(0, len(stint_set))

    def test_make_stint_set_no_consecutive_laps(self):
        data = {
            "DriverNumber": ["1", "16", "69"],
            "Driver": ["Max", "Charles", "George"],
            "Stint": [1, 1, 1],
            "Team": ["Red Bull", "Ferrari", "Mercedes"],
            "LapTime": pandas.to_timedelta(["83.456s", "82.789s", "83.000s"]),
            "TyreLife": [1, 1, 1],
            "Compound": ["SOFT", "SOFT", "SOFT"]
        }

        laps = Laps(pandas.DataFrame(data))
        stint_set: set[Stint] = make_stint_set(2, laps, "SOFT")
        self.assertEqual(0, len(stint_set))

    def test_make_stint_set_slow_lap_time_in_consecutive_laps(self):
        data = {
            "DriverNumber": ["1", "1", "1"],
            "Driver": ["Max", "Max", "Max"],
            "Stint": [1, 1, 1],
            "Team": ["Red Bull", "Red Bull", "Red Bull"],
            "LapTime": pandas.to_timedelta(["83.456s", "100.789s", "83.000s"]),
            "TyreLife": [1, 2, 3],
            "Compound": ["SOFT", "SOFT", "SOFT"]
        }

        laps = Laps(pandas.DataFrame(data))
        stint_set: set[Stint] = make_stint_set(2, laps, "SOFT")
        self.assertEqual(1, len(stint_set))
        self.assertEqual(1, list(stint_set)[0].driver.number)
        self.assertEqual("Max", list(stint_set)[0].driver.name)
        self.assertEqual("Red Bull", list(stint_set)[0].driver.team_name)
        self.assertEqual("SOFT", list(stint_set)[0].compound)
        self.assertEqual(2, len(list(stint_set)[0].laps))
        self.assertEqual(83.456, list(stint_set)[0].laps.get(1))
        self.assertEqual(83.000, list(stint_set)[0].laps.get(3))

    def test_make_stint_set_one_driver(self):
        data = {
            "DriverNumber": ["1", "1", "1"],
            "Driver": ["Max", "Max", "Max"],
            "Stint": [1, 1, 1],
            "Team": ["Red Bull", "Red Bull", "Red Bull"],
            "LapTime": pandas.to_timedelta(["83.456s", "82.789s", "83.000s"]),
            "TyreLife": [1, 2, 3],
            "Compound": ["SOFT", "SOFT", "SOFT"]
        }

        laps = Laps(pandas.DataFrame(data))
        stint_set: set[Stint] = make_stint_set(2, laps, "SOFT")
        self.assertEqual(1, len(stint_set))
        self.assertEqual(1, list(stint_set)[0].driver.number)
        self.assertEqual("Max", list(stint_set)[0].driver.name)
        self.assertEqual("Red Bull", list(stint_set)[0].driver.team_name)
        self.assertEqual("SOFT", list(stint_set)[0].compound)
        self.assertEqual(3, len(list(stint_set)[0].laps))
        self.assertEqual(83.456, list(stint_set)[0].laps.get(1))
        self.assertEqual(82.789, list(stint_set)[0].laps.get(2))
        self.assertEqual(83.000, list(stint_set)[0].laps.get(3))

    def test_make_stint_set_two_drivers(self):
        data = {
            "DriverNumber": ["1", "1", "1", "16", "16"],
            "Driver": ["Max", "Max", "Max", "Charles", "Charles"],
            "Stint": [1, 1, 1, 1, 1],
            "Team": ["Red Bull", "Red Bull", "Red Bull", "Ferrari", "Ferrari"],
            "LapTime": pandas.to_timedelta(["83.456s", "82.789s", "83.000s", "83.600s", "83.700s"]),
            "TyreLife": [1, 2, 3, 1, 2],
            "Compound": ["SOFT", "SOFT", "SOFT", "SOFT", "SOFT"]
        }

        laps = Laps(pandas.DataFrame(data))
        stint_set: set[Stint] = make_stint_set(2, laps, "SOFT")
        self.assertEqual(2, len(stint_set))


if __name__ == '__main__':
    unittest.main()
