import unittest
import warnings
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas
from fastf1.core import Laps

from f1_explorer.visualizations.domain.driver import Driver
from f1_explorer.visualizations.domain.long_run import LongRun, LongRunPoint
from f1_explorer.visualizations.long_runs import (
    LongRunCriteria,
    select_long_runs,
    _make_interactive_long_run_figure,
    plot_by_tyre_age_and_tyre,
)


class LongRuns(unittest.TestCase):
    def test_no_same_compound(self):
        data = {
            "DriverNumber": ["1", "1", "1"],
            "Driver": ["Max", "Max", "Max"],
            "Stint": [1, 1, 1],
            "Team": ["Red Bull", "Red Bull", "Red Bull"],
            "LapNumber": [1, 2, 3],
            "LapTime": pandas.to_timedelta(["83.456s", "82.789s", "83.000s"]),
            "TyreLife": [1, 2, 3],
            "Compound": ["HARD", "HARD", "HARD"]
        }

        laps = Laps(pandas.DataFrame(data))
        runs = select_long_runs(2, laps, "SOFT")
        self.assertEqual(0, len(runs))

    def test_no_consecutive_laps(self):
        data = {
            "DriverNumber": ["1", "16", "69"],
            "Driver": ["Max", "Charles", "George"],
            "Stint": [1, 1, 1],
            "Team": ["Red Bull", "Ferrari", "Mercedes"],
            "LapNumber": [1, 2, 3],
            "LapTime": pandas.to_timedelta(["83.456s", "82.789s", "83.000s"]),
            "TyreLife": [1, 1, 1],
            "Compound": ["SOFT", "SOFT", "SOFT"]
        }

        laps = Laps(pandas.DataFrame(data))
        runs = select_long_runs(2, laps, "SOFT")
        self.assertEqual(0, len(runs))

    def test_slow_lap_time_in_consecutive_laps(self):
        data = {
            "DriverNumber": ["1", "1", "1"],
            "Driver": ["Max", "Max", "Max"],
            "Stint": [1, 1, 1],
            "Team": ["Red Bull", "Red Bull", "Red Bull"],
            "LapNumber": [1, 2, 3],
            "LapTime": pandas.to_timedelta(["83.456s", "100.789s", "83.000s"]),
            "TyreLife": [1, 2, 3],
            "Compound": ["SOFT", "SOFT", "SOFT"]
        }

        laps = Laps(pandas.DataFrame(data))
        runs = select_long_runs(2, laps, "SOFT")
        # The slow lap is a separator; isolated laps on either side cannot
        # provide a trend and are therefore discarded.
        self.assertEqual(0, len(runs))

    def test_one_driver(self):
        data = {
            "DriverNumber": ["1", "1", "1"],
            "Driver": ["Max", "Max", "Max"],
            "Stint": [1, 1, 1],
            "Team": ["Red Bull", "Red Bull", "Red Bull"],
            "LapNumber": [1, 2, 3],
            "LapTime": pandas.to_timedelta(["83.456s", "82.789s", "83.000s"]),
            "TyreLife": [1, 2, 3],
            "Compound": ["SOFT", "SOFT", "SOFT"]
        }

        laps = Laps(pandas.DataFrame(data))
        runs = select_long_runs(2, laps, "SOFT")
        self.assertEqual(1, len(runs))
        run = runs[0]
        self.assertEqual(1, run.driver.number)
        self.assertEqual("Max", run.driver.name)
        self.assertEqual("Red Bull", run.driver.team_name)
        self.assertEqual("SOFT", run.compound)
        self.assertEqual([(1.0, 83.456), (2.0, 82.789), (3.0, 83.0)],
                         [(point.tyre_age, point.lap_time_seconds) for point in run.points])

    def test_two_drivers(self):
        data = {
            "DriverNumber": ["1", "1", "1", "16", "16"],
            "Driver": ["Max", "Max", "Max", "Charles", "Charles"],
            "Stint": [1, 1, 1, 1, 1],
            "Team": ["Red Bull", "Red Bull", "Red Bull", "Ferrari", "Ferrari"],
            "LapNumber": [1, 2, 3, 1, 2],
            "LapTime": pandas.to_timedelta(["83.456s", "82.789s", "83.000s", "83.600s", "83.700s"]),
            "TyreLife": [1, 2, 3, 1, 2],
            "Compound": ["SOFT", "SOFT", "SOFT", "SOFT", "SOFT"]
        }

        laps = Laps(pandas.DataFrame(data))
        runs = select_long_runs(2, laps, "SOFT")
        self.assertEqual(2, len(runs))

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
        result = select_long_runs(2, Laps(pandas.DataFrame(data)), "SOFT")
        self.assertEqual(1, len(result))
        run = result[0]
        self.assertEqual([10, 11], [point.lap_number for point in run.points])
        self.assertEqual([4.0, 5.0], [point.tyre_age for point in run.points])
        self.assertEqual([94.0, 94.4], [point.lap_time_seconds for point in run.points])

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
        result = select_long_runs(2, Laps(pandas.DataFrame(data)), "SOFT")
        self.assertEqual(1, len(result))
        self.assertEqual([[4.0, 5.0, 6.0, 7.0]], [[point.tyre_age for point in run.points] for run in result])

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
        result = select_long_runs(2, Laps(pandas.DataFrame(data)), "SOFT")
        self.assertEqual([[1.0, 2.0], [7.0, 8.0, 9.0]],
                         [[point.tyre_age for point in run.points] for run in result])

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
        result = select_long_runs(2, Laps(pandas.DataFrame(data)), "SOFT")
        # Stint 1 is close to the fastest clean lap from stint 2. The four-lap
        # second stint remains due to the automatic long-run rule.
        self.assertEqual([[1.0, 2.0, 3.0, 4.0]],
                         [[point.tyre_age for point in run.points] for run in result])

    def test_short_run_without_external_reference_is_retained(self):
        data = {
            "DriverNumber": ["1", "1"], "Driver": ["Max", "Max"],
            "Stint": [1, 1], "Team": ["Red Bull", "Red Bull"],
            "LapNumber": [7, 8], "LapTime": pandas.to_timedelta(["95s", "95.3s"]),
            "TyreLife": [3, 4], "Compound": ["SOFT", "SOFT"],
        }
        result = select_long_runs(2, Laps(pandas.DataFrame(data)), "SOFT")
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
        result = select_long_runs(2, Laps(pandas.DataFrame(data)), "SOFT")
        self.assertEqual([[1, 2], [5, 6, 7]],
                         [[point.lap_number for point in run.points] for run in result])

    def test_inaccurate_lap_is_excluded(self):
        frame = pandas.DataFrame({
            "DriverNumber": ["1"] * 5, "Driver": ["Max"] * 5, "Team": ["Red Bull"] * 5,
            "Compound": ["SOFT"] * 5, "Stint": [1] * 5, "LapNumber": list(range(1, 6)),
            "TyreLife": list(range(1, 6)),
            "LapTime": pandas.to_timedelta(["94s", "94.1s", "94.2s", "94.3s", "94.4s"]),
            "IsAccurate": [True, True, False, True, True],
        })
        runs = select_long_runs(2, Laps(frame), "SOFT")
        self.assertEqual([[1, 2], [4, 5]],
                         [[point.lap_number for point in run.points] for run in runs])

    def test_nonfinite_tyre_age_is_kept_but_not_drawn(self):
        frame = pandas.DataFrame({
            "DriverNumber": ["1", "1"], "Driver": ["Max", "Max"], "Team": ["Red Bull"] * 2,
            "Compound": ["SOFT"] * 2, "Stint": [1, 1], "LapNumber": [1, 2],
            "TyreLife": [1, float("inf")],
            "LapTime": pandas.to_timedelta(["94s", "94.1s"]),
        })
        runs = select_long_runs(2, Laps(frame), "SOFT")
        self.assertEqual([1.0, None], [point.tyre_age for point in runs[0].points])

    def test_missing_lap_number_column_selects_nothing(self):
        frame = pandas.DataFrame({
            "DriverNumber": ["1"], "Driver": ["Max"], "Team": ["Red Bull"],
            "Stint": [1], "LapTime": pandas.to_timedelta(["94s"]),
            "TyreLife": [1], "Compound": ["SOFT"],
        })
        self.assertEqual([], select_long_runs(2, Laps(frame), "SOFT"))

    def test_criteria_can_raise_minimum_phase_length(self):
        data = {
            "DriverNumber": ["1"] * 3, "Driver": ["Max"] * 3,
            "Stint": [1] * 3, "Team": ["Red Bull"] * 3,
            "LapNumber": [1, 2, 3], "TyreLife": [1, 2, 3],
            "LapTime": pandas.to_timedelta(["94s", "94.1s", "94.2s"]),
            "Compound": ["SOFT"] * 3,
        }
        result = select_long_runs(3, Laps(pandas.DataFrame(data)), "SOFT", LongRunCriteria())
        self.assertEqual(1, len(result))

    def test_dropped_opening_interval_renumbers_retained_runs(self):
        # The lone opening lap behind the traffic lap fails the minimum run
        # length; the retained run is numbered 1 within its stint.
        frame = pandas.DataFrame({
            "DriverNumber": ["1"] * 5, "Driver": ["Max"] * 5, "Team": ["Red Bull"] * 5,
            "Compound": ["SOFT"] * 5, "Stint": [1] * 5, "LapNumber": list(range(1, 6)),
            "TyreLife": list(range(1, 6)),
            "LapTime": pandas.to_timedelta(["94s", "110s", "94.2s", "94.4s", "94.6s"]),
        })
        runs = select_long_runs(2, Laps(frame), "SOFT")
        self.assertEqual([1], [run.phase_index for run in runs])
        self.assertEqual([[3, 4, 5]],
                         [[point.lap_number for point in run.points] for run in runs])

    def test_phases_with_undefined_stint_match_their_stint(self):
        # NaN stint ids now compare as the same stint: the later run across
        # the traffic lap can exclude the short fast opening run as a
        # qualifying sim.
        frame = pandas.DataFrame({
            "DriverNumber": ["1"] * 6, "Driver": ["Max"] * 6, "Team": ["Red Bull"] * 6,
            "Compound": ["SOFT"] * 6, "Stint": [float("nan")] * 6,
            "LapNumber": list(range(1, 7)), "TyreLife": list(range(1, 7)),
            "LapTime": pandas.to_timedelta(["89s", "89.2s", "110s", "95s", "95.2s", "95.4s"]),
        })
        runs = select_long_runs(2, Laps(frame), "SOFT")
        self.assertEqual([None], [run.stint_id for run in runs])
        self.assertEqual([[4, 5, 6]], [[point.lap_number for point in run.points] for run in runs])

    def test_undefined_stint_run_is_not_its_own_external_reference(self):
        # A lone NaN-stint phase must not see its own clean lap times as an
        # external reference; without other stints it is retained untouched.
        frame = pandas.DataFrame({
            "DriverNumber": ["1", "1"], "Driver": ["Max", "Max"],
            "Team": ["Red Bull", "Red Bull"], "Compound": ["SOFT", "SOFT"],
            "Stint": [float("nan")] * 2,
            "LapNumber": [1, 2], "TyreLife": [1, 2],
            "LapTime": pandas.to_timedelta(["94s", "94.1s"]),
        })
        runs = select_long_runs(2, Laps(frame), "SOFT")
        self.assertEqual(1, len(runs))
        self.assertEqual(None, runs[0].stint_id)
        self.assertEqual([1, 2], [point.lap_number for point in runs[0].points])

    def test_interactive_runs_keep_team_color_and_camera_dash(self):
        runs = [
            LongRun(Driver(1, "Max", "Shared Team"), 1, 1, "SOFT",
                    tuple(LongRunPoint(age, age, time) for age, time in [(1, 94.0), (2, 94.2)])),
            LongRun(Driver(1, "Max", "Shared Team"), 2, 1, "SOFT",
                    tuple(LongRunPoint(age, age, time) for age, time in [(5, 95.0), (6, 95.2)])),
            LongRun(Driver(22, "Yuki", "Shared Team"), 3, 1, "SOFT",
                    tuple(LongRunPoint(age, age, time) for age, time in [(1, 95.5), (2, 95.7)])),
        ]
        session = SimpleNamespace(
            event=SimpleNamespace(year=2025),
            results=pandas.DataFrame(),
            laps=pandas.DataFrame(),
        )

        with patch("f1_explorer.visualizations.long_runs.fastf1.plotting.get_team_color", return_value="#123456"):
            figure = _make_interactive_long_run_figure(session, "SOFT", runs)

        self.assertEqual(["#123456"] * 3, [trace.line.color for trace in figure.data])
        self.assertEqual(["solid", "solid", "dash"], [trace.line.dash for trace in figure.data])
        self.assertEqual("Tyre age [laps]", figure.layout.xaxis.title.text)
        self.assertEqual([5, 6], list(figure.data[1].x))

        fallback_session = SimpleNamespace(results=pandas.DataFrame(), laps=pandas.DataFrame())
        fallback = _make_interactive_long_run_figure(
            fallback_session, "SOFT",
            [LongRun(Driver(99, "Unknown", ""), 1, 1, "SOFT",
                     (LongRunPoint(1, 1, 96.0), LongRunPoint(2, 2, 96.2)))],
        )
        self.assertEqual("gray", fallback.data[0].line.color)
        self.assertEqual("solid", fallback.data[0].line.dash)

    def test_matplotlib_skips_points_without_tyre_age(self):
        frame = pandas.DataFrame({
            "DriverNumber": ["1"] * 4, "Driver": ["Max"] * 4, "Team": ["Red Bull"] * 4,
            "Compound": ["SOFT"] * 4, "Stint": [1] * 4, "LapNumber": list(range(1, 5)),
            "TyreLife": [1, 2, None, 4],
            "LapTime": pandas.to_timedelta([90, 90.2, 90.4, 90.6], unit="s"),
        })
        session = SimpleNamespace(event=SimpleNamespace(year=2026), laps=frame)
        with (
            patch("f1_explorer.visualizations.long_runs.fastf1.plotting.setup_mpl"),
            patch("f1_explorer.visualizations.long_runs.fastf1.plotting.get_team_color", return_value="#123456"),
            patch("f1_explorer.visualizations.long_runs.driver_linestyle", return_value="solid"),
            patch("f1_explorer.visualizations.long_runs.save_matplotlib") as save,
        ):
            plot_by_tyre_age_and_tyre(session, MagicMock(), output_dir="plots")
        figure = save.call_args[0][0]
        lines = figure.axes[0].get_lines()
        self.assertEqual(1, len(lines))
        self.assertEqual([1.0, 2.0, 4.0], list(lines[0].get_xdata()))
        self.assertEqual([90.0, 90.2, 90.6], list(lines[0].get_ydata()))
        self.assertIn("displayed 3", lines[0].get_label())

    def test_real_laps_survive_duplicate_missing_and_used_tyre_ages(self):
        frame = pandas.DataFrame({
            "DriverNumber": ["1"] * 8, "Driver": ["Max"] * 8,
            "Team": ["Red Bull"] * 8, "Compound": ["SOFT"] * 8,
            "Stint": [1] * 4 + [2] * 4, "LapNumber": list(range(10, 18)),
            "TyreLife": [5, 5, None, 8, 5, 6, 7, 8],
            "LapTime": pandas.to_timedelta([90, 91, 92, 93] * 2, unit="s"),
        })
        before = frame.copy(deep=True)
        runs = select_long_runs(2, Laps(frame), "SOFT")
        self.assertEqual([1, 2], [run.stint_id for run in runs])
        self.assertEqual([1, 1], [run.phase_index for run in runs])
        self.assertEqual(list(range(10, 18)),
                         [point.lap_number for run in runs for point in run.points])
        self.assertEqual([5, 5, None, 8], [point.tyre_age for point in runs[0].points])
        session = SimpleNamespace(results=pandas.DataFrame(), laps=pandas.DataFrame())
        figure = _make_interactive_long_run_figure(session, "SOFT", runs)
        self.assertEqual([5, 5, None, 8], list(figure.data[0].x))
        self.assertIsNone(figure.data[0].y[2])
        self.assertFalse(figure.data[0].connectgaps)
        self.assertIn("selected 4, displayed 3", figure.data[0].name)
        self.assertEqual(10, figure.data[0].customdata[0][2])
        pandas.testing.assert_frame_equal(frame, before)

    def test_excluded_lap_splits_phases_with_original_numbers(self):
        frame = pandas.DataFrame({
            "DriverNumber": ["1"] * 9, "Driver": ["Max"] * 9,
            "Team": ["Red Bull"] * 9, "Compound": ["SOFT"] * 9,
            "Stint": [1] * 9, "LapNumber": list(range(20, 29)),
            "TyreLife": list(range(5, 14)),
            "LapTime": pandas.to_timedelta([90] * 9, unit="s"),
            "Deleted": [False] * 4 + [True] + [False] * 4,
        })
        runs = select_long_runs(2, Laps(frame), "SOFT")
        self.assertEqual([1, 2], [run.phase_index for run in runs])
        self.assertEqual([[20, 21, 22, 23], [25, 26, 27, 28]],
                         [[p.lap_number for p in run.points] for run in runs])


if __name__ == '__main__':
    unittest.main()
