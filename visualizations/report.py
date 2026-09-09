"""Generate a self-contained, offline HTML report for one session.

Declared PNG outputs remain available, while Plotly figures are captured for
interactive rendering and static images are embedded. Fresh analysis runs do
not scan old outputs; an explicit rebuild can still import declared PNGs.
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

from visualizations.report_layout import organize_session_report_html, is_spec_output


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
    if any(key in name or key in parts for key in ("telemetry", "speed_distance", "speed_on_track", "shift_on_track", "time_distance_delta", "throttle", "brake", "drs")):
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


def _is_interactive_telemetry_path(relative_path: Path) -> bool:
    """Return whether a static telemetry image is replaced in the report."""

    return any(
        part.lower() in {
            "brake",
            "shift_on_track",
            "speed_distance",
            "speed_on_track",
            "throttle",
            "time_distance_delta",
        }
        for part in relative_path.parts[:-1]
    )


class SessionReport:
    """Collect graph outputs and write one self-contained HTML document."""

    def __init__(
        self,
        session: Any,
        output_dir: str | Path,
        *,
        report_dir: str | Path | None = None,
    ):
        self.session = session
        self.output_dir = Path(output_dir)
        self.report_dir = Path(report_dir) if report_dir is not None else self.output_dir
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

    def accepts_output(self, path: str | Path) -> bool:
        return is_spec_output(str(getattr(self.session, "name", "")), self._relative(path))

    def _add(self, path: str | Path, *, figure_json: str | None = None) -> None:
        candidate = Path(path).resolve()
        if not candidate.is_file():
            return
        relative = self._relative(candidate)
        if not self.accepts_output(candidate):
            return
        if self._is_race_session() and candidate.name == "laptime_by_timing.png":
            return
        if figure_json is None and _is_interactive_telemetry_path(relative):
            return
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
        items = list(self._items.values())
        return sorted(
            items,
            key=lambda item: (order.get(item.section, len(order)), item.path.as_posix()),
        )

    def write(self, output_path: str | Path | None = None, *, extra_paths: Iterable[str | Path] = (),
              scan_existing: bool = True) -> Path:
        """Write an offline report and return its path."""

        if scan_existing:
            self.scan_images(extra_paths)
        else:
            for path in extra_paths:
                self.register_image(path)
        target = Path(output_path) if output_path is not None else self.report_dir / "report.html"
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
            for item in section_items:
                body.append(f'<article class="figure-card" id="{escape(item.anchor)}"><h3>{escape(item.title)}</h3>')
                if item.interactive:
                    data_id = f"figure-data-{_slug(item.anchor)}"
                    safe_json = item.figure_json.replace("<", "\\u003c") if item.figure_json else "{}"
                    is_table = '"type":"table"' in item.figure_json
                    is_qualifying_best = '"f1ExplorerKind":"qualifyingBest"' in item.figure_json
                    is_race_laptime = '"f1ExplorerKind":"raceLapTime"' in item.figure_json
                    is_speed_chart = ('"f1ExplorerKind":"qualifyingSpeed"' in item.figure_json or
                                      '"f1ExplorerKind":"practiceSpeed"' in item.figure_json)
                    kind = (" table" if is_table else "") + (" qualifying-best" if is_qualifying_best else "")
                    if is_race_laptime:
                        body.append('''<div class="r02-rules"><strong>マーカーの見方</strong><table><thead><tr><th>ラップ開始時の状況</th><th>クリーンラップ</th><th>非クリーンラップ</th></tr></thead><tbody><tr><th>前走車とのギャップが2.000秒以内</th><td><span class="r02-swatch r02-close-clean"></span>白塗り＋チームカラー枠</td><td><span class="r02-swatch r02-close-unclean"></span>白塗り＋細い黒枠</td></tr><tr><th>2.000秒超またはギャップ不明</th><td><span class="r02-swatch r02-normal-clean"></span>チームカラー塗り</td><td><span class="r02-swatch r02-normal-unclean"></span>チームカラー塗り＋細い黒枠</td></tr></tbody></table><p>前走車は順位ではなく、ラップ開始時点で直前にコントロールラインを通過した車です。非クリーンラップにはSC・VSC・黄旗、ピットイン／アウト、計測精度不足などを含みます。判定はラップ開始時点を基準とし、ラップ途中で追いついたケースは含みません。</p></div>''')
                    if is_speed_chart:
                        body.append('''<div class="speed-rules"><strong>速度ラベルの見方</strong><p>太字は、計測地点で前走車が0秒超〜2.000秒以内にいたことを示します。スリップストリームによる速度向上の可能性を示すもので、因果関係を確定するものではありません。<code>SpeedST</code>はFastF1のデータに正確な計測位置・時刻がないため、太字判定の対象外です。Q-02の「トウあり」は太字、「トウなし」は通常表示です。ギャップ不明時も通常表示です。</p></div>''')
                    body.append(
                        f'<div class="plotly-container{kind}" data-plotly-source="{escape(data_id)}" '
                        f'data-report-section="{escape(item.section)}"></div>'
                    )
                    body.append(f'<script type="application/json" id="{escape(data_id)}">{safe_json}</script>')
                else:
                    encoded = base64.b64encode(item.path.read_bytes()).decode("ascii")
                    body.append(f'<img class="zoomable-image" loading="lazy" src="data:image/png;base64,{encoded}" alt="{escape(item.title)}" title="Click to open the image in a new tab">')
                body.append(f'<p class="source">{escape(item.path.name)}</p></article>')
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
.r02-rules {{ margin: 0 0 1rem; padding: .75rem 1rem; background: #f5f7fa; border: 1px solid #d9dee5; border-radius: 6px; font-size: .9rem; overflow-x: auto; }}
.r02-rules table {{ margin: .5rem 0; border-collapse: collapse; width: 100%; min-width: 620px; }}
.r02-rules th, .r02-rules td {{ padding: .35rem .5rem; border: 1px solid #d9dee5; text-align: left; vertical-align: middle; }}
.r02-rules th {{ background: #edf1f5; font-weight: 600; }}
.r02-rules p {{ margin: .6rem 0 0; color: #4d5966; }}
.r02-swatch {{ display: inline-block; width: .85rem; height: .85rem; margin-right: .35rem; vertical-align: -.1rem; border-radius: 50%; background: #58708a; }}
.r02-close-clean {{ background: white; border: 2px solid #58708a; }}
.r02-close-unclean {{ background: white; border: 1px solid #111; }}
.r02-normal-unclean {{ border: 1px solid #111; }}
.speed-rules {{ margin: 0 0 1rem; padding: .65rem 1rem; background: #f5f7fa; border: 1px solid #d9dee5; border-radius: 6px; font-size: .9rem; }}
.speed-rules p {{ margin: .4rem 0 0; color: #4d5966; }}
.figure-card img {{ display: block; width: auto; max-width: 100%; height: auto; }}
.zoomable-image {{ cursor: zoom-in; }}
.plotly-container {{ min-height: 640px; height: 640px; width: 100%; max-width: 100%; overflow-x: hidden; }}
.plotly-container.table {{ min-height: 900px; height: 900px; }}
.plotly-container.qualifying-best {{ min-height: 1500px; height: 1500px; }}
.y-range-controls {{ display: grid; grid-template-columns: auto minmax(8rem, 1fr) auto; align-items: center; gap: .75rem; margin: 0 3rem .5rem 4rem; color: #4d5966; font-size: .82rem; }}
.y-range-values {{ min-width: 12rem; text-align: right; font-variant-numeric: tabular-nums; }}
.dual-range {{ position: relative; height: 1.4rem; }}
.dual-range input[type="range"] {{ position: absolute; inset: 0; width: 100%; margin: 0; background: transparent; pointer-events: none; appearance: none; -webkit-appearance: none; }}
.dual-range input[type="range"]::-webkit-slider-runnable-track {{ height: 4px; border-radius: 2px; background: #c7d1dc; }}
.dual-range input[type="range"]::-moz-range-track {{ height: 4px; border-radius: 2px; background: #c7d1dc; }}
.dual-range input[type="range"]::-webkit-slider-thumb {{ width: 15px; height: 15px; margin-top: -5.5px; border: 1px solid #145da0; border-radius: 50%; background: #fff; pointer-events: auto; cursor: ew-resize; appearance: none; -webkit-appearance: none; }}
.dual-range input[type="range"]::-moz-range-thumb {{ width: 15px; height: 15px; border: 1px solid #145da0; border-radius: 50%; background: #fff; pointer-events: auto; cursor: ew-resize; }}
.source {{ color: #687582; font-size: .8rem; margin-bottom: 0; }}
</style></head><body>
<header id="summary"><h1>F1 Explorer — {event_name} / {session_name}</h1><p>Generated: {generated}</p><p>Interactive figures render in your browser; existing PNG outputs remain available beside this report.</p><p>Non-telemetry line charts provide X-axis filtering and Y-axis zoom controls.</p></header>
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
    const telemetry = node.dataset.reportSection === "Telemetry";
    const trackMap = figure.layout.meta && ["trackMap", "qualifyingTrackMap", "trackMapComparison"].includes(figure.layout.meta.f1ExplorerKind);
    const lineChart = !table && !telemetry && !trackMap && Array.isArray(figure.data) &&
      figure.data.some((trace) => (trace.type === "scatter" || trace.type === "scattergl") &&
        typeof trace.mode === "string" && trace.mode.includes("lines"));
    const qualifyingBest = figure.layout.meta && figure.layout.meta.f1ExplorerKind === "qualifyingBest";
    const minimumHeight = table ? 900 : 640;
    figure.layout.height = Math.max(Number(figure.layout.height) || 0, minimumHeight);
    figure.layout.autosize = true;
    const titleText = figure.layout.title && typeof figure.layout.title.text === "string" ? figure.layout.title.text : "";
    const configuredYAxisRange = figure.layout.yaxis && Array.isArray(figure.layout.yaxis.range) ? figure.layout.yaxis.range : [];
    const descendingYAxisRange = configuredYAxisRange.length === 2 &&
      Number(configuredYAxisRange[0]) > Number(configuredYAxisRange[1]);
    const reverseYAxis = !table && !trackMap && figure.layout.yaxis && typeof figure.layout.yaxis === "object" &&
      (figure.layout.yaxis.autorange === "reversed" || descendingYAxisRange || /lap time/i.test(titleText));
    const explicitYAxisRange = reverseYAxis && Array.isArray(figure.layout.yaxis.range) && figure.layout.yaxis.range.length === 2;
    if (reverseYAxis) {{
      figure.layout.yaxis = Object.assign({{}}, figure.layout.yaxis, explicitYAxisRange ? {{autorange: false}} : {{autorange: "reversed"}});
    }}
    const allYValues = (figure.data || []).flatMap((trace) => Array.isArray(trace.y) ? trace.y : [])
      .filter((value) => typeof value === "number" && Number.isFinite(value));
    if (lineChart) {{
      figure.layout.xaxis = Object.assign({{}}, figure.layout.xaxis || {{}}, {{
        rangeslider: Object.assign({{}}, (figure.layout.xaxis || {{}}).rangeslider || {{}}, {{visible: true}}),
      }});
      if (configuredYAxisRange.length !== 2 && allYValues.length >= 2) {{
        const low = Math.min(...allYValues), high = Math.max(...allYValues);
        const padding = (high - low || Math.max(Math.abs(high), 1)) * 0.02;
        figure.layout.yaxis = Object.assign({{}}, figure.layout.yaxis || {{}}, {{
          autorange: false,
          range: reverseYAxis ? [high + padding, low - padding] : [low - padding, high + padding],
        }});
      }}
    }}
    window.Plotly.newPlot(node, figure.data || [], figure.layout || {{}}, {{responsive: true, displaylogo: false, scrollZoom: trackMap}}).then(() => {{
      if (qualifyingBest) {{
        node.on("plotly_buttonclicked", (event) => {{
          const label = event && event.button ? event.button.label : "";
          const modes = {{
            "タイム": {{visible: [true, false, true], axis: true}},
            "最速比率": {{visible: [false, true, true], axis: true}},
          }};
          const mode = modes[label];
          if (!mode) return;
          // Keep the table visible below the selected bar trace.
          const updates = mode.visible.map((visible, index) =>
            window.Plotly.restyle(node, {{visible}}, [index])
          );
          Promise.all(updates).then(() => {{
            const values = label === "タイム" ? node.data[0].y : label === "最速比率" ? node.data[1].y : [];
            const finite = Array.isArray(values) ? values.filter((value) => Number.isFinite(Number(value))).map(Number) : [];
            const axisUpdate = {{"xaxis.visible": mode.axis, "yaxis.visible": mode.axis}};
            if (mode.axis && finite.length) {{
              const low = Math.min(...finite);
              const high = Math.max(...finite);
              const padding = Math.max((high - low) * 0.08, high * 0.01);
              axisUpdate["yaxis.autorange"] = false;
              axisUpdate["yaxis.range"] = [Math.max(0, low - padding), high + padding];
            }}
            window.Plotly.relayout(node, axisUpdate);
          }});
        }});
      }}
      if (lineChart && allYValues.length >= 2) {{
        const domainLow = Math.min(...allYValues);
        const domainHigh = Math.max(...allYValues);
        const span = domainHigh - domainLow || Math.max(Math.abs(domainHigh), 1);
        const padding = span * 0.02;
        const initialRange = configuredYAxisRange.length === 2 ? configuredYAxisRange :
          (node._fullLayout.yaxis.range || [domainLow - padding, domainHigh + padding]);
        const initialLow = Math.min(...initialRange);
        const initialHigh = Math.max(...initialRange);
        // Include explicit bounds (e.g. 60s even when all gaps are smaller).
        const minimum = Math.min(domainLow - padding, initialLow);
        const maximum = Math.max(domainHigh + padding, initialHigh);
        const controls = document.createElement("div");
        controls.className = "y-range-controls";
        controls.innerHTML = `<label>Y range</label><div class="dual-range"><input aria-label="Y minimum" type="range" min="${{minimum}}" max="${{maximum}}" step="any" value="${{initialLow}}"><input aria-label="Y maximum" type="range" min="${{minimum}}" max="${{maximum}}" step="any" value="${{initialHigh}}"></div><output class="y-range-values">${{initialLow.toFixed(3)}} – ${{initialHigh.toFixed(3)}}</output>`;
        node.parentNode.insertBefore(controls, node);
        const sliders = controls.querySelectorAll("input");
        const output = controls.querySelector("output");
        const applyYRange = () => {{
          let low = Number(sliders[0].value);
          let high = Number(sliders[1].value);
          if (low > high) [low, high] = [high, low];
          output.value = `${{low.toFixed(3)}} – ${{high.toFixed(3)}}`;
          const range = reverseYAxis ? [high, low] : [low, high];
          window.Plotly.relayout(node, {{"yaxis.autorange": false, "yaxis.range": range}});
        }};
        sliders.forEach((slider) => slider.addEventListener("input", applyYRange));
        node.on("plotly_relayout", () => {{
          const range = node._fullLayout.yaxis.range;
          const low = Math.min(...range), high = Math.max(...range);
          sliders.forEach((slider) => {{
            slider.min = Math.min(minimum, low);
            slider.max = Math.max(maximum, high);
          }});
          sliders[0].value = low;
          sliders[1].value = high;
          output.value = `${{low.toFixed(3)}} – ${{high.toFixed(3)}}`;
        }});
      }}
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
    image.addEventListener("click", () => {{
      const bytes = Uint8Array.from(atob(image.src.split(",")[1]), (char) => char.charCodeAt(0));
      const url = URL.createObjectURL(new Blob([bytes], {{type: "image/png"}}));
      window.open(url, "_blank", "noopener,noreferrer");
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    }});
  }});
}})();
</script></body></html>
"""
        html = organize_session_report_html(html, str(getattr(self.session, "name", "")))
        target.write_text(html, encoding="utf-8")
        return target


def _plotly_js() -> str:
    """Return the bundled Plotly runtime, without a network dependency."""

    from plotly.offline import get_plotlyjs

    return get_plotlyjs()
