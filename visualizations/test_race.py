import unittest

import pandas
from fastf1.core import Laps

from visualizations.race import make_driver_laps_set


class Race(unittest.TestCase):
    def test_make_lap_log(self):
        data = {
            "DriverNumber": ["1", "1", "1"],
            "Driver": ["Max", "Max", "Max"],
            "Stint": [1, 1, 1],
            "Team": ["Red Bull", "Red Bull", "Red Bull"],
            "LapNumber": [1, 2, 3],
            "LapTime": pandas.to_timedelta(["83.456s", "82.789s", "83.000s"]),
        }
        laps = Laps(pandas.DataFrame(data))
        result = make_driver_laps_set(laps)
        self.assertEqual(1, len(result))
        self.assertEqual(3, len(list(result)[0].laps))


if __name__ == '__main__':
    unittest.main()
