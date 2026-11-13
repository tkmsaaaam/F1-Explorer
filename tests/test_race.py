import unittest
from contextlib import ExitStack
import math
import tempfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import matplotlib.pyplot as plt
import pandas
from fastf1.core import Laps

from f1_explorer.visualizations.domain.driver import Driver
from f1_explorer.visualizations.domain.driver_laps import DriverLaps
from f1_explorer.visualizations.domain.lap import Lap
from f1_explorer.visualizations.domain.tyre import Tyre
from f1_explorer.visualizations.race import (
    execute,
    gap_to_ahead_graph,
    gap_to_ahead_table,
    gap_to_top_graph,
    gap_to_top_table,
    laptime,
    make_driver_laps_set,
    positions,
    tyres,
    write_messages,
    write_track_status,
)
from f1_explorer.visualizations.race_metrics import (
    gap_observations,
    lap_times_by_position,
)


class Race(unittest.TestCase):
    @staticmethod
    def _driver_laps(number, name, positions_and_seconds):
        laps = {
            lap_number: Lap(80, pandas.to_timedelta(timestamp, unit="s"), position,
                            tyre=Tyre("Soft", True))
            for lap_number, (position, timestamp) in positions_and_seconds.items()
        }
        return DriverLaps(Driver(number, name, f"Team {name}"), laps)

    def test_gap_tables_use_actual_lap_numbers_and_metric_values(self):
        leader = self._driver_laps(1, "LEADER", {1: (1, 80), 2: (2, 162), 3: (2, 241), 4: (1, 320)})
        runner = self._driver_laps(2, "RUNNER", {1: (2, 82), 2: (1, 160), 3: (1, 240), 4: (2, 323)})
        dnf = self._driver_laps(3, "DNF", {1: (3, 84), 2: (3, 164), 3: (3, 244)})
        hole = self._driver_laps(4, "HOLE", {1: (4, 88), 3: (4, 248)})
        late_start = self._driver_laps(6, "LATE", {3: (5, 250), 4: (5, 330)})
        empty = DriverLaps(Driver(5, "EMPTY", "Team EMPTY"), {})
        lap_logs = [leader, runner, dnf, hole, late_start, empty]
        session = SimpleNamespace(laps=MagicMock())
        with patch("f1_explorer.visualizations.race.save_plotly") as save:
            gap_to_ahead_table(MagicMock(), "ahead.png", lap_logs)
            ahead_fig = save.call_args.args[0]
            gap_to_top_table(MagicMock(), "top.png", lap_logs, session)
            top_fig = save.call_args.args[0]

        ahead_cells = ahead_fig.data[0].cells
        top_cells = top_fig.data[0].cells
        self.assertEqual([1, 2, 3, 4], list(ahead_cells.values[0]))
        self.assertEqual([1, 2, 3, 4], list(top_cells.values[0]))
        headers = list(ahead_fig.data[0].header.values)
        ahead_by_driver = {name: list(values) for name, values in zip(headers[1:], ahead_cells.values[1:])}
        headers = list(top_fig.data[0].header.values)
        top_by_driver = {name: list(values) for name, values in zip(headers[1:], top_cells.values[1:])}
        self.assertEqual([2.0, "---", "---", 3.0], ahead_by_driver["RUNNER"])
        self.assertEqual([2.0, 2.0, 3.0, "---"], ahead_by_driver["DNF"])
        self.assertEqual(["---", "---", "---", "---"], ahead_by_driver["EMPTY"])
        self.assertEqual([4.0, "---", 4.0, "---"], ahead_by_driver["HOLE"])
        self.assertEqual(["---", "---", 2.0, "---"], ahead_by_driver["LATE"])
        self.assertEqual(["---", 2.0, 1.0, "---"], ahead_by_driver["LEADER"])
        self.assertEqual([0.0, 2.0, 1.0, 0.0], top_by_driver["LEADER"])
        self.assertEqual([2.0, 0.0, 0.0, 3.0], top_by_driver["RUNNER"])
        self.assertEqual([4.0, 4.0, 4.0, "---"], top_by_driver["DNF"])
        self.assertEqual("gold", top_cells.fill.color[1][0])
        ahead_colors = dict(zip(ahead_fig.data[0].header.values[1:], ahead_cells.fill.color[1:]))
        top_colors = dict(zip(top_fig.data[0].header.values[1:], top_cells.fill.color[1:]))
        self.assertEqual("#9966ff", ahead_colors["RUNNER"][0])
        self.assertEqual("#ffffff", ahead_colors["RUNNER"][3])
        self.assertEqual("#e95464", top_colors["HOLE"][0])

        # The report's evidence table consumes layout.meta.gapEvidence; pin
        # the race.py → report.py contract on real table output.
        ahead_evidence = ahead_fig.layout.meta["gapEvidence"]
        self.assertIn({"driver": "1", "lap": 1, "comparison": None, "reason": "no_preceding_position"},
                      ahead_evidence)
        self.assertIn({"driver": "2", "lap": 1, "comparison": 1, "reason": "valid"},
                      ahead_evidence)
        top_evidence = top_fig.layout.meta["gapEvidence"]
        self.assertIn({"driver": "1", "lap": 1, "comparison": 1, "reason": "valid"}, top_evidence)

        for fig in (ahead_fig, top_fig):
            for column in fig.data[0].cells.values:
                self.assertEqual(4, len(column))
            for column in fig.data[0].cells.fill.color:
                self.assertEqual(4, len(column))
        for fig, values in ((ahead_fig, ahead_by_driver), (top_fig, top_by_driver)):
            colors = dict(zip(fig.data[0].header.values[1:], fig.data[0].cells.fill.color[1:]))
            for name, column in values.items():
                for index, value in enumerate(column):
                    if value == "---":
                        self.assertEqual("#ffffff", colors[name][index])

        session.event = SimpleNamespace(year=2026)
        nonempty = [driver for driver in lap_logs if driver.laps]
        with (
            patch("f1_explorer.visualizations.race.fastf1.plotting.get_team_color", return_value="#123456"),
            patch("f1_explorer.visualizations.race.save_plotly") as save,
        ):
            gap_to_ahead_graph(MagicMock(), "output", "ahead", session, None, nonempty)
            ahead_graph = save.call_args.args[0]
            gap_to_top_graph(MagicMock(), "output", "top", session, None, nonempty)
            top_graph = save.call_args.args[0]
        for graph, table in ((ahead_graph, ahead_by_driver), (top_graph, top_by_driver)):
            for trace in graph.data:
                for lap, value in zip(trace.x, trace.y):
                    self.assertEqual("---" if value is None else value, table[trace.name][lap - 1])

    def test_gap_tables_handle_only_empty_drivers(self):
        empty = DriverLaps(Driver(1, "EMPTY", "Team"), {})
        with patch("f1_explorer.visualizations.race.save_plotly") as save:
            gap_to_ahead_table(MagicMock(), "ahead.png", [empty])
            ahead = save.call_args.args[0]
            gap_to_top_table(MagicMock(), "top.png", [empty], SimpleNamespace(laps=None))
            top = save.call_args.args[0]
        for fig in (ahead, top):
            self.assertEqual(["Lap", "EMPTY"], list(fig.data[0].header.values))
            self.assertEqual([[], []], [list(column) for column in fig.data[0].cells.values])

    def test_gap_tables_handle_no_drivers(self):
        with patch("f1_explorer.visualizations.race.save_plotly") as save:
            gap_to_ahead_table(MagicMock(), "ahead.png", [])
            ahead = save.call_args.args[0]
            gap_to_top_table(MagicMock(), "top.png", [], SimpleNamespace(laps=MagicMock()))
            top = save.call_args.args[0]

        self.assertEqual(["Lap"], list(ahead.data[0].header.values))
        self.assertEqual([[]], [list(ahead.data[0].cells.values[0])])
        self.assertEqual(["Lap"], list(top.data[0].header.values))
        self.assertEqual([[]], [list(top.data[0].cells.values[0])])

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
            "Time": pandas.to_timedelta(["83s", "166s", "84s"]),
            "LapTime": pandas.to_timedelta(["83.456s", "82.789s", "83.000s"]),
        }
        laps = Laps(pandas.DataFrame(data))
        result = make_driver_laps_set(laps)
        self.assertEqual(2, len(result))
        # Make iteration order deterministic for both set and list return types
        result_sorted = sorted(list(result), key=lambda dl: dl.get_driver().get_number(), reverse=True)
        self.assertEqual(2, len(result_sorted[1].get_laps()))
        self.assertEqual(1, result_sorted[1].get_driver().get_number())
        self.assertEqual('Max', result_sorted[1].get_driver().get_name())
        self.assertEqual('Red Bull', result_sorted[1].get_driver().get_team_name())
        self.assertEqual(83.456, result_sorted[1].get_laps()[1].get_time())
        self.assertEqual(timedelta(seconds=83), result_sorted[1].get_laps()[1].get_at())
        self.assertEqual(1, result_sorted[1].get_laps()[1].get_position())
        self.assertEqual(False, result_sorted[1].get_laps()[1].get_pit_out())
        self.assertEqual(True, result_sorted[1].get_laps()[1].get_tyre().get_new())
        self.assertEqual('Soft', result_sorted[1].get_laps()[1].get_tyre().get_compound())
        self.assertEqual(82.789, result_sorted[1].get_laps()[2].get_time())
        self.assertEqual(timedelta(seconds=166), result_sorted[1].get_laps()[2].get_at())
        self.assertEqual(1, result_sorted[1].get_laps()[2].get_position())
        self.assertEqual(False, result_sorted[1].get_laps()[2].get_pit_out())
        self.assertEqual(True, result_sorted[1].get_laps()[2].get_tyre().get_new())
        self.assertEqual('Soft', result_sorted[1].get_laps()[2].get_tyre().get_compound())

        self.assertEqual(1, len(result_sorted[0].get_laps()))
        self.assertEqual(16, result_sorted[0].get_driver().get_number())
        self.assertEqual('Lec', result_sorted[0].get_driver().get_name())
        self.assertEqual('Ferrari', result_sorted[0].get_driver().get_team_name())
        self.assertEqual(83.000, result_sorted[0].get_laps()[1].get_time())
        self.assertEqual(timedelta(seconds=84), result_sorted[0].get_laps()[1].get_at())
        self.assertEqual(2, result_sorted[0].get_laps()[1].get_position())
        self.assertEqual(False, result_sorted[0].get_laps()[1].get_pit_out())
        self.assertEqual(True, result_sorted[0].get_laps()[1].get_tyre().get_new())
        self.assertEqual('Soft', result_sorted[0].get_laps()[1].get_tyre().get_compound())

    def test_make_lap_log_marks_only_laps_with_pit_out_time(self):
        data = {
            "DriverNumber": ["1"], "Driver": ["Max"], "Stint": [2], "Team": ["Red Bull"],
            "LapNumber": [10], "Position": [1], "Compound": ["Soft"], "FreshTyre": [True],
            "PitOutTime": pandas.to_timedelta(["12s"]),
            "Time": pandas.to_timedelta(["720s"]),
            "LapTime": pandas.to_timedelta(["90s"]),
        }
        result = make_driver_laps_set(Laps(pandas.DataFrame(data)))

        self.assertTrue(result[0].get_laps()[10].get_pit_out())

    def test_make_lap_log_keeps_incomplete_rows_with_none_values(self):
        data = {
            "DriverNumber": ["1", "1", "16"],
            "Driver": ["Max", "Max", "Lec"],
            "Stint": [1, 1, 1],
            "Team": ["Red Bull", "Red Bull", "Ferrari"],
            "LapNumber": [1, 2, 1],
            "Position": [1, float("nan"), float("nan")],
            "Compound": ["Soft", "Soft", "Soft"],
            "FreshTyre": [True, True, True],
            "PitOutTime": pandas.to_timedelta([None, None, None]),
            "Time": pandas.to_timedelta(["83s", "166s", "84s"]),
            "LapTime": pandas.to_timedelta(["83s", "83s", "84s"]),
        }

        result = make_driver_laps_set(Laps(pandas.DataFrame(data)))

        self.assertEqual([1, 16], [driver_laps.driver.number for driver_laps in result])
        self.assertEqual([1, 2], list(result[0].laps))
        self.assertEqual(1, result[0].laps[1].get_position())
        # Missing positions stay missing: no zero rank is fabricated.
        self.assertIsNone(result[0].laps[2].get_position())
        self.assertEqual([1], list(result[1].laps))
        self.assertIsNone(result[1].laps[1].get_position())

    def test_make_lap_log_keeps_lap_missing_lap_time_only(self):
        """A lap missing only its LapTime keeps position and gap values."""
        laps = Laps(pandas.DataFrame({
            "DriverNumber": ["1", "2"],
            "Driver": ["Max", "Lec"],
            "Stint": [1, 1],
            "Team": ["Red Bull", "Ferrari"],
            "LapNumber": [1, 1],
            "Position": [1, 2],
            "Compound": ["Soft", "Soft"],
            "FreshTyre": [True, True],
            "PitOutTime": pandas.to_datetime(["", ""]),
            "Time": pandas.to_timedelta(["83s", "84s"]),
            "LapTime": pandas.to_timedelta([pandas.NaT, "83s"]),
        }))
        result = make_driver_laps_set(laps)
        self.assertIsNone(result[0].laps[1].get_time())
        self.assertEqual(timedelta(seconds=83), result[0].laps[1].get_at())
        self.assertEqual(1, result[0].laps[1].get_position())

        positions = lap_times_by_position(result)
        self.assertEqual({1: 83.0, 2: 84.0}, {p: t.total_seconds() for p, t in positions[1].items()})
        observation = gap_observations(result[1], result, ahead=True)[0]
        self.assertEqual((1.0, 1, None),
                         (observation.seconds, observation.comparison_number, observation.reason))

    def test_make_lap_log_keeps_lap_missing_session_time_only(self):
        """A lap missing only its session-elapsed time keeps its position."""
        laps = Laps(pandas.DataFrame({
            "DriverNumber": ["1", "2"],
            "Driver": ["Max", "Lec"],
            "Stint": [1, 1],
            "Team": ["Red Bull", "Ferrari"],
            "LapNumber": [1, 1],
            "Position": [1, 2],
            "Compound": ["Soft", "Soft"],
            "FreshTyre": [True, True],
            "PitOutTime": pandas.to_datetime(["", ""]),
            "Time": pandas.to_timedelta(["83s", pandas.NaT]),
            "LapTime": pandas.to_timedelta(["83s", "83s"]),
        }))
        result = make_driver_laps_set(laps)
        self.assertEqual(2, result[1].laps[1].get_position())
        self.assertIsNone(result[1].laps[1].get_at())
        self.assertEqual({1: 83.0}, {k: t.total_seconds() for k, t in lap_times_by_position(result)[1].items()})

        # Without a session-elapsed time the lap provides no gap value,
        # and none is fabricated in its place.
        self.assertEqual("missing_own_record",
                         gap_observations(result[1], result, ahead=True)[0].reason)

    def test_make_lap_log_rejects_unrankable_positions(self):
        laps = Laps(pandas.DataFrame({
            "DriverNumber": ["1", "1", "1"],
            "Driver": ["Max", "Max", "Max"],
            "Stint": [1, 1, 1],
            "Team": ["Red Bull", "Red Bull", "Red Bull"],
            "LapNumber": [1, 2, 3],
            "Position": [0, 1.0, float("inf")],
            "Compound": ["Soft", "Soft", "Soft"],
            "FreshTyre": [True, True, True],
            "PitOutTime": pandas.to_datetime(["", "", ""]),
            "Time": pandas.to_timedelta(["83s", "166s", "249s"]),
            "LapTime": pandas.to_timedelta(["83s", "83s", "83s"]),
        }))
        result = make_driver_laps_set(laps)
        self.assertIsNone(result[0].laps[1].get_position())
        self.assertEqual(1, result[0].laps[2].get_position())
        self.assertIsNone(result[0].laps[3].get_position())
        reasons = [item.reason for item in gap_observations(result[0], result, ahead=True)]
        self.assertEqual(["missing_own_record", "no_preceding_position", "missing_own_record"], reasons)

    def test_laptime_graph_keeps_original_complete_lap_target(self):
        """R-07 keeps plotting only fully recorded laps, even when the
        adapter now retains laps that miss only a non-identifier value."""
        fixture_laps = pandas.DataFrame({
            "DriverNumber": ["1", "1", "1"],
            "Driver": ["Max", "Max", "Max"],
            "Stint": [1, 1, 1],
            "Team": ["Red Bull", "Red Bull", "Red Bull"],
            "LapNumber": [1, 2, 3],
            "Position": [1.0, 1.0, 1.0],
            "Compound": ["Soft", "Soft", "Soft"],
            "FreshTyre": [True, True, True],
            "PitOutTime": pandas.to_datetime(["", "", ""]),
            "Time": pandas.to_timedelta(["83s", "166s", pandas.NaT]),
            "LapTime": pandas.to_timedelta(["83s", "83s", "83s"]),
        })
        lap_logs = make_driver_laps_set(Laps(fixture_laps))
        self.assertEqual(3, len(lap_logs[0].get_laps()))

        session = SimpleNamespace(
            event=SimpleNamespace(year=2026),
            laps=Laps(fixture_laps.assign(IsAccurate=[True] * 3, Deleted=[False] * 3, TrackStatus=["1"] * 3)),
        )
        with (
            patch("f1_explorer.visualizations.race.save_matplotlib") as save,
            patch("f1_explorer.visualizations.race.current_report", return_value=MagicMock()),
            patch("f1_explorer.visualizations.race.fastf1.plotting.get_team_color", return_value="#123456"),
        ):
            laptime(MagicMock(), "output", "laptime_graph", session, None, lap_logs)

        figure = save.call_args.args[0]
        lines = figure.axes[0].get_lines()
        self.assertEqual([[1, 2]], [list(line.get_xdata()) for line in lines])
        self.assertEqual([[83.0, 83.0]], [list(line.get_ydata()) for line in lines])

    def test_positions_graph_keeps_missing_position_out_of_the_line(self):
        lap_logs = [
            DriverLaps(Driver(1, "MAX", "Red Bull"), {
                1: Lap(80, timedelta(seconds=83), 1, tyre=Tyre("Soft", True)),
                2: Lap(80, timedelta(seconds=166), None, tyre=Tyre("Soft", True)),
            }),
        ]
        session = SimpleNamespace(event=SimpleNamespace(year=2026))
        with (
            patch("f1_explorer.visualizations.race.save_matplotlib") as save,
            patch("f1_explorer.visualizations.race.fastf1.plotting.get_team_color", return_value="#123456"),
        ):
            positions(MagicMock(), "output", session, lap_logs)

        line = save.call_args.args[0].axes[0].get_lines()[0]
        points = line.get_xydata()
        self.assertEqual([1, 2], [float(point[0]) for point in points])
        self.assertEqual(1.0, points[0][1])
        self.assertTrue(math.isnan(points[1][1]))

    def test_positions_graph_hides_driver_without_any_recorded_position(self):
        """A driver whose laps all miss the position gets no ghost line or legend entry."""
        lap_logs = [
            DriverLaps(Driver(1, "MAX", "Red Bull"), {
                1: Lap(80, timedelta(seconds=83), None, tyre=Tyre("Soft", True)),
                2: Lap(80, timedelta(seconds=166), None, tyre=Tyre("Soft", True)),
            }),
        ]
        session = SimpleNamespace(event=SimpleNamespace(year=2026))
        with (
            patch("f1_explorer.visualizations.race.save_matplotlib") as save,
            patch("f1_explorer.visualizations.race.fastf1.plotting.get_team_color", return_value="#123456"),
        ):
            positions(MagicMock(), "output", session, lap_logs)

        self.assertEqual([], list(save.call_args.args[0].axes[0].get_lines()))

    def test_laptime_graph_hides_driver_without_any_complete_lap(self):
        """A driver retained with only partial laps gets no ghost line or legend entry."""
        fixture_laps = pandas.DataFrame({
            "DriverNumber": ["1", "1"],
            "Driver": ["Max", "Max"],
            "Stint": [1, 1],
            "Team": ["Red Bull", "Red Bull"],
            "LapNumber": [1, 2],
            "Position": [None, None],
            "Compound": ["Soft", "Soft"],
            "FreshTyre": [True, True],
            "PitOutTime": pandas.to_datetime(["", ""]),
            "Time": pandas.to_timedelta(["83s", "166s"]),
            "LapTime": pandas.to_timedelta(["83s", "83s"]),
        })
        lap_logs = make_driver_laps_set(Laps(fixture_laps))
        self.assertEqual(2, len(lap_logs[0].get_laps()))

        session = SimpleNamespace(
            event=SimpleNamespace(year=2026),
            laps=Laps(fixture_laps.assign(IsAccurate=[True] * 2, Deleted=[False] * 2, TrackStatus=["1"] * 2)),
        )
        with (
            patch("f1_explorer.visualizations.race.save_matplotlib") as save,
            patch("f1_explorer.visualizations.race.current_report", return_value=MagicMock()),
        ):
            laptime(MagicMock(), "output", "laptime_graph", session, None, lap_logs)

        self.assertEqual([], list(save.call_args.args[0].axes[0].get_lines()))

    def test_gap_graphs_keep_legend_for_driver_without_any_gaps(self):
        """Like empty drivers, a driver whose every lap misses position or
        time still gets a classification-order legend trace; its series
        carries null gaps instead of fabricated zeros.  The committed
        classification-order contract keeps empty driver traces, and this
        new no-gap case follows the same rule."""
        lap_logs = [
            DriverLaps(Driver(1, "FIRST", "Team A"), {
                1: Lap(80, timedelta(seconds=83), None, tyre=Tyre("Soft", True)),
                2: Lap(80, timedelta(seconds=166), None, tyre=Tyre("Soft", True)),
            }),
        ]
        session = SimpleNamespace(event=SimpleNamespace(year=2026), laps=MagicMock())
        with (
            patch("f1_explorer.visualizations.race.fastf1.plotting.get_team_color", return_value="#123456"),
            patch("f1_explorer.visualizations.race.save_plotly") as save,
        ):
            gap_to_ahead_graph(MagicMock(), "output", "ahead", session, None, lap_logs)
            ahead = save.call_args.args[0]
            gap_to_top_graph(MagicMock(), "output", "top", session, None, lap_logs)
            top = save.call_args.args[0]

        self.assertEqual(["FIRST"], [trace.name for trace in ahead.data])
        self.assertEqual([None, None], list(ahead.data[0].y))
        self.assertEqual(["FIRST"], [trace.name for trace in top.data])
        self.assertEqual([None, None], list(top.data[0].y))

    def test_tyre_chart_marks_stint_changes_and_labels_age_and_condition(self):
        laps = Laps(pandas.DataFrame({
            "DriverNumber": ["1"] * 5,
            "LapNumber": [1, 2, 3, 4, 5],
            "Position": [1] * 5,
            "Compound": ["SOFT"] * 5,
            "Stint": [1, 1, 1, 2, 2],
            "TyreLife": [1, 2, 3, 5, 6],
            "FreshTyre": [True, True, True, False, False],
        }))

        with patch("f1_explorer.visualizations.race.save_matplotlib") as save:
            tyres(MagicMock(), "test-output/tyres.png", laps)

        figure = save.call_args.args[0]
        axis = figure.axes[0]
        self.assertEqual([text.get_text() for text in axis.texts], ["1 N", "2", "3", "5 U", "6"])
        self.assertEqual(5, len(axis.patches))
        self.assertEqual(2, len(axis.collections))
        plt.close(figure)

    def test_gap_ahead_graph_is_plotly_and_sorted_by_result_position(self):
        first_lap = MagicMock()
        first_lap.get_position.return_value = 1
        second_lap = MagicMock()
        second_lap.get_position.return_value = 2
        lap_logs = [
            DriverLaps(Driver(2, "SECOND", "Team B"), {1: second_lap}),
            DriverLaps(Driver(1, "FIRST", "Team A"), {1: first_lap}),
        ]
        session = SimpleNamespace(
            event=SimpleNamespace(year=2026),
            results=pandas.DataFrame({"DriverNumber": ["1", "2"], "Position": [5, 1]}),
        )

        observations = [SimpleNamespace(lap_number=n, seconds=v, comparison_number=1, reason=None)
                        for n, v in [(1, None), (2, 1.25), (3, 3.25)]]
        with (
            patch("f1_explorer.visualizations.race.gap_observations_all",
                  return_value={1: observations, 2: observations}),
            patch("f1_explorer.visualizations.race.fastf1.plotting.get_team_color", return_value="#123456"),
            patch("f1_explorer.visualizations.race.save_plotly") as save,
        ):
            gap_to_ahead_graph(MagicMock(), "output", "gap_ahead_graph", session, 15, lap_logs)

        self.assertEqual(2, save.call_count)
        default_figure = save.call_args_list[0].args[0]
        ranged_figure = save.call_args_list[1].args[0]
        self.assertEqual(["SECOND", "FIRST"], [trace.name for trace in default_figure.data])
        self.assertEqual((3.29, 1.21), default_figure.layout.yaxis.range)
        self.assertEqual((15, 0), ranged_figure.layout.yaxis.range)
        self.assertEqual("output/gap_ahead_graph.png", save.call_args_list[0].args[1])

    def test_all_gap_outputs_share_classification_and_fallback_order(self):
        from f1_explorer.visualizations.session_order import driver_order

        # Car 2 retires while second, but is classified fifth. Cars 10/3
        # share a result rank; car 4 has no result and car 9 no timed lap.
        lap_logs = [
            self._driver_laps(2, "DNF", {1: (2, 82)}),
            self._driver_laps(9, "UNTIMED", {}),
            self._driver_laps(4, "NORESULT", {1: (4, 84)}),
            self._driver_laps(3, "TIE3", {1: (3, 83)}),
            self._driver_laps(10, "TIE10", {1: (1, 80)}),
        ]
        for results in (
            pandas.DataFrame({"DriverNumber": ["2", "10", "3", "4"],
                              "Position": [5, 1, 1, float("nan")]}),
            pandas.DataFrame(),
        ):
            with self.subTest(results=results.to_dict()):
                session = SimpleNamespace(
                    event=SimpleNamespace(year=2026), results=results,
                    laps=pandas.DataFrame({"DriverNumber": ["2", "10", "3", "4"],
                                           "LapTime": pandas.to_timedelta([82, 80, 83, 79], unit="s")}),
                )
                expected = (["TIE10", "TIE3", "DNF", "NORESULT", "UNTIMED"]
                            if not results.empty else
                            ["NORESULT", "TIE10", "DNF", "TIE3", "UNTIMED"])
                with (
                    patch("f1_explorer.visualizations.race.fastf1.plotting.get_team_color", return_value="#123456"),
                    patch("f1_explorer.visualizations.race.save_plotly") as save,
                ):
                    gap_to_ahead_table(MagicMock(), "ahead.png", lap_logs, ranks=driver_order(session))
                    gap_to_top_table(MagicMock(), "top.png", lap_logs, session)
                    gap_to_ahead_graph(MagicMock(), "output", "ahead", session, 15, lap_logs)
                    gap_to_top_graph(MagicMock(), "output", "top", session, 30, lap_logs)
                figures = [call.args[0] for call in save.call_args_list]
                for figure in figures[:2]:
                    self.assertEqual(expected, list(figure.data[0].header.values)[1:])
                for figure in figures[2:]:
                    self.assertEqual(expected, [trace.name for trace in figure.data])

    def test_execute_passes_result_ranks_to_ahead_table(self):
        session = SimpleNamespace(
            laps=pandas.DataFrame(),
            results=pandas.DataFrame({"DriverNumber": ["2", "1"], "Position": [1, 5]}),
        )
        functions = ("make_driver_laps_set", "laptime",
                     "gap_to_ahead_table", "gap_to_top_table", "gap_to_ahead_graph", "gap_to_top_graph",
                     "positions", "speed_first_10s", "speed_until_turn1", "tyres",
                     "write_messages", "write_track_status")
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            mocks = {name: stack.enter_context(patch(f"f1_explorer.visualizations.race.{name}"))
                     for name in functions}
            execute(session, MagicMock(), tmp, tmp, None, None, None)
            self.assertEqual({"2": 1, "1": 5}, mocks["gap_to_ahead_table"].call_args.kwargs["ranks"])

    def test_ahead_table_without_ranks_uses_car_number_string_order(self):
        logs = [self._driver_laps(2, "SECOND", {1: (1, 80)}),
                self._driver_laps(10, "TENTH", {1: (2, 82)})]
        with patch("f1_explorer.visualizations.race.save_plotly") as save:
            gap_to_ahead_table(MagicMock(), "ahead.png", logs)
        self.assertEqual(["Lap", "TENTH", "SECOND"], list(save.call_args.args[0].data[0].header.values))

    def test_gap_top_graph_is_plotly_and_keeps_zero_at_top(self):
        lap_logs = [DriverLaps(Driver(1, "FIRST", "Team A"), {1: MagicMock()})]
        session = SimpleNamespace(event=SimpleNamespace(year=2026), laps=MagicMock())

        with (
            patch("f1_explorer.visualizations.race.gap_observations_all",
                  return_value={1: [SimpleNamespace(lap_number=1, seconds=0.0,
                                                    comparison_number=1, reason=None)]}),
            patch("f1_explorer.visualizations.race.fastf1.plotting.get_team_color", return_value="#123456"),
            patch("f1_explorer.visualizations.race.save_plotly") as save,
        ):
            gap_to_top_graph(MagicMock(), "output", "gap_top_graph", session, None, lap_logs)

        save.assert_called_once()
        figure = save.call_args.args[0]
        self.assertEqual("FIRST", figure.data[0].name)
        self.assertEqual((60, 0), figure.layout.yaxis.range)
        self.assertEqual("x unified", figure.layout.hovermode)


class WriteSessionLogs(unittest.TestCase):
    """race.execute() が書き出す race_control.txt / track_status.txt の検査。"""

    @staticmethod
    def _messages_frame(count: int) -> pandas.DataFrame:
        return pandas.DataFrame({
            "Time": pandas.date_range("2026-01-01", periods=count, freq="min"),
            "Lap": list(range(count)),
            "Category": ["Flag"] * count,
            "Flag": [None] * count,
            "Scope": [None] * count,
            "RacingNumber": [None] * count,
            "Message": [f"M{i}" for i in range(count)],
        })

    def test_write_track_status_uses_track_status_and_survives_count_mismatch(self):
        track_status = pandas.DataFrame({
            "Time": pandas.to_datetime(["2026-01-01 00:00:10", "2026-01-01 00:00:02"], format="%Y-%m-%d %H:%M:%S"),
            "Status": ["2", "1"],
            "Message": ["Yellow", "Clear"],
        })
        session = SimpleNamespace(track_status=track_status, race_control_messages=self._messages_frame(5))
        with tempfile.TemporaryDirectory() as tmp:
            logs_path = Path(tmp) / "logs"
            write_track_status(session, str(logs_path))
            content = (logs_path / "track_status.txt").read_text(encoding="utf-8")

        self.assertEqual(
            "2026-01-01 00:00:10 : 2 : Yellow\n"
            "2026-01-01 00:00:02 : 1 : Clear\n",
            content)

        session = SimpleNamespace(
            track_status=pandas.DataFrame({
                "Time": pandas.to_datetime(
                    [f"2026-01-01 00:{i:02d}:00" for i in range(1, 6)], format="%Y-%m-%d %H:%M:%S"),
                "Status": ["1", "2", "4", "5", "1"],
                "Message": ["Clear", "Yellow", "Safety Car", "Red Flag", "AllClear"],
            }),
            race_control_messages=self._messages_frame(1),
        )
        with tempfile.TemporaryDirectory() as tmp:
            logs_path = Path(tmp) / "logs"
            write_track_status(session, str(logs_path))
            content = (logs_path / "track_status.txt").read_text(encoding="utf-8")

        self.assertEqual(
            "2026-01-01 00:05:00 : 1 : AllClear\n"
            "2026-01-01 00:04:00 : 5 : Red Flag\n"
            "2026-01-01 00:03:00 : 4 : Safety Car\n"
            "2026-01-01 00:02:00 : 2 : Yellow\n"
            "2026-01-01 00:01:00 : 1 : Clear\n",
            content)

    def test_write_log_functions_write_empty_files_without_rows(self):
        session = SimpleNamespace(
            track_status=pandas.DataFrame({"Time": [], "Status": [], "Message": []}),
            race_control_messages=pandas.DataFrame({
                "Time": [], "Lap": [], "Category": [], "Flag": [], "Scope": [],
                "RacingNumber": [], "Message": [],
            }),
        )
        with tempfile.TemporaryDirectory() as tmp:
            logs_path = Path(tmp) / "logs"
            write_track_status(session, str(logs_path))
            write_messages(session, str(logs_path))
            self.assertTrue((logs_path / "track_status.txt").is_file())
            self.assertTrue((logs_path / "race_control.txt").is_file())
            self.assertEqual("", (logs_path / "track_status.txt").read_text(encoding="utf-8"))
            self.assertEqual("", (logs_path / "race_control.txt").read_text(encoding="utf-8"))

    def test_write_messages_sorts_by_time_and_keeps_newest_first(self):
        messages = pandas.DataFrame({
            "Time": pandas.to_datetime(
                ["2026-01-01 00:02:00", "2026-01-01 00:01:00", "2026-01-01 00:03:00"],
                format="%Y-%m-%d %H:%M:%S"),
            "Lap": [3, 2, 4],
            "Category": ["Other", "Flag", "Flag"],
            "Flag": [None, "YELLOW", "CLEAR"],
            "Scope": [None, "Track", "Track"],
            "RacingNumber": [None, None, None],
            "Message": ["FIRST", "SECOND", "THIRD"],
        })
        session = SimpleNamespace(race_control_messages=messages)
        with tempfile.TemporaryDirectory() as tmp:
            logs_path = Path(tmp) / "logs"
            write_messages(session, str(logs_path))
            content = (logs_path / "race_control.txt").read_text(encoding="utf-8")

        self.assertEqual(
            "2026-01-01 00:03:00 : 4 : Flag : CLEAR : Track : None : THIRD\n"
            "2026-01-01 00:02:00 : 3 : Other : None : None : None : FIRST\n"
            "2026-01-01 00:01:00 : 2 : Flag : YELLOW : Track : None : SECOND\n",
            content)


if __name__ == '__main__':
    unittest.main()
