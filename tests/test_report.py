"""Tests for the self-contained session report."""

from __future__ import annotations

import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import plotly.graph_objects as go

from visualizations.report import SessionReport, current_report
from visualizations.qualifying_layout import QUALIFYING_SECTIONS, organize_qualifying_report_html


class SessionReportTest(unittest.TestCase):
    def test_qualifying_spec_numbers_preserve_content_and_are_idempotent(self) -> None:
        original = (
            '<nav>old navigation</nav><main>'
            '<article class="figure-card" id="timing-2"><h3>Laptime By Timing</h3>'
            '<script type="application/json">{"data":[]}</script></article>'
            '<article id="weather"><h3>Air Temp</h3></article>'
            '<article id="unknown"><h3>Unknown</h3></article></main>'
        )
        numbered = organize_qualifying_report_html(original)
        self.assertIn('<h3>[Q-11] 時刻別のラップタイム推移</h3>', numbered)
        self.assertIn('<h3>[Q-33] 気温の推移</h3>', numbered)
        self.assertIn('<article id="unknown"><h3>Unknown</h3></article>', numbered)
        self.assertIn('<script type="application/json">{"data":[]}</script>', numbered)
        self.assertIn('id="timing-2"', numbered)
        self.assertEqual(organize_qualifying_report_html(numbered), numbered)

    def test_qualifying_order_titles_links_and_spec_match(self) -> None:
        entries = [item for _, _, items in QUALIFYING_SECTIONS for item in items]
        html = '<nav></nav><main>' + ''.join(
            f'<article id="old-{i}"><h3>[Q-99] {name}</h3></article>'
            for i, (name, _) in reversed(list(enumerate(entries)))
        ) + '</main>'
        result = organize_qualifying_report_html(html)
        expected = [f'[Q-{i:02d}] {title}' for i, (_, title) in enumerate(entries, 1)]
        self.assertEqual(re.findall(r'<h3>(.*?)</h3>', result), expected)
        spec = (Path(__file__).resolve().parents[1] / 'specs/QUALIFYING.md').read_text()
        self.assertEqual(re.findall(r'^### (\[Q-\d+\] .*)$', spec, re.M), expected)
        self.assertEqual(re.findall(r'^## ([1-6]\. .*)$', spec, re.M),
                         [title for _, title, _ in QUALIFYING_SECTIONS])
        ids = re.findall(r'\bid="([^"]+)"', result)
        self.assertEqual(len(ids), len(set(ids)))
        for anchor in re.findall(r'href="#([^"]+)"', result):
            self.assertTrue(anchor == 'summary' or anchor in ids)

    def test_spec_numbers_are_only_added_to_qualifying_reports(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "flat_out.png"
            image.write_bytes(b"placeholder")
            for name in ("Qualifying", "Sprint Qualifying", "Race", "Practice 1"):
                with self.subTest(session=name):
                    report = SessionReport(SimpleNamespace(name=name), root)
                    html = report.write().read_text()
                    self.assertEqual('[Q-15] 自己最速ラップの全開率' in html, 'Qualifying' in name)

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
            self.assertIn("id=\"additional-figures\"", html)
            self.assertIn("plotly-container", html)
            self.assertIn("data:image/png;base64,", html)
            self.assertIn("zoomable-image", html)
            self.assertIn('data-image-path="file://', html)
            self.assertIn("window.open(image.dataset.imagePath || image.currentSrc || image.src", html)
            self.assertIn("tyres.png", html)
            self.assertIn("plotly_selected", html)
            self.assertIn("figure.layout.selectdirection = \"v\"", html)
            self.assertIn("const reverseYAxis", html)
            self.assertIn("const descendingYAxisRange", html)
            self.assertIn("const trackMap", html)
            self.assertIn("scrollZoom: trackMap", html)
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

    def test_driver_track_images_are_replaced_by_interactive_figures(self) -> None:
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

            speed_path = output_dir / "speed_on_track.png"
            shift_path = output_dir / "shift_on_track.png"
            speed_path.write_bytes(b"placeholder")
            shift_path.write_bytes(b"placeholder")

            session = SimpleNamespace(
                name="Qualifying",
                event=SimpleNamespace(EventName="GP", Location="GP"),
            )
            report = SessionReport(session, output_dir)
            figure = go.Figure(data=[go.Scatter(x=[0, 1], y=[0, 1])])
            report.register_plotly(figure, speed_path)
            report.register_plotly(figure, shift_path)
            html = report.write().read_text(encoding="utf-8")

            self.assertNotIn('<details class="figure-group">', html)
            self.assertIn('data-plotly-source="figure-data-telemetry-speed-on-track"', html)
            self.assertIn('data-plotly-source="figure-data-telemetry-shift-on-track"', html)
            self.assertNotIn("1_VER.png", html)
            self.assertNotIn("11_PER.png", html)
            self.assertIn('id="telemetry-comparison"', html)

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
