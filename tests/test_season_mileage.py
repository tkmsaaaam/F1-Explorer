import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas
import analyze_season

from f1_explorer.season_mileage import (
    Driver,
    DriverMetrics,
    Metric,
    WeekendMetrics,
    _attack_metrics,
    analyze_session,
    apply_driver_aliases,
    count_completed_laps,
    render_report_section,
)


def _laps(numbers, times, *, compounds=None, s1=None, pit_out=None, pit_in=None, generated=None):
    count = len(numbers)
    return pandas.DataFrame({
        "DriverNumber": ["1"] * count,
        "LapNumber": numbers,
        "Time": pandas.to_timedelta(["90s"] * count),
        "LapTime": pandas.to_timedelta(times),
        "Sector1Time": pandas.to_timedelta(s1 or ["28s"] * count),
        "Sector2Time": pandas.to_timedelta(["36s"] * count),
        "Sector3Time": pandas.to_timedelta(["26s"] * count),
        "PitOutTime": pit_out or [pandas.NaT] * count,
        "PitInTime": pit_in or [pandas.NaT] * count,
        "Compound": compounds or ["SOFT"] * count,
        "IsAccurate": [True] * count,
        "Deleted": [False] * count,
        "FastF1Generated": generated or [False] * count,
        "TrackStatus": ["1"] * count,
    })


class SeasonMileageTests(unittest.TestCase):
    def test_sprint_points_use_loaded_venues_in_calendar_order(self):
        shanghai = analyze_season.Weekend("Chinese Grand Prix")
        shanghai.set_sprint_point("AAA", 8)
        miami = analyze_season.Weekend("Miami Grand Prix")
        miami.set_sprint_point("AAA", 0)
        race_only = analyze_season.Weekend("Japanese Grand Prix")
        race_only.set_point("AAA", 25)
        schedule = pandas.DataFrame({"RoundNumber": [2, 3, 6, 10],
                                     "Location": ["Shanghai", "Suzuka", "Miami", "Unknown"]})
        results = {6: miami, 3: race_only, 2: shanghai}
        rows = analyze_season._sprint_point_rows(results, schedule)
        self.assertEqual([(2, "Shanghai"), (6, "Miami")], rows)
        self.assertEqual([8, 0], [results[number].get_sprint_point("AAA") for number, _ in rows])

    def test_published_championship_order_applies_to_every_table(self):
        drivers = {"a": Driver("a", "A Driver", "AAA", "1"),
                   "b": Driver("b", "B Driver", "BBB", "2")}
        standings = pandas.DataFrame({"driverId": ["a", "b"], "position": [2, 1]})
        with patch.object(analyze_season, "Ergast") as api:
            api.return_value.get_driver_standings.return_value = SimpleNamespace(content=[standings])
            order = getattr(analyze_season, "__season_driver_order")(2026, drivers, {}, MagicMock())
            api.return_value.get_driver_standings.assert_called_once_with(season=2026, round="last", limit=100)
        self.assertEqual(["b", "a"], order)
        html = render_report_section(drivers, [WeekendMetrics("GP", 1)], driver_order=order)
        self.assertEqual(4, html.count("<th>BBB</th><th>AAA</th>"))

    def test_championship_fallback_uses_points_countback_then_practice_only(self):
        drivers = {"a": Driver("a", "A", "AAA", "1"),
                   "b": Driver("b", "B", "BBB", "2"),
                   "c": Driver("c", "C", "CCC", "3")}
        race = analyze_season.Weekend("GP")
        race.set_grid_position("AAA", 1)
        race.set_position("AAA", 2)
        race.set_position("BBB", 1)
        race.set_point("AAA", 25)
        race.set_point("BBB", 25)
        with patch.object(analyze_season, "Ergast") as api:
            api.return_value.get_driver_standings.side_effect = ValueError("unavailable")
            order = getattr(analyze_season, "__season_driver_order")(2026, drivers, {1: race}, MagicMock())
        self.assertEqual(["b", "a", "c"], order)

    def test_completed_laps_count_end_records_and_unique_numbers(self):
        laps = pandas.DataFrame({
            "LapNumber": [1, 2, 2, 4, 5],
            "Time": pandas.to_timedelta(["90s", None, "180s", "270s", "360s"]),
            "FastF1Generated": [False, False, False, False, True],
        })
        self.assertEqual((3, ["3"]), count_completed_laps(laps))

    def test_practice_long_run_is_not_counted_as_attack(self):
        laps = _laps([1, 2, 3, 4, 5], ["90s"] * 5)
        result = _attack_metrics(laps, "FP1", qualifying=False)["FP1:1"]
        self.assertEqual(0, result.value)
        self.assertTrue(result.incomplete)
        self.assertIn("FP用途判定不明", result.details[0])

    def test_fast_sector_abort_and_deleted_lap_are_counted(self):
        laps = _laps(
            [1, 2, 3], [None, "90s", "90s"],
            s1=["28s", "28s", "28s"],
            pit_out=[pandas.NaT] * 3,
            pit_in=[pandas.NaT, pandas.NaT, pandas.NaT],
        )
        laps.loc[2, "Deleted"] = True
        result = _attack_metrics(laps, "FP1", qualifying=False)["FP1:1"]
        self.assertEqual(3, result.value)
        self.assertIn("Lap 1 (S1)", result.details[0])

    def test_pit_out_lap_is_not_counted_but_pit_in_attack_is(self):
        laps = _laps([1, 2, 3], ["90s", "90s", "90s"],
                     pit_out=[pandas.NaT, pandas.to_timedelta(["1s"])[0], pandas.NaT],
                     pit_in=[pandas.NaT, pandas.NaT, pandas.to_timedelta(["80s"])[0]])
        result = _attack_metrics(laps, "FP1", qualifying=False)["FP1:1"]
        self.assertEqual(2, result.value)

    def test_compounds_have_independent_reference_and_unknown_is_reported(self):
        laps = _laps([1, 2, 3], ["90s", "100s", "90s"], compounds=["SOFT", "MEDIUM", None])
        result = _attack_metrics(laps, "FP1", qualifying=False)["FP1:1"]
        self.assertEqual(2, result.value)
        self.assertTrue(result.incomplete)
        self.assertIn("コンパウンド単位: コンパウンド不明", result.details)

    def test_qualifying_split_failure_does_not_assign_attempts_to_q1(self):
        laps = _laps([1], ["90s"])
        fake_session = SimpleNamespace(laps=SimpleNamespace(
            split_qualifying_sessions=lambda: (_ for _ in ()).throw(ValueError("missing status"))))
        laps.attrs["session"] = fake_session
        result = _attack_metrics(laps, "Q", qualifying=True)
        self.assertEqual({"Q1", "Q2", "Q3"}, set(result))
        self.assertTrue(all(metric.value is None and metric.status == "unknown" for metric in result.values()))

    def test_qualifying_nonparticipant_and_cancelled_segment_are_distinct(self):
        class QualifyingLaps(pandas.DataFrame):
            @property
            def _constructor(self):
                return QualifyingLaps

            def split_qualifying_sessions(self):
                return [self[self.DriverNumber == "1"], self.iloc[0:0], None]

        laps = QualifyingLaps(_laps([1, 2, 3], ["90s", "91s", "92s"]))
        laps.loc[1, "DriverNumber"] = "2"
        laps.loc[1, "Compound"] = "MEDIUM"

        class Session:
            def __init__(self):
                self.laps = laps

            def get_driver(self, number):
                return {"DriverId": f"driver-{number}", "Abbreviation": f"D{number}"}

        _, metrics = analyze_session(Session(), "Q")
        self.assertEqual("not-participant", metrics["driver-2"].attacks["Q1"].status)
        self.assertEqual("not-participant", metrics["driver-1"].attacks["Q2"].status)
        self.assertEqual("not-held", metrics["driver-1"].attacks["Q3"].status)

    def test_session_driver_identity_uses_driver_id_and_keeps_metric_types_separate(self):
        class Session:
            laps = _laps([1, 2], ["90s", "100s"])

            def get_driver(self, number):
                return {"DriverId": "driver-one", "Abbreviation": "AAA", "FullName": "A Driver"}

        drivers, metrics = analyze_session(Session(), "FP1")
        self.assertEqual(["driver-one"], list(drivers))
        self.assertEqual(2, metrics["driver-one"].laps["FP1"].value)
        self.assertIn("FP1", metrics["driver-one"].attacks)

    def test_driver_identity_is_stable_when_id_is_discovered_later(self):
        identity_by_number = {}
        prior_weekend = WeekendMetrics("First GP", 1)
        drivers = {}

        class Session:
            def __init__(self, driver_info):
                self.laps = _laps([1], ["90s"])
                self.driver_info = driver_info

            def get_driver(self, number):
                return self.driver_info

        first_drivers, first_metrics = analyze_session(
            Session({"Abbreviation": "STR", "FullName": "Lance Stroll"}), "FP1",
            identity_by_number=identity_by_number,
        )
        drivers.update(first_drivers)
        prior_weekend.drivers.update(first_metrics)

        aliases = {}
        second_drivers, second_metrics = analyze_session(
            Session({"DriverId": "stroll", "Abbreviation": "STR", "FullName": "Lance Stroll"}), "FP2",
            identity_by_number=identity_by_number, identity_aliases=aliases,
        )
        apply_driver_aliases(drivers, [prior_weekend], aliases)
        drivers.update(second_drivers)

        self.assertEqual({"stroll"}, set(drivers))
        self.assertEqual({"stroll"}, set(prior_weekend.drivers))
        self.assertEqual(1, prior_weekend.drivers["stroll"].laps["FP1"].value)
        self.assertEqual(1, second_metrics["stroll"].laps["FP2"].value)
        html = render_report_section(drivers, [prior_weekend, WeekendMetrics("Second GP", 2, second_metrics)])
        self.assertEqual(6, html.count("<th>STR</th>"))

    def test_missing_id_after_known_id_reuses_key_but_different_driver_does_not(self):
        identity_by_number = {}

        class Session:
            def __init__(self, driver_info):
                self.laps = _laps([1], ["90s"])
                self.driver_info = driver_info

            def get_driver(self, number):
                return self.driver_info

        first, _ = analyze_session(Session({"DriverId": "stroll", "Abbreviation": "STR", "FullName": "Lance Stroll"}),
                                   "FP1", identity_by_number=identity_by_number)
        later, _ = analyze_session(Session({"Abbreviation": "STR", "FullName": "Lance Stroll"}),
                                   "FP2", identity_by_number=identity_by_number)
        replacement, _ = analyze_session(Session({"DriverId": "other", "Abbreviation": "ABC", "FullName": "Other Driver"}),
                                         "FP3", identity_by_number=identity_by_number)
        unnumbered_replacement, _ = analyze_session(
            Session({"Abbreviation": "XYZ", "FullName": "Replacement Driver"}), "FP1",
            identity_by_number=identity_by_number,
        )

        self.assertEqual({"stroll"}, set(first))
        self.assertEqual({"stroll"}, set(later))
        self.assertEqual({"other"}, set(replacement))
        self.assertEqual({"number:1:xyz|replacement driver"}, set(unnumbered_replacement))

    def test_incomplete_names_keep_fallback_history_linked_to_later_driver_id(self):
        identity_by_number = {}
        identity_history_by_number = {}
        accumulated_drivers = {}
        weekends = []

        class Session:
            def __init__(self, info):
                self.laps = _laps([1], ["90s"])
                self.info = info

            def get_driver(self, number):
                return self.info

        records = [
            ("FP1", {"Abbreviation": "STR", "FullName": "Lance Stroll"}),
            ("FP2", {"Abbreviation": "STR", "FullName": "None None"}),
            ("FP3", {"DriverId": "stroll", "Abbreviation": "STR", "FullName": "None None"}),
            ("Q", {"Abbreviation": "STR", "FullName": "Lance Stroll"}),
        ]
        for round_number, (code, info) in enumerate(records, 1):
            aliases = {}
            found_drivers, found_metrics = analyze_session(
                Session(info), code,
                identity_by_number=identity_by_number,
                identity_history_by_number=identity_history_by_number,
                identity_aliases=aliases,
            )
            apply_driver_aliases(accumulated_drivers, weekends, aliases)
            accumulated_drivers.update(found_drivers)
            weekend = WeekendMetrics(f"GP {round_number}", round_number, found_metrics)
            weekends.append(weekend)

        self.assertEqual({"stroll"}, set(accumulated_drivers))
        self.assertTrue(all(set(weekend.drivers) == {"stroll"} for weekend in weekends))
        self.assertEqual("Lance Stroll", accumulated_drivers["stroll"].name)
        self.assertEqual(4, sum(weekend.drivers["stroll"].laps[code].value or 0
                                for weekend, (code, _) in zip(weekends, records)))

    def test_complete_names_prevent_merging_distinct_drivers_reusing_number(self):
        identity_by_number = {}
        identity_history_by_number = {}

        class Session:
            def __init__(self, info):
                self.laps = _laps([1], ["90s"])
                self.info = info

            def get_driver(self, number):
                return self.info

        original, _ = analyze_session(
            Session({"DriverId": "driver-one", "Abbreviation": "AAA", "FullName": "Alex Example"}),
            "FP1", identity_by_number=identity_by_number,
            identity_history_by_number=identity_history_by_number,
        )
        replacement, _ = analyze_session(
            Session({"Abbreviation": "AAA", "FullName": "Another Example"}),
            "FP2", identity_by_number=identity_by_number,
            identity_history_by_number=identity_history_by_number,
        )

        self.assertEqual({"driver-one"}, set(original))
        self.assertEqual({"number:1:aaa|another example"}, set(replacement))

    def test_abbreviation_fallback_name_matches_id_then_missing_full_name(self):
        identity_by_number = {}
        identity_history_by_number = {}

        class Session:
            def __init__(self, info):
                self.laps = _laps([1], ["90s"])
                self.info = info

            def get_driver(self, number):
                return self.info

        no_name, _ = analyze_session(
            Session({"Abbreviation": "STR"}), "FP1",
            identity_by_number=identity_by_number,
            identity_history_by_number=identity_history_by_number,
        )
        identified, _ = analyze_session(
            Session({"DriverId": "stroll", "Abbreviation": "STR", "FullName": "Lance Stroll"}), "FP2",
            identity_by_number=identity_by_number,
            identity_history_by_number=identity_history_by_number,
        )
        name_missing_again, _ = analyze_session(
            Session({"Abbreviation": "STR"}), "FP3",
            identity_by_number=identity_by_number,
            identity_history_by_number=identity_history_by_number,
        )

        self.assertEqual({"number:1"}, set(no_name))
        self.assertEqual({"stroll"}, set(identified))
        self.assertEqual({"stroll"}, set(name_missing_again))
        self.assertEqual("Lance Stroll", name_missing_again["stroll"].name)

    def test_report_sums_rounds_and_marks_failed_data(self):
        driver = Driver("one", "A Driver", "AAA", "1")
        first = WeekendMetrics("One GP", 1, {
            "one": DriverMetrics(laps={"FP1": Metric(10, "available")},
                                 attacks={"FP1": Metric(2, "available")})
        }, {"FP1": "available", "FP2": "failed"})
        second = WeekendMetrics("Two GP", 2, {
            "one": DriverMetrics(laps={"FP1": Metric(12, "available")},
                                 attacks={"FP1": Metric(1, "available")})
        }, {"FP1": "available"})
        html = render_report_section({"one": driver}, [first, second])
        self.assertIn("22* ", html)
        self.assertIn("3", html)
        self.assertIn("GPを選択", html)
        self.assertIn("取得失敗", html)


if __name__ == "__main__":
    unittest.main()
