"""Tests for the self-contained session report."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import plotly.graph_objects as go

from visualizations.report import SessionReport, current_report


class SessionReportTest(unittest.TestCase):
    def test_report_contains_interactive_and_static_items_in_one_file(self) -> None:
        with TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "Qualifying"
            output_dir.mkdir()
            static_path = output_dir / "long_runs" / "Soft.png"
            static_path.parent.mkdir()
            static_path.write_bytes(b"not-a-real-image")
            interactive_path = output_dir / "laptime_by_lap_number.png"
            interactive_path.write_bytes(b"placeholder")
            external = Path(temporary) / "tyres.png"
            external.write_bytes(b"weekend")

            session = SimpleNamespace(
                name="Qualifying",
                event=SimpleNamespace(EventName="Test <GP>", Location="Test"),
            )
            report = SessionReport(session, output_dir)
            report.activate()
            self.assertIs(current_report(), report)
            report.register_plotly(
                go.Figure(data=[go.Scatter(x=[1, 2], y=[3, 4])]),
                interactive_path,
            )
            report.deactivate()
            self.assertIsNone(current_report())
            report_path = report.write(extra_paths=(external,))

            html = report_path.read_text(encoding="utf-8")
            self.assertIn("id=\"summary\"", html)
            self.assertIn("id=\"long-runs\"", html)
            self.assertIn("plotly-container", html)
            self.assertIn("data:image/png;base64,", html)
            self.assertIn("zoomable-image", html)
            self.assertIn('data-image-path="file://', html)
            self.assertIn("window.open(image.dataset.imagePath || image.currentSrc || image.src", html)
            self.assertIn("tyres.png", html)
            self.assertIn("plotly_selected", html)
            self.assertIn("figure.layout.selectdirection = \"v\"", html)
            self.assertIn("const reverseYAxis", html)
            self.assertIn("const explicitYAxisRange", html)
            self.assertIn("reverseYAxis ? [Math.max(...values), Math.min(...values)]", html)
            self.assertIn('event["yaxis.autorange"] !== true', html)
            self.assertIn('"yaxis.range": [Math.max(...allYValues), Math.min(...allYValues)]', html)
            self.assertNotIn('<script src="https://', html)
            self.assertEqual(html.count("window.Plotly.newPlot"), 1)
            self.assertIn("box-sizing: border-box", html)
            self.assertIn("max-width: 100%", html)
            self.assertIn("overflow-x: hidden", html)

    def test_report_is_stable_and_escapes_embedded_figure_json(self) -> None:
        with TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "session"
            output_dir.mkdir()
            interactive_path = output_dir / "laptime_table.png"
            interactive_path.write_bytes(b"placeholder")
            figure = go.Figure(
                data=[go.Scatter(x=[1], y=["<script>alert(1)</script>"])]
            )
            session = SimpleNamespace(
                name="Practice 1",
                event=SimpleNamespace(EventName="GP", Location="GP"),
            )
            report = SessionReport(session, output_dir)
            report.register_plotly(figure, interactive_path)
            path = report.write()
            html = path.read_text(encoding="utf-8")
            self.assertNotIn("</script>alert(1)", html)
            self.assertIn(r"\\u003cscript\\u003e", json.dumps(html))

    def test_race_report_omits_laptime_by_timing(self) -> None:
        with TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "Race"
            output_dir.mkdir()
            timing_path = output_dir / "laptime_by_timing.png"
            timing_path.write_bytes(b"placeholder")
            session = SimpleNamespace(
                name="Race",
                event=SimpleNamespace(EventName="GP", Location="GP"),
            )
            report = SessionReport(session, output_dir)
            report.register_image(timing_path)

            html = report.write().read_text(encoding="utf-8")
            self.assertNotIn("laptime_by_timing.png", html)

    def test_driver_track_images_are_collapsible_by_plot_type(self) -> None:
        with TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "Qualifying"
            for directory, filename in (
                ("speed_on_track", "1_VER.png"),
                ("speed_on_track", "11_PER.png"),
                ("shift_on_track", "1_VER.png"),
            ):
                path = output_dir / directory / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"placeholder")

            session = SimpleNamespace(
                name="Qualifying",
                event=SimpleNamespace(EventName="GP", Location="GP"),
            )
            report = SessionReport(session, output_dir)
            html = report.write().read_text(encoding="utf-8")

            self.assertEqual(html.count('<details class="figure-group">'), 2)
            self.assertIn("Speed On Track (2 drivers)", html)
            self.assertIn("Shift On Track (1 driver)", html)
            self.assertIn('id="telemetry"', html)

    def test_interactive_telemetry_replaces_static_category_images(self) -> None:
        with TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "Qualifying"
            static_path = output_dir / "brake" / "1-5.png"
            static_path.parent.mkdir(parents=True)
            static_path.write_bytes(b"placeholder")
            interactive_path = output_dir / "brake.png"
            interactive_path.write_bytes(b"placeholder")

            session = SimpleNamespace(
                name="Qualifying",
                event=SimpleNamespace(EventName="GP", Location="GP"),
            )
            report = SessionReport(session, output_dir)
            report.register_image(static_path)
            report.register_plotly(go.Figure(data=[go.Scatter(x=[0, 1], y=[0, 1])]), interactive_path)
            html = report.write().read_text(encoding="utf-8")

            self.assertIn('data-plotly-source="figure-data-telemetry-brake"', html)
            self.assertNotIn("1-5.png", html)

    def test_report_can_be_written_outside_the_image_directory(self) -> None:
        with TemporaryDirectory() as temporary:
            image_dir = Path(temporary) / "images/session"
            report_dir = Path(temporary) / "reports/session"
            image_path = image_dir / "plot.png"
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(b"placeholder")
            session = SimpleNamespace(
                name="Practice 1",
                event=SimpleNamespace(EventName="GP", Location="GP"),
            )

            report = SessionReport(session, image_dir, report_dir=report_dir)
            path = report.write()

            self.assertEqual(path, report_dir / "report.html")
            self.assertTrue(path.is_file())
            self.assertIn("plot.png", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
