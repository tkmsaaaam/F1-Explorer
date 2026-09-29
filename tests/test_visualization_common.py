"""Tests for the common visualization foundation."""

from __future__ import annotations

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import plotly.graph_objects as go

from visualizations.output import (
    resolve_output_dir,
    save_matplotlib,
    save_plotly,
    save_plotly_batch,
    session_output_dir,
    session_report_dir,
)
from visualizations.style import driver_linestyle
from visualizations.report import SessionReport


def _session() -> SimpleNamespace:
    return SimpleNamespace(
        event=SimpleNamespace(year=2025, RoundNumber=7, Location="Silverstone"),
        name="Free Practice 1",
    )


class VisualizationCommon(unittest.TestCase):
    def test_session_output_dir_preserves_session_layout_and_normalizes_root(self) -> None:
        session = _session()
        self.assertEqual(
            session_output_dir(session, Path("./images")),
            Path("images/2025/7_Silverstone/FreePractice1"),
        )
        self.assertEqual(
            session_output_dir(session, "custom"),
            Path("custom/2025/7_Silverstone/FreePractice1"),
        )
        self.assertEqual(
            session_report_dir(session),
            Path("reports/2025/7_Silverstone/FreePractice1"),
        )


    def test_resolve_output_dir_uses_derived_or_explicit_path(self) -> None:
        session = _session()
        self.assertEqual(
            resolve_output_dir(session, None),
            Path("images/2025/7_Silverstone/FreePractice1"),
        )
        self.assertEqual(resolve_output_dir(session, "plots"), Path("plots"))


    def test_session_output_dir_accepts_mapping_event(self) -> None:
        session = {
            "event": {"year": 2025, "RoundNumber": 7, "Location": "Spa"},
            "name": "Race",
        }
        self.assertEqual(session_output_dir(session, "images"), Path("images/2025/7_Spa/Race"))


    def test_save_matplotlib_creates_parent_and_closes_once(self) -> None:
        fig = Mock()
        log = Mock()
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "plots/figure.png"
            with patch("visualizations.output.plt.close") as close:
                result = save_matplotlib(fig, output_path, log)

        self.assertEqual(result, output_path)
        fig.savefig.assert_called_once_with(result, bbox_inches="tight")
        close.assert_called_once_with(fig)
        log.info.assert_called_once()


    def test_save_matplotlib_closes_when_save_raises(self) -> None:
        fig = Mock()
        fig.savefig.side_effect = RuntimeError("save failed")
        log = Mock()
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "plots/figure.png"
            with patch("visualizations.output.plt.close") as close:
                with self.assertRaisesRegex(RuntimeError, "save failed"):
                    save_matplotlib(fig, output_path, log)

        close.assert_called_once_with(fig)
        log.info.assert_not_called()


    def test_save_plotly_creates_parent_and_passes_dimensions(self) -> None:
        fig = Mock()
        log = Mock()
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "plots/figure.png"
            result = save_plotly(fig, output_path, log, width=1200, height=800)

        self.assertEqual(result, output_path)
        fig.write_image.assert_called_once_with(result, width=1200, height=800)
        log.info.assert_called_once()


    def test_save_plotly_batch_registers_three_images_in_order(self) -> None:
        figures = [go.Figure(data=[go.Table(header=dict(values=[name]))])
                   for name in ("durations", "ranks", "gaps")]
        log = Mock()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / f"corners_{name}.png"
                     for name in ("durations", "ranks", "gaps_to_best")]

            def write_images(*, fig, file, width, height):
                self.assertEqual(fig, figures)
                self.assertEqual(file, paths)
                self.assertEqual((width, height), (1920, 1080))
                for path in file:
                    path.write_bytes(b"png")

            with SessionReport(SimpleNamespace(name="Practice 1"), root) as report:
                with patch("visualizations.output.pio.write_images", side_effect=write_images) as write:
                    self.assertEqual(
                        save_plotly_batch(figures, paths, log, width=1920, height=1080), paths,
                    )
                self.assertEqual({item.path for item in report._ordered_items()},
                                 {path.resolve() for path in paths})
                self.assertTrue(all(item.figure_json for item in report._ordered_items()))
                html = report.write(scan_existing=False).read_text(encoding="utf-8")
                self.assertTrue(all(path.name in html for path in paths))
                self.assertEqual(html.count('<script type="application/json"'), 3)
                self.assertTrue(all(f'"values":["{name}"]' in html
                                    for name in ("durations", "ranks", "gaps")))
            write.assert_called_once()
            self.assertEqual(log.info.call_count, 3)


    def test_save_plotly_batch_propagates_write_failure(self) -> None:
        log = Mock()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corners_durations.png"
            with patch("visualizations.output.pio.write_images", side_effect=RuntimeError("failed")):
                with self.assertRaisesRegex(RuntimeError, "failed"):
                    save_plotly_batch([go.Figure()], [path], log, width=1920, height=1080)
            log.info.assert_not_called()


    def test_driver_linestyle_uses_camera_and_safe_defaults(self) -> None:
        self.assertEqual(driver_linestyle(2025, 1), "solid")
        self.assertEqual(driver_linestyle(2025, 22), "dashed")
        self.assertEqual(driver_linestyle(1900, 99), "solid")
