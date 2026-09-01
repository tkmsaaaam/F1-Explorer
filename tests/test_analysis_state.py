"""Tests for analysis fingerprints and success manifests."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from analysis_state import (
    MISSING_VERSION,
    SCHEMA_VERSION,
    build_fingerprint,
    manifest_path,
    should_skip,
    write_success_manifest,
)


IDENTITY = {
    "year": 2026,
    "round": 5,
    "session": "Race",
    "entrypoint": "analyze_race.py",
}


class AnalysisStateTest(unittest.TestCase):
    def _repo(self, root: Path) -> Path:
        (root / "visualizations/domain").mkdir(parents=True)
        (root / "analyze_race.py").write_text("print('race')\n", encoding="utf-8")
        (root / "setup.py").write_text("# setup\n", encoding="utf-8")
        (root / "constants.py").write_text("YEAR = 2026\n", encoding="utf-8")
        (root / "util.py").write_text("# util\n", encoding="utf-8")
        (root / "requirements.txt").write_text(
            "present-package==1.0\nmissing_package>=2\n", encoding="utf-8"
        )
        (root / "visualizations/chart.py").write_text("# chart\n", encoding="utf-8")
        (root / "visualizations/domain/lap.py").write_text("# lap\n", encoding="utf-8")
        return root

    def _fingerprint(self, root: Path):
        versions = {"present-package": "1.2.3"}

        def version(name: str) -> str:
            if name not in versions:
                from importlib.metadata import PackageNotFoundError

                raise PackageNotFoundError(name)
            return versions[name]

        with patch("analysis_state.metadata.version", side_effect=version):
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
        self.assertIn("visualizations/domain/lap.py", first.source_files)
        self.assertNotIn(str(root), first.source_files)
        self.assertEqual(first.dependencies["present-package"], "1.2.3")
        self.assertEqual(first.dependencies["missing-package"], MISSING_VERSION)

    def test_source_content_change_changes_only_source_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self._repo(Path(temporary))
            before = self._fingerprint(root)
            (root / "visualizations/chart.py").write_text("# changed\n", encoding="utf-8")
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
            path = write_success_manifest(output_dir, fingerprint, IDENTITY)

            self.assertTrue(should_skip(path, fingerprint, IDENTITY))
            self.assertFalse(should_skip(path, fingerprint, IDENTITY, force=True))
            changed_identity = {**IDENTITY, "session": "Qualifying"}
            self.assertFalse(should_skip(path, fingerprint, changed_identity))
            output.unlink()
            self.assertFalse(should_skip(path, fingerprint, IDENTITY))

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
            self.assertFalse(should_skip(path, fingerprint, IDENTITY))

            path.write_text(
                json.dumps({"schema_version": SCHEMA_VERSION - 1}), encoding="utf-8"
            )
            self.assertFalse(should_skip(path, fingerprint, IDENTITY))

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
                output_dir, fingerprint, IDENTITY, extra_output_paths=(external,)
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
            self.assertTrue(should_skip(path, fingerprint, IDENTITY))

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
                extra_output_dirs=(image_dir,),
            )
            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertIn("report.html", payload["output_files"])
            self.assertIn(str(image.resolve()), payload["output_files"])
            self.assertNotIn(str((image_dir / ".analysis-manifest.json").resolve()), payload["output_files"])
            self.assertTrue(should_skip(path, fingerprint, IDENTITY))
            image.unlink()
            self.assertFalse(should_skip(path, fingerprint, IDENTITY))


if __name__ == "__main__":
    unittest.main()
