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
from visualizations.report_layout import PRACTICE_SECTIONS, RACE_SECTIONS, organize_session_report_html
from unittest.mock import MagicMock, patch
from visualizations.output import save_matplotlib, save_plotly


class SessionReportTest(unittest.TestCase):
    def test_unknown_outputs_are_neither_saved_nor_scanned(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with SessionReport(SimpleNamespace(name="Practice 1"), root) as report:
                unknown = root / "unknown.png"
                figure = MagicMock()
                with patch("visualizations.output.plt.close") as close:
                    save_matplotlib(figure, unknown, MagicMock())
                figure.savefig.assert_not_called()
                close.assert_called_once_with(figure)
                save_plotly(figure, unknown, MagicMock(), width=640, height=640)
                figure.write_image.assert_not_called()
                unknown.write_bytes(b"old image")
                report.scan_images()
                self.assertEqual([], report._ordered_items())

    def test_fresh_generation_does_not_reuse_stale_start_images(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "speed_first_10s.png").write_bytes(b"old fastest lap")
            report = SessionReport(SimpleNamespace(name="Race"), root)
            html = report.write(scan_existing=False).read_text()
            self.assertNotIn("speed_first_10s.png", html)

    def test_sprint_qualifying_has_exactly_26_declared_cards(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "SprintQualifying"
            output.mkdir()
            report = SessionReport(SimpleNamespace(name="Sprint Qualifying"), output)
            for _, _, entries in QUALIFYING_SECTIONS:
                for key, _ in entries:
                    path = root / "tyres.png" if key == "weekend tyres" else output / (key.replace(" ", "_") + ".png")
                    path.write_bytes(b"placeholder")
                    report.register_image(path)
            (output / "sector1time.png").write_bytes(b"obsolete")
            html = report.write().read_text()
            self.assertEqual(re.findall(r'<h3>\[(Q-\d+)\]', html),
                             [f"Q-{number:02}" for number in range(1, 27)])
            self.assertNotIn("additional-figures", html)
            self.assertNotIn("sector1time.png", html)

    def test_axis_range_controls_cover_race_qualifying_and_practice(self) -> None:
        cases = (
            ("Race", "gap_top_graph.png", "Race"),
            ("Sprint", "gap_top_graph.png", "Race"),
            ("Qualifying", "laptime_by_lap_number.png", "Run Volume"),
            ("Practice 1", "long_runs/SOFT.png", "Long Runs"),
        )
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for session_name, filename, expected_section in cases:
                with self.subTest(session=session_name):
                    output_dir = root / session_name
                    output_dir.mkdir()
                    line_path = output_dir / filename
                    line_path.parent.mkdir(parents=True, exist_ok=True)
                    line_path.write_bytes(b"placeholder")
                    telemetry_path = output_dir / "time_distance_delta.png"
                    telemetry_path.write_bytes(b"placeholder")
                    session = SimpleNamespace(
                        name=session_name,
                        event=SimpleNamespace(EventName="GP", Location="GP"),
                    )
                    report = SessionReport(session, output_dir)
                    line = go.Figure(data=[go.Scatter(x=[1, 2], y=[3, 4], mode="lines")])
                    report.register_plotly(line, line_path)
                    report.register_plotly(line, telemetry_path)

                    html = report.write().read_text(encoding="utf-8")

                    self.assertIn(f'data-report-section="{expected_section}"', html)
                    if session_name not in {"Race", "Sprint"}:
                        self.assertIn('data-report-section="Telemetry"', html)
                    self.assertIn("const lineChart = !table && !telemetry && !trackMap", html)
                    self.assertIn("figure.layout.xaxis = Object.assign", html)
                    self.assertIn('controls.className = "y-range-controls"', html)
                    self.assertIn('class="dual-range"', html)
                    self.assertIn('aria-label="Y minimum"', html)
                    self.assertIn('aria-label="Y maximum"', html)
                    self.assertIn("Y range", html)

    def test_practice_and_race_layouts_match_declared_order(self) -> None:
        for session_name, sections, prefix in (
            ("Practice 1", PRACTICE_SECTIONS, "P"),
            ("Race", RACE_SECTIONS, "R"),
        ):
            entries = [item for section in sections for item in section.items]
            cards = []
            for i, item in enumerate(reversed(entries)):
                title = "Tyres" if item.key in {"session tyres", "weekend tyres"} else item.key
                article_id = f"{item.key.replace(' ', '-')}-{i}"
                if item.key == "weekend tyres":
                    article_id = f"external-tyres-{i}"
                cards.append(f'<article id="{article_id}"><h3>{title}</h3></article>')
            result = organize_session_report_html('<nav></nav><main>' + ''.join(cards) + '</main>', session_name)
            expected = [f'[{prefix}-{i:02d}] {item.title}' for i, item in enumerate(entries, 1)
                        if prefix != "P" or i not in {14, 15, 16, 18}]
            self.assertEqual(re.findall(r'<h3>(.*?)</h3>', result), expected)
            self.assertEqual(organize_session_report_html(result, session_name), result)

    def test_qualifying_spec_numbers_preserve_content_and_are_idempotent(self) -> None:
        original = (
            '<nav>old navigation</nav><main>'
            '<article class="figure-card" id="timing-2"><h3>Laptime By Timing</h3>'
            '<script type="application/json">{"data":[]}</script></article>'
            '<article id="weather"><h3>Air Temp</h3></article>'
            '<article id="unknown"><h3>Unknown</h3></article></main>'
        )
        numbered = organize_qualifying_report_html(original)
        self.assertIn('<h3>[Q-05] 時刻別のラップタイム推移</h3>', numbered)
        self.assertIn('<h3>[Q-23] 気温の推移</h3>', numbered)
        self.assertNotIn('<article id="unknown">', numbered)
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
                    self.assertEqual('[Q-09] 自己最速ラップの全開率' in html, 'Qualifying' in name)

    def test_report_contains_interactive_and_static_items_in_one_file(self) -> None:
        with TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "Qualifying"
            output_dir.mkdir()
            static_path = output_dir / "air_temp.png"
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
                go.Figure(data=[go.Scatter(x=[1, 2], y=[3, 4], mode="lines")]),
                interactive_path,
            )
            report.deactivate()
            self.assertIsNone(current_report())
            report_path = report.write(extra_paths=(external,))

            html = report_path.read_text(encoding="utf-8")
            self.assertIn("id=\"summary\"", html)
            self.assertNotIn("id=\"additional-figures\"", html)
            self.assertIn("plotly-container", html)
            self.assertIn(".plotly-container.qualifying-best", html)
            self.assertIn("data:image/png;base64,", html)
            self.assertIn("zoomable-image", html)
            self.assertNotIn('data-image-path=', html)
            self.assertIn('new Blob([bytes], {type: "image/png"})', html)
            self.assertIn('window.open(url, "_blank", "noopener,noreferrer")', html)
            self.assertIn('value="${initialLow}"', html)
            self.assertIn('value="${initialHigh}"', html)
            self.assertIn("tyres.png", html)
            self.assertIn('data-report-section="Run Volume"', html)
            self.assertIn("const lineChart", html)
            self.assertIn('controls.className = "y-range-controls"', html)
            self.assertIn('class="dual-range"', html)
            self.assertIn('output.value = `${low.toFixed(3)} – ${high.toFixed(3)}`', html)
            self.assertIn('slider.addEventListener("input", applyYRange)', html)
            self.assertIn('"yaxis.range": range', html)
            self.assertIn("rangeslider", html)
            self.assertNotIn("figure.layout.yaxis.rangeslider", html)
            self.assertIn('node.on("plotly_buttonclicked"', html)
            self.assertIn('window.Plotly.restyle(node, {visible}, [index])', html)
            self.assertIn('axisUpdate["yaxis.range"]', html)
            self.assertIn("const reverseYAxis", html)
            self.assertIn("const descendingYAxisRange", html)
            self.assertIn("const trackMap", html)
            self.assertIn("scrollZoom: trackMap", html)
            self.assertIn("const explicitYAxisRange", html)
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
            self.assertNotIn('data-plotly-source="figure-data-telemetry-shift-on-track"', html)
            self.assertNotIn("1_VER.png", html)
            self.assertNotIn("11_PER.png", html)
            self.assertIn('id="telemetry-comparison"', html)

    def test_interactive_telemetry_replaces_static_category_images(self) -> None:
        with TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "Qualifying"
            static_path = output_dir / "brake" / "1-5.png"
            static_path.parent.mkdir(parents=True)
            static_path.write_bytes(b"placeholder")
            interactive_path = output_dir / "time_distance_delta.png"
            interactive_path.write_bytes(b"placeholder")

            session = SimpleNamespace(
                name="Qualifying",
                event=SimpleNamespace(EventName="GP", Location="GP"),
            )
            report = SessionReport(session, output_dir)
            report.register_image(static_path)
            report.register_plotly(go.Figure(data=[go.Scatter(x=[0, 1], y=[0, 1])]), interactive_path)
            html = report.write().read_text(encoding="utf-8")

            self.assertIn('data-plotly-source="figure-data-telemetry-time-distance-delta"', html)
            self.assertNotIn("1-5.png", html)

    def test_report_can_be_written_outside_the_image_directory(self) -> None:
        with TemporaryDirectory() as temporary:
            image_dir = Path(temporary) / "images/session"
            report_dir = Path(temporary) / "reports/session"
            image_path = image_dir / "air_temp.png"
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
            self.assertIn("air_temp.png", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
