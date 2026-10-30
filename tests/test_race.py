import unittest
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
    gap_to_ahead_graph,
    gap_to_ahead_table,
    gap_to_top_graph,
    gap_to_top_table,
    make_driver_laps_set,
    make_lap_start_by_position_by_number,
    make_top_time_map,
    tyres,
)
from f1_explorer.visualizations.race_metrics import lap_times_by_position, top_time_map


class Race(unittest.TestCase):
    @staticmethod
    def _driver_laps(number, name, positions_and_seconds):
        base = pandas.Timestamp("2026-01-01")
        laps = {
            lap_number: Lap(80, base + pandas.to_timedelta(timestamp, unit="s"), position, tyre=Tyre("Soft", True))
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
        position_logs = lap_times_by_position(lap_logs)
        session = SimpleNamespace(laps=MagicMock())
        top_times = top_time_map(lap_logs)
        with (
            patch("f1_explorer.visualizations.race.make_top_time_map", return_value=top_times),
            patch("f1_explorer.visualizations.race.save_plotly") as save,
        ):
            gap_to_ahead_table(MagicMock(), "ahead.png", lap_logs, position_logs)
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
            patch("f1_explorer.visualizations.race.make_top_time_map", return_value=top_times),
            patch("f1_explorer.visualizations.race.fastf1.plotting.get_team_color", return_value="#123456"),
            patch("f1_explorer.visualizations.race.save_plotly") as save,
        ):
            gap_to_ahead_graph(MagicMock(), "output", "ahead", session, None, nonempty, position_logs)
            ahead_graph = save.call_args.args[0]
            gap_to_top_graph(MagicMock(), "output", "top", session, None, nonempty)
            top_graph = save.call_args.args[0]
        for graph, table in ((ahead_graph, ahead_by_driver), (top_graph, top_by_driver)):
            for trace in graph.data:
                for lap, value in zip(trace.x, trace.y):
                    self.assertEqual("---" if value is None else value, table[trace.name][lap - 1])

    def test_gap_tables_handle_only_empty_drivers(self):
        empty = DriverLaps(Driver(1, "EMPTY", "Team"), {})
        with (
            patch("f1_explorer.visualizations.race.make_top_time_map", return_value={}),
            patch("f1_explorer.visualizations.race.save_plotly") as save,
        ):
            gap_to_ahead_table(MagicMock(), "ahead.png", [empty], {})
            ahead = save.call_args.args[0]
            gap_to_top_table(MagicMock(), "top.png", [empty], SimpleNamespace(laps=None))
            top = save.call_args.args[0]
        for fig in (ahead, top):
            self.assertEqual(["Lap", "EMPTY"], list(fig.data[0].header.values))
            self.assertEqual([[], []], [list(column) for column in fig.data[0].cells.values])

    def test_gap_tables_handle_no_drivers(self):
        with patch("f1_explorer.visualizations.race.save_plotly") as save:
            gap_to_ahead_table(MagicMock(), "ahead.png", [], {})
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
            "Time": pandas.to_datetime(["2026-01-01 00:00:00", "2026-01-01 00:01:23", "2026-01-01 00:00:0"]),
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
        self.assertEqual(pandas.to_datetime("2026-01-01 00:00:00"), result_sorted[1].get_laps()[1].get_at())
        self.assertEqual(1, result_sorted[1].get_laps()[1].get_position())
        self.assertEqual(False, result_sorted[1].get_laps()[1].get_pit_out())
        self.assertEqual(True, result_sorted[1].get_laps()[1].get_tyre().get_new())
        self.assertEqual('Soft', result_sorted[1].get_laps()[1].get_tyre().get_compound())
        self.assertEqual(82.789, result_sorted[1].get_laps()[2].get_time())
        self.assertEqual(pandas.to_datetime("2026-01-01 00:01:23"), result_sorted[1].get_laps()[2].get_at())
        self.assertEqual(1, result_sorted[1].get_laps()[2].get_position())
        self.assertEqual(False, result_sorted[1].get_laps()[2].get_pit_out())
        self.assertEqual(True, result_sorted[1].get_laps()[2].get_tyre().get_new())
        self.assertEqual('Soft', result_sorted[1].get_laps()[2].get_tyre().get_compound())

        self.assertEqual(1, len(result_sorted[0].get_laps()))
        self.assertEqual(16, result_sorted[0].get_driver().get_number())
        self.assertEqual('Lec', result_sorted[0].get_driver().get_name())
        self.assertEqual('Ferrari', result_sorted[0].get_driver().get_team_name())
        self.assertEqual(83.000, result_sorted[0].get_laps()[1].get_time())
        self.assertEqual(pandas.to_datetime("2026-01-01 00:00:00"), result_sorted[0].get_laps()[1].get_at())
        self.assertEqual(2, result_sorted[0].get_laps()[1].get_position())
        self.assertEqual(False, result_sorted[0].get_laps()[1].get_pit_out())
        self.assertEqual(True, result_sorted[0].get_laps()[1].get_tyre().get_new())
        self.assertEqual('Soft', result_sorted[0].get_laps()[1].get_tyre().get_compound())

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

    def test_make_lap_log_marks_only_laps_with_pit_out_time(self):
        data = {
            "DriverNumber": ["1"], "Driver": ["Max"], "Stint": [2], "Team": ["Red Bull"],
            "LapNumber": [10], "Position": [1], "Compound": ["Soft"], "FreshTyre": [True],
            "PitOutTime": pandas.to_timedelta(["12s"]),
            "Time": pandas.to_datetime(["2026-01-01 00:12:00"]),
            "LapTime": pandas.to_timedelta(["90s"]),
        }
        result = make_driver_laps_set(Laps(pandas.DataFrame(data)))

        self.assertTrue(result[0].get_laps()[10].get_pit_out())

    def test_make_lap_log_skips_incomplete_laps_and_empty_drivers(self):
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

        self.assertEqual([1], [driver_laps.driver.number for driver_laps in result])
        self.assertEqual([1], list(result[0].laps))

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

    def test_gap_ahead_graph_is_plotly_and_sorted_by_final_position(self):
        first_lap = MagicMock()
        first_lap.get_position.return_value = 1
        second_lap = MagicMock()
        second_lap.get_position.return_value = 2
        lap_logs = [
            DriverLaps(Driver(2, "SECOND", "Team B"), {1: second_lap}),
            DriverLaps(Driver(1, "FIRST", "Team A"), {1: first_lap}),
        ]
        session = SimpleNamespace(event=SimpleNamespace(year=2026))

        with (
            patch(
                "f1_explorer.visualizations.race.calculate_gap_to_ahead",
                return_value=[(1, None), (2, 1.25), (3, 3.25)],
            ),
            patch("f1_explorer.visualizations.race.fastf1.plotting.get_team_color", return_value="#123456"),
            patch("f1_explorer.visualizations.race.save_plotly") as save,
        ):
            gap_to_ahead_graph(MagicMock(), "output", "gap_ahead_graph", session, 15, lap_logs, {})

        self.assertEqual(2, save.call_count)
        default_figure = save.call_args_list[0].args[0]
        ranged_figure = save.call_args_list[1].args[0]
        self.assertEqual(["FIRST", "SECOND"], [trace.name for trace in default_figure.data])
        self.assertEqual((3.29, 1.21), default_figure.layout.yaxis.range)
        self.assertEqual((15, 0), ranged_figure.layout.yaxis.range)
        self.assertEqual("output/gap_ahead_graph.png", save.call_args_list[0].args[1])

    def test_gap_top_graph_is_plotly_and_keeps_zero_at_top(self):
        leader_lap = MagicMock()
        leader_lap.get_position.return_value = 1
        lap_logs = [DriverLaps(Driver(1, "FIRST", "Team A"), {1: leader_lap})]
        session = SimpleNamespace(event=SimpleNamespace(year=2026), laps=MagicMock())

        with (
            patch("f1_explorer.visualizations.race.make_top_time_map", return_value={}),
            patch("f1_explorer.visualizations.race.calculate_gap_to_leader", return_value=[(1, 0.0)]),
            patch("f1_explorer.visualizations.race.fastf1.plotting.get_team_color", return_value="#123456"),
            patch("f1_explorer.visualizations.race.save_plotly") as save,
        ):
            gap_to_top_graph(MagicMock(), "output", "gap_top_graph", session, None, lap_logs)

        save.assert_called_once()
        figure = save.call_args.args[0]
        self.assertEqual("FIRST", figure.data[0].name)
        self.assertEqual((60, 0), figure.layout.yaxis.range)
        self.assertEqual("x unified", figure.layout.hovermode)


if __name__ == '__main__':
    unittest.main()
