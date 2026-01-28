import unittest

import pandas
from fastf1.core import Laps

from visualizations.race import make_driver_laps_set, make_lap_start_by_position_by_number, make_top_time_map


class Race(unittest.TestCase):
    def test_make_lap_log_empty(self):
        data = {
            "DriverNumber": [],
            "Driver": [],
            "Stint": [],
            "Team": [],
            "LapNumber": [],
            "Position": [],
            "Compound": [],
            "FreshTyre": [],
            "PitOutTime": pandas.to_datetime([]),
            "Time": pandas.to_datetime([]),
            "LapTime": pandas.to_timedelta([]),
        }
        laps = Laps(pandas.DataFrame(data))
        result = make_driver_laps_set(laps)
        self.assertEqual(0, len(result))

    def test_make_lap_log(self):
        data = {
            "DriverNumber": ["1", "1", "16"],
            "Driver": ["Max", "Max", "Lec"],
            "Stint": [1, 1, 1],
            "Team": ["Red Bull", "Red Bull", "Ferrari"],
            "LapNumber": [1, 2, 1],
            "Position": [1, 1, 2],
            "Compound": ["Soft", "Soft", "Soft"],
            "FreshTyre": [True, True, True],
            "PitOutTime": pandas.to_datetime(["", "", ""]),
            "Time": pandas.to_datetime(["2026-01-01 00:00:00", "2026-01-01 00:01:23", "2026-01-01 00:00:0"]),
            "LapTime": pandas.to_timedelta(["83.456s", "82.789s", "83.000s"]),
        }
        laps = Laps(pandas.DataFrame(data))
        result = make_driver_laps_set(laps)
        self.assertEqual(2, len(result))
        self.assertEqual(2, len(list(result)[0].laps))
        self.assertEqual(1, list(result)[0].driver.get_number())
        self.assertEqual('Max', list(result)[0].driver.get_name())
        self.assertEqual('Red Bull', list(result)[0].driver.get_team_name())
        self.assertEqual(83.456, list(result)[0].laps[1].get_time())
        self.assertEqual(pandas.to_datetime("2026-01-01 00:00:00"), list(result)[0].laps[1].get_at())
        self.assertEqual(1, list(result)[0].laps[1].get_position())
        self.assertEqual(True, list(result)[0].laps[1].get_pit_out())
        self.assertEqual(True, list(result)[0].laps[1].get_tyre().get_new())
        self.assertEqual('Soft', list(result)[0].laps[1].get_tyre().get_compound())
        self.assertEqual(82.789, list(result)[0].laps[2].get_time())
        self.assertEqual(pandas.to_datetime("2026-01-01 00:01:23"), list(result)[0].laps[2].get_at())
        self.assertEqual(1, list(result)[0].laps[2].get_position())
        self.assertEqual(True, list(result)[0].laps[2].get_pit_out())
        self.assertEqual(True, list(result)[0].laps[2].get_tyre().get_new())
        self.assertEqual('Soft', list(result)[0].laps[2].get_tyre().get_compound())

        self.assertEqual(1, len(list(result)[1].laps))
        self.assertEqual(16, list(result)[1].driver.get_number())
        self.assertEqual('Lec', list(result)[1].driver.get_name())
        self.assertEqual('Ferrari', list(result)[1].driver.get_team_name())
        self.assertEqual(83.000, list(result)[1].laps[1].get_time())
        self.assertEqual(pandas.to_datetime("2026-01-01 00:00:00"), list(result)[1].laps[1].get_at())
        self.assertEqual(2, list(result)[1].laps[1].get_position())
        self.assertEqual(True, list(result)[1].laps[1].get_pit_out())
        self.assertEqual(True, list(result)[1].laps[1].get_tyre().get_new())
        self.assertEqual('Soft', list(result)[1].laps[1].get_tyre().get_compound())

    def test_make_lap_start_by_position_by_number(self):
        data = {
            "DriverNumber": ["1", "1", "16", "16"],
            "Driver": ["Max", "Max", "Lec", "Lec"],
            "Stint": [1, 1, 1, 1],
            "Team": ["Red Bull", "Red Bull", "Ferrari", "Ferrari"],
            "LapNumber": [1, 2, 1, 2],
            "Position": [1, 1, 2, 2],
            "Compound": ["Soft", "Soft", "Soft", "Soft"],
            "FreshTyre": [True, True, True, True],
            "PitOutTime": pandas.to_datetime(["", "", "", ""]),
            "Time": pandas.to_datetime(
                ["2026-01-01 00:00:00", "2026-01-01 00:01:23", "2026-01-01 00:00:00", "2026-01-01 00:01:24"]),
            "LapTime": pandas.to_timedelta(["83.456s", "82.789s", "84.000s", "83.000s"]),
        }
        laps = Laps(pandas.DataFrame(data))
        result = make_lap_start_by_position_by_number(laps)
        self.assertEqual(2, len(result))
        self.assertEqual(pandas.to_datetime("2026-01-01 00:00:00"), result[1][1])
        self.assertEqual(pandas.to_datetime("2026-01-01 00:00:00"), result[1][2])
        self.assertEqual(pandas.to_datetime("2026-01-01 00:01:23"), result[2][1])
        self.assertEqual(pandas.to_datetime("2026-01-01 00:01:24"), result[2][2])

    def test_make_top_time_map(self):
        data = {
            "DriverNumber": ["1", "1", "16", "16"],
            "Driver": ["Max", "Max", "Lec", "Lec"],
            "Stint": [1, 1, 1, 1],
            "Team": ["Red Bull", "Red Bull", "Ferrari", "Ferrari"],
            "LapNumber": [1, 2, 1, 2],
            "Position": [1, 1, 2, 2],
            "Compound": ["Soft", "Soft", "Soft", "Soft"],
            "FreshTyre": [True, True, True, True],
            "PitOutTime": pandas.to_datetime(["", "", "", ""]),
            "Time": pandas.to_datetime(
                ["2026-01-01 00:00:00", "2026-01-01 00:01:23", "2026-01-01 00:00:00", "2026-01-01 00:01:24"]),
            "LapTime": pandas.to_timedelta(["83.456s", "82.789s", "84.000s", "83.000s"]),
        }
        laps = Laps(pandas.DataFrame(data))
        result = make_top_time_map(laps)
        self.assertEqual(2, len(result))
        self.assertEqual(pandas.to_datetime("2026-01-01 00:00:00"), result[1])
        self.assertEqual(pandas.to_datetime("2026-01-01 00:01:23"), result[2])


if __name__ == '__main__':
    unittest.main()
