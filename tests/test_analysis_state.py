"""Tests for analysis fingerprints and success manifests."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from f1_explorer.analysis_state import (
    MISSING_VERSION,
    SCHEMA_VERSION,
    build_fingerprint,
    manifest_path,
    invalidate_success_manifest,
    should_skip,
    write_success_manifest,
)


IDENTITY = {
    "year": 2026,
    "round": 5,
    "session": "Race",
    "entrypoint": "analyze_race.py",
}
SESSION_INPUT = {"algorithm": "fastf1-session-input-v1", "hash": "a" * 64,
                 "components": ["event"], "fastf1_version": "test"}


class AnalysisStateTest(unittest.TestCase):
    def _session_inputs(self):
        from types import SimpleNamespace

        data = pd.DataFrame({"Time": [pd.Timestamp("2026-01-01")], "Value": [1]})
        return SimpleNamespace(
            event={"Year": 2026, "Round": 1},
            results=pd.DataFrame({"Position": [1], "Driver": ["AAA"]}),
            laps=pd.DataFrame({"LapNumber": [1], "Value": [1]}),
            weather_data=data.copy(),
            session_status=pd.DataFrame({"Status": ["Finished"]}),
            track_status=pd.DataFrame({"Time": [pd.Timestamp("2026-01-01")], "Status": ["1"]}),
            car_data={"1": data.copy()}, pos_data={"1": data.copy()},
            race_control_messages=pd.DataFrame({"Time": [pd.Timestamp("2026-01-01")], "Message": ["green"]}),
        )

    def test_manifest_excludes_unused_pngs_but_tracks_retained_images_and_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self._repo(Path(temporary) / "repo")
            report_dir = Path(temporary) / "reports"
            image_dir = Path(temporary) / "images"
            image_dir.mkdir()
            retained = image_dir / "laptime_table.png"
            stale = image_dir / "SpeedFL.png"
            log = image_dir / "messages.txt"
            for path in (retained, stale, log):
                path.write_bytes(b"output")
            fingerprint = self._fingerprint(root)
            manifest = write_success_manifest(
                report_dir, fingerprint, IDENTITY,
                extra_output_paths=(retained, log), required_output_paths=(retained,), session_input=SESSION_INPUT,
            )
            files = json.loads(manifest.read_text())["output_files"]
            self.assertIn(str(retained.resolve()), files)
            self.assertIn(str(log.resolve()), files)
            self.assertNotIn(str(stale.resolve()), files)
            stale.unlink()
            self.assertTrue(should_skip(manifest, fingerprint, IDENTITY, session_input=SESSION_INPUT))
            retained.unlink()
            self.assertFalse(should_skip(manifest, fingerprint, IDENTITY, session_input=SESSION_INPUT))

    def _repo(self, root: Path) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        (root / "analyze_race.py").write_text("print('race')\n", encoding="utf-8")
        package = root / "f1_explorer"
        package.mkdir()
        (package / "visualizations/domain").mkdir(parents=True)
        (package / "config.py").write_text("# config\n", encoding="utf-8")
        (package / "constants.py").write_text("YEAR = 2026\n", encoding="utf-8")
        (package / "util.py").write_text("# util\n", encoding="utf-8")
        (root / "requirements.txt").write_text(
            "present-package==1.0\nmissing_package>=2\n", encoding="utf-8"
        )
        (package / "visualizations/chart.py").write_text("# chart\n", encoding="utf-8")
        (package / "visualizations/domain/lap.py").write_text("# lap\n", encoding="utf-8")
        return root

    def _fingerprint(self, root: Path):
        versions = {"present-package": "1.2.3"}

        def version(name: str) -> str:
            if name not in versions:
                from importlib.metadata import PackageNotFoundError

                raise PackageNotFoundError(name)
            return versions[name]

        with patch("f1_explorer.analysis_state.metadata.version", side_effect=version):
            return build_fingerprint(root / "analyze_race.py", root)

    def test_fingerprint_is_deterministic_and_uses_relative_sorted_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self._repo(Path(temporary))
            first = self._fingerprint(root)
            second = self._fingerprint(root)

        self.assertEqual(first.source_hash, second.source_hash)
        self.assertEqual(first.environment_hash, second.environment_hash)
        self.assertEqual(list(first.source_files), sorted(first.source_files))
        self.assertIn("analyze_race.py", first.source_files)
        self.assertIn("f1_explorer/visualizations/domain/lap.py", first.source_files)
        self.assertNotIn(str(root), first.source_files)
        self.assertEqual(first.dependencies["present-package"], "1.2.3")
        self.assertEqual(first.dependencies["missing-package"], MISSING_VERSION)

    def test_source_content_change_changes_only_source_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self._repo(Path(temporary))
            before = self._fingerprint(root)
            (root / "f1_explorer/visualizations/chart.py").write_text("# changed\n", encoding="utf-8")
            after = self._fingerprint(root)

        self.assertNotEqual(before.source_hash, after.source_hash)
        self.assertEqual(before.environment_hash, after.environment_hash)

    def test_manifest_match_force_identity_and_missing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self._repo(Path(temporary) / "repo")
            output_dir = Path(temporary) / "images/session"
            output_dir.mkdir(parents=True)
            output = output_dir / "plot.png"
            output.write_bytes(b"image")
            fingerprint = self._fingerprint(root)
            path = write_success_manifest(output_dir, fingerprint, IDENTITY,
                                          extra_output_paths=(output,), required_output_paths=(output,), session_input=SESSION_INPUT)

            self.assertTrue(should_skip(path, fingerprint, IDENTITY, session_input=SESSION_INPUT))
            self.assertFalse(should_skip(path, fingerprint, IDENTITY, force=True))
            self.assertFalse(should_skip(path, fingerprint, IDENTITY, session_input=SESSION_INPUT, complete=False))
            self.assertFalse(should_skip(path, fingerprint, IDENTITY, session_input=None))
            changed_input = {**SESSION_INPUT, "hash": "b" * 64}
            self.assertFalse(should_skip(path, fingerprint, IDENTITY, session_input=changed_input))
            changed_identity = {**IDENTITY, "session": "Qualifying"}
            self.assertFalse(should_skip(path, fingerprint, changed_identity, session_input=SESSION_INPUT))
            output.unlink()
            self.assertFalse(should_skip(path, fingerprint, IDENTITY, session_input=SESSION_INPUT))

    def test_corrupt_and_old_manifest_are_cache_misses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self._repo(Path(temporary) / "repo")
            output_dir = Path(temporary) / "output"
            output_dir.mkdir()
            output = output_dir / "plot.png"
            output.write_bytes(b"image")
            fingerprint = self._fingerprint(root)
            path = manifest_path(output_dir)
            path.write_text("not json", encoding="utf-8")
            self.assertFalse(should_skip(path, fingerprint, IDENTITY, session_input=SESSION_INPUT))

            path.write_text(
                json.dumps({"schema_version": SCHEMA_VERSION - 1}), encoding="utf-8"
            )
            self.assertFalse(should_skip(path, fingerprint, IDENTITY, session_input=SESSION_INPUT))

    def test_success_manifest_contains_metadata_and_is_written_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self._repo(Path(temporary) / "repo")
            output_dir = Path(temporary) / "output"
            nested = output_dir / "tables/table.csv"
            nested.parent.mkdir(parents=True)
            nested.write_text("value\n", encoding="utf-8")
            external = Path(temporary) / "summary.txt"
            external.write_text("done\n", encoding="utf-8")
            fingerprint = self._fingerprint(root)

            path = write_success_manifest(
                output_dir, fingerprint, IDENTITY, extra_output_paths=(external, nested),
                required_output_paths=(external,), session_input=SESSION_INPUT
            )
            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(payload["schema_version"], SCHEMA_VERSION)
            self.assertEqual(payload["identity"], IDENTITY)
            self.assertEqual(
                payload["fingerprints"]["source"]["hash"], fingerprint.source_hash
            )
            self.assertIn("tables/table.csv", payload["output_files"])
            self.assertIn(str(external.resolve()), payload["output_files"])
            self.assertTrue(payload["completed_at"].endswith("Z"))
            self.assertEqual(list(output_dir.glob("*.tmp")), [])
            self.assertTrue(should_skip(path, fingerprint, IDENTITY, session_input=SESSION_INPUT))

    def test_manifest_tracks_outputs_from_a_separate_image_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self._repo(Path(temporary) / "repo")
            report_dir = Path(temporary) / "reports/session"
            report_dir.mkdir(parents=True)
            report = report_dir / "report.html"
            report.write_text("<html></html>", encoding="utf-8")
            image_dir = Path(temporary) / "images/session"
            image_dir.mkdir(parents=True)
            image = image_dir / "plot.png"
            image.write_bytes(b"image")
            (image_dir / ".analysis-manifest.json").write_text("legacy", encoding="utf-8")
            fingerprint = self._fingerprint(root)

            path = write_success_manifest(
                report_dir,
                fingerprint,
                IDENTITY,
                extra_output_paths=(report, image), required_output_paths=(report,), session_input=SESSION_INPUT,
            )
            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertIn("report.html", payload["output_files"])
            self.assertIn(str(image.resolve()), payload["output_files"])
            self.assertNotIn(str((image_dir / ".analysis-manifest.json").resolve()), payload["output_files"])
            self.assertTrue(should_skip(path, fingerprint, IDENTITY, session_input=SESSION_INPUT))
            image.unlink()
            self.assertFalse(should_skip(path, fingerprint, IDENTITY, session_input=SESSION_INPUT))

    def test_manifest_requires_explicit_existing_outputs_and_can_be_invalidated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self._repo(Path(temporary) / "repo")
            output_dir = Path(temporary) / "output"
            output_dir.mkdir()
            stale = output_dir / "old.png"
            stale.write_bytes(b"old")
            old_log = output_dir / "old.log"
            old_log.write_text("old log", encoding="utf-8")
            fingerprint = self._fingerprint(root)
            with self.assertRaises(ValueError):
                write_success_manifest(output_dir, fingerprint, IDENTITY)
            required = output_dir / "new.png"
            with self.assertRaises(FileNotFoundError):
                write_success_manifest(output_dir, fingerprint, IDENTITY,
                                       extra_output_paths=(required,), required_output_paths=(required,),
                                       session_input=SESSION_INPUT)
            self.assertTrue(stale.is_file())
            required.write_bytes(b"stale output")
            with self.assertRaises(ValueError):
                write_success_manifest(output_dir, fingerprint, IDENTITY,
                                       extra_output_paths=(stale,), required_output_paths=(required,),
                                       session_input=SESSION_INPUT)
            current = output_dir / "current.html"
            current.write_text("current", encoding="utf-8")
            manifest = write_success_manifest(
                output_dir, fingerprint, IDENTITY, extra_output_paths=(current,),
                required_output_paths=(current,), session_input=SESSION_INPUT,
            )
            files = json.loads(manifest.read_text(encoding="utf-8"))["output_files"]
            self.assertEqual(files, ["current.html"])
            self.assertTrue(stale.is_file())
            self.assertTrue(old_log.is_file())
            previous = manifest_path(output_dir)
            previous.write_text("old success", encoding="utf-8")
            invalidate_success_manifest(output_dir)
            self.assertFalse(previous.exists())
            self.assertTrue(stale.is_file())

    def test_session_input_normalization_and_finished_gate(self) -> None:
        from f1_explorer.analysis_state import session_input_fingerprint, session_is_finished

        frame = pd.DataFrame({"Time": [pd.Timestamp("2026-01-01"), pd.NaT],
                              "Value": [1.0, float("nan")]}, index=[4, 5])
        session = type("Session", (), {})()
        session.event = {"Year": 2026, "Round": 1}
        session.results = pd.DataFrame({"Position": [1], "Driver": ["AAA"]})
        session.laps = frame.assign(LapNumber=[1, 2])
        session.weather_data = pd.DataFrame({"Time": [pd.Timestamp("2026-01-01 00:00:01")]})
        session.session_status = pd.DataFrame({"Status": ["Started", "FINISHED"]})
        session.track_status = pd.DataFrame({"Time": [pd.Timestamp("2026-01-01 00:00:01")], "Status": ["1"]})
        session.car_data = {"1": frame}
        session.pos_data = {"1": frame}
        session.race_control_messages = pd.DataFrame({"Time": [pd.Timestamp("2026-01-01 00:00:01")], "Message": ["test"]})
        first = session_input_fingerprint(session, include_messages=True)
        self.assertTrue(session_is_finished(session))
        self.assertIsNotNone(first)
        session.laps.loc[4, "Value"] = 2.0
        self.assertNotEqual(first["hash"], session_input_fingerprint(session, include_messages=True)["hash"])
        session.session_status = pd.DataFrame({"Status": ["Finalised"]})
        self.assertFalse(session_is_finished(session))
        session.session_status = pd.DataFrame()
        self.assertFalse(session_is_finished(session))
        del session.results
        self.assertIsNone(session_input_fingerprint(session, include_messages=True))
        session = self._session_inputs()
        session.results = None
        self.assertIsNone(session_input_fingerprint(session, include_messages=True))

        class Unavailable:
            @property
            def results(self):
                raise RuntimeError("FastF1 data not loaded")

        broken = Unavailable()
        for name, value in vars(self._session_inputs()).items():
            if name != "results":
                setattr(broken, name, value)
        self.assertIsNone(session_input_fingerprint(broken, include_messages=True))

    def test_each_raw_session_component_changes_the_fingerprint(self) -> None:
        from f1_explorer.analysis_state import session_input_fingerprint

        changes = {
            "event": lambda s: s.event.update(Round=2),
            "results": lambda s: s.results.__setitem__("Position", [2]),
            "laps": lambda s: s.laps.__setitem__("Value", [2]),
            "weather_data": lambda s: s.weather_data.__setitem__("Value", [2]),
            "session_status": lambda s: s.session_status.__setitem__("Status", ["Started"]),
            "track_status": lambda s: s.track_status.__setitem__("Status", ["2"]),
            "car_data": lambda s: s.car_data["1"].__setitem__("Value", [2]),
            "pos_data": lambda s: s.pos_data["1"].__setitem__("Value", [2]),
            "race_control_messages": lambda s: s.race_control_messages.__setitem__("Message", ["red"]),
        }
        for component, change in changes.items():
            with self.subTest(component=component):
                session = self._session_inputs()
                before = session_input_fingerprint(session, include_messages=True)
                change(session)
                after = session_input_fingerprint(session, include_messages=True)
                self.assertIsNotNone(before)
                self.assertNotEqual(before["hash"], after["hash"])
        without_messages = session_input_fingerprint(self._session_inputs(), include_messages=False)
        with_messages = session_input_fingerprint(self._session_inputs(), include_messages=True)
        self.assertNotEqual(without_messages["hash"], with_messages["hash"])
        self.assertNotIn("race_control_messages", without_messages["components"])

    def test_dataframe_shape_order_missing_and_numeric_types_are_explicit(self) -> None:
        from f1_explorer.analysis_state import session_input_fingerprint

        baseline = self._session_inputs()
        base_hash = session_input_fingerprint(baseline, include_messages=False)["hash"]
        variants = []
        changed = self._session_inputs()
        changed.laps = changed.laps.set_index(pd.Index([8]))
        variants.append(("index", changed))
        changed = self._session_inputs()
        changed.laps = changed.laps[["Value", "LapNumber"]]
        variants.append(("column order", changed))
        changed = self._session_inputs()
        changed.laps["Extra"] = [1]
        variants.append(("added column", changed))
        changed = self._session_inputs()
        changed.laps = changed.laps.drop(columns="LapNumber")
        variants.append(("missing required column", changed))
        changed = self._session_inputs()
        changed.pos_data["1"] = changed.pos_data["1"].drop(columns="Time")
        variants.append(("missing telemetry column", changed))
        changed = self._session_inputs()
        changed.laps = pd.DataFrame({"LapNumber": [1, 2], "Value": [1, 2]})
        changed.laps = changed.laps.iloc[::-1]
        variants.append(("row order", changed))
        for label, session in variants:
            with self.subTest(label=label):
                current = session_input_fingerprint(session, include_messages=False)
                if label.startswith("missing"):
                    self.assertIsNone(current)
                else:
                    self.assertNotEqual(base_hash, current["hash"])

        left = self._session_inputs()
        left.laps = pd.DataFrame({"LapNumber": [1], "Value": [float("nan")]})
        right = self._session_inputs()
        right.laps = pd.DataFrame({"LapNumber": [1], "Value": [None]})
        self.assertEqual(session_input_fingerprint(left, include_messages=False)["hash"],
                         session_input_fingerprint(right, include_messages=False)["hash"])
        left.laps["Value"] = [1]
        right.laps["Value"] = [1.0]
        self.assertNotEqual(session_input_fingerprint(left, include_messages=False)["hash"],
                            session_input_fingerprint(right, include_messages=False)["hash"])


if __name__ == "__main__":
    unittest.main()
