"""Graph-data embedding preserves the remaining static session chart data."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

import matplotlib.dates as dates
import matplotlib.pyplot as plt
import pandas as pd
from fastf1.core import Laps

from f1_explorer.visualizations.embedded_matplotlib import embed_matplotlib
from f1_explorer.visualizations.output import save_matplotlib
from f1_explorer.visualizations.report import SessionReport
from f1_explorer.visualizations.race import tyres


class EmbeddedMatplotlibTest(unittest.TestCase):
    def test_dates_lines_missing_samples_and_axis_direction(self):
        fig, ax = plt.subplots()
        try:
            times = pd.date_range("2026-09-30T12:00:00", periods=3, freq="min")
            ax.plot(times, [1, float("nan"), 3], color="red", linestyle="--", label="AAA")
            ax.legend()
            ax.invert_yaxis()
            ax.set_xlabel("Time [UTC]")
            result = embed_matplotlib(fig)
            self.assertEqual(result.data[0].line.dash, "dash")
            self.assertEqual(pd.Timestamp(result.data[0].x[0]), pd.Timestamp(times[0], tz="UTC"))
            self.assertEqual(list(result.layout.yaxis.range), list(ax.get_ylim()))
            self.assertIn("null", result.to_json())
            self.assertEqual(result.layout.xaxis.type, "date")
            self.assertTrue(result.data[0].showlegend)
        finally:
            plt.close(fig)

    def test_map_segments_sector_markers_and_labels(self):
        fig, ax = plt.subplots()
        try:
            ax.plot([0, 1, 2], [0, 2, 0], color="red")
            ax.text(1, 2, "1", color="blue")
            ax.scatter([1], [2], s=150, facecolors="white", edgecolors="#00a6ff")
            ax.annotate("S1→S2", (1, 2), xytext=(7, 7), textcoords="offset points")
            ax.set_aspect("equal")
            ax.axis("off")
            result = embed_matplotlib(fig)
            self.assertEqual(list(result.data[0].x), [0, 1, 2])
            self.assertEqual(list(result.data[1].x), [1])
            self.assertEqual([text.text for text in result.layout.annotations], ["1", "S1→S2"])
            self.assertEqual(result.layout.annotations[1].xshift, 7)
            self.assertEqual(result.layout.yaxis.scaleanchor, "x")
            self.assertFalse(result.layout.xaxis.visible)
        finally:
            plt.close(fig)

    def test_tyre_history_embeds_bars_stint_boundaries_and_labels_without_png(self):
        laps = Laps(pd.DataFrame({
            "DriverNumber": ["1"] * 3, "LapNumber": [1, 2, 3], "Position": [1] * 3,
            "Compound": ["SOFT"] * 3, "Stint": [1, 1, 2], "TyreLife": [1, 2, 5],
            "FreshTyre": [True, True, False],
        }))
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with SessionReport(SimpleNamespace(name="Race"), root) as report:
                with patch("matplotlib.figure.Figure.savefig") as save:
                    tyres(Mock(), str(root / "tyres.png"), laps)
                save.assert_not_called()
                self.assertEqual(list(root.glob("*.png")), [])
                import json
                data = json.loads(report._ordered_items()[0].figure_json)
                self.assertEqual(len(data["layout"]["shapes"]), 3)
                self.assertEqual([text["text"] for text in data["layout"]["annotations"]], ["1 N", "2", "5 U"])
                self.assertEqual(data["layout"]["yaxis"]["ticktext"], ["1"])
                html = report.write(scan_existing=False).read_text()
                self.assertTrue('data-plotly-source=' in html)
                self.assertFalse('<img class="zoomable-image"' in html)
                self.assertEqual(report.image_paths(), ())

    def test_weather_output_embeds_graph_without_image_rendering(self):
        from f1_explorer.visualizations.weather import plot_weather

        session = SimpleNamespace(name="Practice 1", date=pd.Timestamp("2026-09-30"),
                                  weather_data=pd.DataFrame({
                                      "Time": pd.to_timedelta([0, 60], unit="s"), "Rainfall": [0, 1],
                                  }))
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with SessionReport(session, root) as report:
                with patch("matplotlib.figure.Figure.savefig") as save:
                    plot_weather(session, Mock(), "Rainfall", str(root / "rainfall.png"))
                save.assert_not_called()
                self.assertEqual(list(root.glob("*.png")), [])
                self.assertEqual(len(report._ordered_items()), 1)

    def test_unsupported_artist_fails_and_closes_figure(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            fig, ax = plt.subplots()
            ax.imshow([[1, 2], [3, 4]])
            with SessionReport(SimpleNamespace(name="Practice 1"), root):
                with self.assertRaisesRegex(ValueError, "Raster artists"):
                    save_matplotlib(fig, root / "rainfall.png", Mock())
            self.assertFalse(plt.fignum_exists(fig.number))
