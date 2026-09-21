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


_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "template.html"


def _render_template(**values: str) -> str:
    html = _TEMPLATE_PATH.read_text(encoding="utf-8")
    for name, value in values.items():
        html = html.replace(f"@@{name.upper()}@@", value)
    return html


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

        html = _render_template(
            event_name=event_name,
            session_name=session_name,
            generated=generated,
            nav="".join(nav),
            body="".join(body),
            plotly_js=plotly_js,
        )
        html = organize_session_report_html(html, str(getattr(self.session, "name", "")))
        target.write_text(html, encoding="utf-8")
        if output_path is None and event is not None:
            try:
                expected = (
                    str(getattr(event, "year")),
                    f'{getattr(event, "RoundNumber")}_{getattr(event, "Location")}',
                    str(getattr(self.session, "name")).replace(" ", ""),
                )
                if self.report_dir.parts[-3:] == expected:
                    from visualizations.report_index import build_index
                    build_index(self.report_dir.parents[2])
            except (AttributeError, IndexError):
                pass
        return target


def _plotly_js() -> str:
    """Return the bundled Plotly runtime, without a network dependency."""

    from plotly.offline import get_plotlyjs

    return get_plotlyjs()
