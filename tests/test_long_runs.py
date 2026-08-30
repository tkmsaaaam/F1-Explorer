import unittest

import pandas
from fastf1.core import Laps

from visualizations.long_runs import LongRunCriteria, make_stint_set, Stint


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
        stint_set: list[Stint] = make_stint_set(2, laps, "SOFT")
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
        stint_set: list[Stint] = make_stint_set(2, laps, "SOFT")
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
        stint_set: list[Stint] = make_stint_set(2, laps, "SOFT")
        # The slow lap is a separator; isolated laps on either side cannot
        # provide a trend and are therefore discarded.
        self.assertEqual(0, len(stint_set))

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
        stint_set: list[Stint] = make_stint_set(2, laps, "SOFT")
        self.assertEqual(1, len(stint_set))
        self.assertEqual(1, list(stint_set)[0].get_driver().get_number())
        self.assertEqual("Max", list(stint_set)[0].get_driver().get_name())
        self.assertEqual("Red Bull", list(stint_set)[0].get_driver().get_team_name())
        self.assertEqual("SOFT", list(stint_set)[0].get_compound())
        self.assertEqual(3, len(list(stint_set)[0].get_laps()))
        self.assertEqual(83.456, list(stint_set)[0].get_laps().get(1))
        self.assertEqual(82.789, list(stint_set)[0].get_laps().get(2))
        self.assertEqual(83.000, list(stint_set)[0].get_laps().get(3))

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
        stint_set: list[Stint] = make_stint_set(2, laps, "SOFT")
        self.assertEqual(2, len(stint_set))

    def test_red_flag_lap_removed_but_truncated_run_retained(self):
        data = {
            "DriverNumber": ["1"] * 3,
            "Driver": ["Max"] * 3,
            "Stint": [1] * 3,
            "Team": ["Red Bull"] * 3,
            "LapNumber": [10, 11, 12],
            "LapTime": pandas.to_timedelta(["94s", "94.4s", "120s"]),
            "TyreLife": [4, 5, 6],
            "Compound": ["SOFT"] * 3,
            "TrackStatus": ["1", "1", "5"],
        }
        result = make_stint_set(2, Laps(pandas.DataFrame(data)), "SOFT")
        self.assertEqual([{4: 94.0, 5: 94.4}], [stint.laps for stint in result])

    def test_opening_qualifying_phase_is_removed_and_later_run_retained(self):
        data = {
            "DriverNumber": ["1"] * 7,
            "Driver": ["Max"] * 7,
            "Stint": [1] * 7,
            "Team": ["Red Bull"] * 7,
            "LapNumber": list(range(1, 8)),
            "LapTime": pandas.to_timedelta(["89s", "89.2s", "110s", "95s", "95.2s", "95.4s", "95.6s"]),
            "TyreLife": list(range(1, 8)),
            "Compound": ["SOFT"] * 7,
        }
        result = make_stint_set(2, Laps(pandas.DataFrame(data)), "SOFT")
        self.assertEqual(1, len(result))
        self.assertEqual([4, 5, 6, 7], sorted(result[0].laps))

    def test_unlimited_traffic_laps_split_retained_blocks(self):
        data = {
            "DriverNumber": ["1"] * 9,
            "Driver": ["Max"] * 9,
            "Stint": [1] * 9,
            "Team": ["Red Bull"] * 9,
            "LapNumber": list(range(1, 10)),
            "LapTime": pandas.to_timedelta(["94s", "94.2s", "110s", "112s", "111s", "109s", "95s", "95.2s", "95.4s"]),
            "TyreLife": list(range(1, 10)),
            "Compound": ["SOFT"] * 9,
        }
        result = make_stint_set(2, Laps(pandas.DataFrame(data)), "SOFT")
        self.assertEqual([[1, 2], [7, 8, 9]], [sorted(stint.laps) for stint in result])

    def test_short_absolute_qualifying_phase_uses_other_stint_reference(self):
        data = {
            "DriverNumber": ["1"] * 6,
            "Driver": ["Max"] * 6,
            "Stint": [1, 1, 2, 2, 2, 2],
            "Team": ["Red Bull"] * 6,
            "LapNumber": [1, 2, 5, 6, 7, 8],
            "LapTime": pandas.to_timedelta(["89s", "89.2s", "88.8s", "95s", "95.2s", "95.4s"]),
            "TyreLife": [1, 2, 1, 2, 3, 4],
            "Compound": ["SOFT"] * 6,
        }
        result = make_stint_set(2, Laps(pandas.DataFrame(data)), "SOFT")
        # Stint 1 is close to the fastest clean lap from stint 2. The four-lap
        # second stint remains due to the automatic long-run rule.
        self.assertEqual([[1, 2, 3, 4]], [sorted(stint.laps) for stint in result])

    def test_short_run_without_external_reference_is_retained(self):
        data = {
            "DriverNumber": ["1", "1"], "Driver": ["Max", "Max"],
            "Stint": [1, 1], "Team": ["Red Bull", "Red Bull"],
            "LapNumber": [7, 8], "LapTime": pandas.to_timedelta(["95s", "95.3s"]),
            "TyreLife": [3, 4], "Compound": ["SOFT", "SOFT"],
        }
        result = make_stint_set(2, Laps(pandas.DataFrame(data)), "SOFT")
        self.assertEqual(1, len(result))

    def test_optional_quality_columns_filter_only_individual_laps(self):
        data = {
            "DriverNumber": ["1"] * 8, "Driver": ["Max"] * 8,
            "Stint": [1] * 8, "Team": ["Red Bull"] * 8,
            "LapNumber": list(range(1, 9)), "TyreLife": list(range(1, 9)),
            "LapTime": pandas.to_timedelta(["94s", "94.1s", None, "94.3s", "94.4s", "94.5s", "94.6s", "94.7s"]),
            "Compound": ["SOFT"] * 8,
            "PitInTime": [pandas.NaT, pandas.NaT, pandas.NaT, pandas.NaT, pandas.NaT, pandas.NaT, pandas.NaT,
                          pandas.to_timedelta(1, unit="s")],
            "PitOutTime": [pandas.NaT, pandas.NaT, pandas.NaT, pandas.to_timedelta(1, unit="s"),
                           pandas.NaT, pandas.NaT, pandas.NaT, pandas.NaT],
            "Deleted": [False, False, False, False, False, False, False, False],
            "IsAccurate": [True] * 8,
            "TrackStatus": ["1"] * 8,
        }
        result = make_stint_set(2, Laps(pandas.DataFrame(data)), "SOFT")
        self.assertEqual([[1, 2], [5, 6, 7]], [sorted(stint.laps) for stint in result])

    def test_criteria_can_raise_minimum_phase_length(self):
        data = {
            "DriverNumber": ["1"] * 3, "Driver": ["Max"] * 3,
            "Stint": [1] * 3, "Team": ["Red Bull"] * 3,
            "LapNumber": [1, 2, 3], "TyreLife": [1, 2, 3],
            "LapTime": pandas.to_timedelta(["94s", "94.1s", "94.2s"]),
            "Compound": ["SOFT"] * 3,
        }
        result = make_stint_set(3, Laps(pandas.DataFrame(data)), "SOFT", LongRunCriteria())
        self.assertEqual(1, len(result))


if __name__ == '__main__':
    unittest.main()
