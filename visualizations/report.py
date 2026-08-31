"""Generate a self-contained, offline HTML report for one session.

The report collector is intentionally additive: existing PNG files continue to
be written, while Plotly figures are captured for interactive rendering and
other images are embedded as static fallbacks.
"""

from __future__ import annotations

import base64
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import re
from typing import Any, Iterable


_CURRENT_REPORT: ContextVar["SessionReport | None"] = ContextVar(
    "f1_explorer_current_report", default=None
)

_SECTION_ORDER = (
    "Summary",
    "Run Volume",
    "Short Runs",
    "Long Runs",
    "Telemetry",
    "Race",
    "Tyres",
    "Weather",
    "Static Graphs",
)


@dataclass(slots=True)
class ReportItem:
    """One graph or image displayed in the report."""

    path: Path
    title: str
    section: str
    anchor: str
    figure_json: str | None = None

    @property
    def interactive(self) -> bool:
        return self.figure_json is not None


def current_report() -> "SessionReport | None":
    """Return the report active for the current analysis context."""

    return _CURRENT_REPORT.get()


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return value or "figure"


def _section_for(relative_path: Path) -> str:
    parts = [part.lower() for part in relative_path.parts]
    name = relative_path.stem.lower()
    if "long_run" in name or "long_runs" in parts:
        return "Long Runs"
    if any(key in name or key in parts for key in ("telemetry", "speed_distance", "speed_on_track", "shift_on_track", "throttle", "brake", "drs")):
        return "Telemetry"
    if any(key in name for key in ("weather", "air_temp", "track_temp", "wind_speed", "rainfall")):
        return "Weather"
    if any(key in name for key in ("lap_number", "laptime", "pit_time", "pit")):
        return "Run Volume"
    if any(key in name for key in ("tyre", "tire")):
        return "Tyres"
    if any(key in name for key in ("position", "gap", "speed_first", "speed_until", "race")):
        return "Race"
    if any(key in name for key in ("best", "segment", "flat_out", "ideal", "gear", "time_distance")):
        return "Short Runs"
    return "Static Graphs"


def _title_for(relative_path: Path) -> str:
    words = re.sub(r"[_-]+", " ", relative_path.stem).strip()
    return words.title() or relative_path.name


def _collapsible_group_for(relative_path: Path) -> str | None:
    """Return the track-image group name for driver-by-driver plots."""

    parent = relative_path.parent.name.lower()
    if parent in {"shift_on_track", "speed_on_track"}:
        return parent
    return None


class SessionReport:
    """Collect graph outputs and write one self-contained HTML document."""

    def __init__(self, session: Any, output_dir: str | Path):
        self.session = session
        self.output_dir = Path(output_dir)
        self._items: dict[str, ReportItem] = {}
        self._anchor_counts: dict[str, int] = {}
        self._token: Token[SessionReport | None] | None = None

    def activate(self) -> None:
        """Make this collector visible to the shared output helpers."""

        if self._token is None:
            self._token = _CURRENT_REPORT.set(self)

    def deactivate(self) -> None:
        """Stop collecting figures for this report."""

        if self._token is not None:
            _CURRENT_REPORT.reset(self._token)
            self._token = None

    def __enter__(self) -> "SessionReport":
        self.activate()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.deactivate()

    def _relative(self, path: str | Path) -> Path:
        candidate = Path(path).resolve()
        try:
            return candidate.relative_to(self.output_dir.resolve())
        except ValueError:
            # Keep artifacts such as the weekend-level tyre chart distinct
            # from a session-level file with the same basename.
            return Path("__external__") / candidate.name

    def _is_race_session(self) -> bool:
        return str(getattr(self.session, "name", "")).strip().lower() in {
            "race", "sprint", "sprint race",
        }

    def _add(self, path: str | Path, *, figure_json: str | None = None) -> None:
        candidate = Path(path).resolve()
        if not candidate.is_file():
            return
        if self._is_race_session() and candidate.name == "laptime_by_timing.png":
            return
        relative = self._relative(candidate)
        key = relative.as_posix()
        section = _section_for(relative)
        title = _title_for(relative)
        anchor_base = _slug(f"{section}-{relative.with_suffix('').as_posix()}")
        count = self._anchor_counts.get(anchor_base, 0)
        self._anchor_counts[anchor_base] = count + 1
        anchor = anchor_base if count == 0 else f"{anchor_base}-{count + 1}"
        existing = self._items.get(key)
        if existing is not None and existing.figure_json is not None and figure_json is None:
            return
        self._items[key] = ReportItem(candidate, title, section, anchor, figure_json)

    def register_plotly(self, figure: Any, path: str | Path) -> None:
        """Register a Plotly figure while preserving its normal PNG output."""

        figure_json = figure.to_json(validate=False, pretty=False)
        self._add(path, figure_json=figure_json)

    def register_image(self, path: str | Path) -> None:
        """Register an existing image as a static report item."""

        self._add(path)

    def scan_images(self, extra_paths: Iterable[str | Path] = ()) -> None:
        """Add PNGs not already registered by a save helper."""

        if self.output_dir.is_dir():
            for path in sorted(self.output_dir.rglob("*.png")):
                self.register_image(path)
        for path in extra_paths:
            self.register_image(path)

    def _ordered_items(self) -> list[ReportItem]:
        order = {section: index for index, section in enumerate(_SECTION_ORDER)}
        return sorted(
            self._items.values(),
            key=lambda item: (order.get(item.section, len(order)), item.path.as_posix()),
        )

    def write(self, output_path: str | Path | None = None, *, extra_paths: Iterable[str | Path] = ()) -> Path:
        """Write an offline report and return its path."""

        self.scan_images(extra_paths)
        target = Path(output_path) if output_path is not None else self.output_dir / "report.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        items = self._ordered_items()
        plotly_js = _plotly_js()
        session_name = escape(str(getattr(self.session, "name", "Session")))
        event = getattr(self.session, "event", None)
        event_name = escape(str(getattr(event, "EventName", getattr(event, "Location", ""))))
        generated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        sections: dict[str, list[ReportItem]] = {section: [] for section in _SECTION_ORDER}
        for item in items:
            sections.setdefault(item.section, []).append(item)

        nav = [f'<a href="#summary">Summary</a>']
        body: list[str] = []
        for section in _SECTION_ORDER[1:]:
            section_items = sections.get(section, [])
            if not section_items:
                continue
            section_anchor = _slug(section)
            nav.append(f'<a href="#{section_anchor}">{escape(section)}</a>')
            body.append(f'<section class="report-section" id="{section_anchor}"><h2>{escape(section)}</h2>')
            groups: dict[str | None, list[ReportItem]] = {}
            for item in section_items:
                groups.setdefault(_collapsible_group_for(self._relative(item.path)), []).append(item)
            for group_name, group_items in groups.items():
                if group_name is not None:
                    group_title = _title_for(Path(group_name))
                    driver_label = "driver" if len(group_items) == 1 else "drivers"
                    body.append(
                        f'<details class="figure-group"><summary>{escape(group_title)} '
                        f'({len(group_items)} {driver_label})</summary><div class="figure-group-content">'
                    )
                for item in group_items:
                    body.append(f'<article class="figure-card" id="{escape(item.anchor)}"><h3>{escape(item.title)}</h3>')
                    if item.interactive:
                        data_id = f"figure-data-{_slug(item.anchor)}"
                        safe_json = item.figure_json.replace("<", "\\u003c") if item.figure_json else "{}"
                        is_table = '"type":"table"' in item.figure_json
                        kind = " table" if is_table else ""
                        body.append(f'<div class="plotly-container{kind}" data-plotly-source="{escape(data_id)}"></div>')
                        body.append(f'<script type="application/json" id="{escape(data_id)}">{safe_json}</script>')
                    else:
                        encoded = base64.b64encode(item.path.read_bytes()).decode("ascii")
                        source_url = escape(item.path.as_uri(), quote=True)
                        body.append(f'<img class="zoomable-image" loading="lazy" src="data:image/png;base64,{encoded}" data-image-path="{source_url}" alt="{escape(item.title)}" title="Click to open the image in a new tab">')
                    body.append(f'<p class="source">{escape(item.path.name)}</p></article>')
                if group_name is not None:
                    body.append('</div></details>')
            body.append("</section>")

        html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>F1 Explorer — {event_name} {session_name}</title>
<style>
:root {{ color-scheme: light; font-family: system-ui, -apple-system, sans-serif; }}
*, *::before, *::after {{ box-sizing: border-box; }}
body {{ margin: 0; color: #202124; background: #fafafa; }}
header {{ padding: 1.5rem 2rem; background: #18202a; color: white; }}
header h1 {{ margin: 0 0 .35rem; font-size: 1.55rem; }}
header p {{ margin: .2rem 0; color: #d7e0ea; }}
nav {{ position: sticky; top: 0; z-index: 5; display: flex; flex-wrap: wrap; gap: .65rem 1rem; padding: .7rem 2rem; background: white; border-bottom: 1px solid #d9dee5; }}
nav a {{ color: #145da0; text-decoration: none; font-weight: 600; }}
main {{ width: 100%; max-width: 1500px; margin: 0 auto; padding: 1rem 2rem 4rem; }}
.report-section {{ scroll-margin-top: 4rem; margin: 2rem 0 3rem; }}
.report-section h2 {{ border-bottom: 2px solid #b8c4d1; padding-bottom: .4rem; }}
.figure-card {{ min-width: 0; max-width: 100%; overflow-x: hidden; scroll-margin-top: 4rem; margin: 1.4rem 0 2rem; padding: 1rem; background: white; border: 1px solid #e0e4e8; border-radius: 8px; box-shadow: 0 1px 3px #0000000d; }}
.figure-card h3 {{ margin-top: 0; }}
.figure-card img {{ display: block; width: auto; max-width: 100%; height: auto; }}
.figure-group {{ margin: 1.4rem 0 2rem; }}
.figure-group > summary {{ cursor: pointer; padding: .8rem 1rem; background: white; border: 1px solid #b8c4d1; border-radius: 8px; color: #145da0; font-weight: 700; list-style-position: inside; }}
.figure-group[open] > summary {{ border-radius: 8px 8px 0 0; }}
.figure-group-content {{ padding-top: .1rem; }}
.zoomable-image {{ cursor: zoom-in; }}
.plotly-container {{ min-height: 640px; height: 640px; width: 100%; max-width: 100%; overflow-x: hidden; }}
.plotly-container.table {{ min-height: 900px; height: 900px; }}
.source {{ color: #687582; font-size: .8rem; margin-bottom: 0; }}
</style></head><body>
<header id="summary"><h1>F1 Explorer — {event_name} / {session_name}</h1><p>Generated: {generated}</p><p>Interactive figures render in your browser; existing PNG outputs remain available beside this report.</p><p>For vertical zoom, choose Box Select in the graph toolbar and drag across the desired Y range. Use Reset Axes to restore the view.</p></header>
<nav>{''.join(nav)}</nav><main>{''.join(body)}</main>
<script>{plotly_js}</script>
<script>
(function() {{
  const render = (node) => {{
    if (node.dataset.rendered) return;
    const source = document.getElementById(node.dataset.plotlySource);
    if (!source || !window.Plotly) return;
    const figure = JSON.parse(source.textContent);
    figure.layout = Object.assign({{}}, figure.layout || {{}});
    const table = Array.isArray(figure.data) && figure.data.some((trace) => trace.type === "table");
    const minimumHeight = table ? 900 : 640;
    figure.layout.height = Math.max(Number(figure.layout.height) || 0, minimumHeight);
    figure.layout.autosize = true;
    const titleText = figure.layout.title && typeof figure.layout.title.text === "string" ? figure.layout.title.text : "";
    const reverseYAxis = !table && figure.layout.yaxis && typeof figure.layout.yaxis === "object" &&
      (figure.layout.yaxis.autorange === "reversed" || /lap time/i.test(titleText));
    const explicitYAxisRange = reverseYAxis && Array.isArray(figure.layout.yaxis.range) && figure.layout.yaxis.range.length === 2;
    if (reverseYAxis) {{
      figure.layout.yaxis = Object.assign({{}}, figure.layout.yaxis, explicitYAxisRange ? {{autorange: false}} : {{autorange: "reversed"}});
    }}
    if (!table && figure.layout.yaxis && typeof figure.layout.yaxis === "object") {{
      figure.layout.yaxis = Object.assign({{}}, figure.layout.yaxis, {{
        rangeslider: Object.assign({{}}, figure.layout.yaxis.rangeslider || {{}}, {{visible: true}}),
      }});
      figure.layout.selectdirection = "v";
    }}
    window.Plotly.newPlot(node, figure.data || [], figure.layout || {{}}, {{responsive: true, displaylogo: false}}).then(() => {{
      const allYValues = (figure.data || []).flatMap((trace) => Array.isArray(trace.y) ? trace.y : [])
        .filter((value) => typeof value === "number" && Number.isFinite(value));
      node.on("plotly_selected", (event) => {{
        const values = (event && event.points ? event.points : [])
          .map((point) => point.y)
          .filter((value) => typeof value === "number" && Number.isFinite(value));
        if (values.length < 2) return;
        const range = reverseYAxis ? [Math.max(...values), Math.min(...values)] : [Math.min(...values), Math.max(...values)];
        window.Plotly.relayout(node, {{"yaxis.autorange": false, "yaxis.range": range}});
      }});
      node.on("plotly_relayout", (event) => {{
        if (!reverseYAxis || !event || event["yaxis.autorange"] !== true || allYValues.length < 2) return;
        window.Plotly.relayout(node, {{
          "yaxis.autorange": false,
          "yaxis.range": [Math.max(...allYValues), Math.min(...allYValues)],
        }});
      }});
    }});
    node.dataset.rendered = "1";
  }};
  const nodes = document.querySelectorAll("[data-plotly-source]");
  if ("IntersectionObserver" in window) {{
    const observer = new IntersectionObserver((entries) => entries.forEach((entry) => {{ if (entry.isIntersecting) {{ render(entry.target); observer.unobserve(entry.target); }} }}), {{rootMargin: "300px"}});
    nodes.forEach((node) => observer.observe(node));
  }} else {{ nodes.forEach(render); }}
  document.querySelectorAll(".zoomable-image").forEach((image) => {{
    image.addEventListener("click", () => window.open(image.dataset.imagePath || image.currentSrc || image.src, "_blank", "noopener,noreferrer"));
  }});
}})();
</script></body></html>
"""
        target.write_text(html, encoding="utf-8")
        return target


def _plotly_js() -> str:
    """Return the bundled Plotly runtime, without a network dependency."""

    from plotly.offline import get_plotlyjs

    return get_plotlyjs()
