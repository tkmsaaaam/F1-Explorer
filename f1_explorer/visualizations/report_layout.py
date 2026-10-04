"""Declarative ordering and numbering for static session reports."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
import re
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LayoutItem:
    key: str
    title: str


@dataclass(frozen=True, slots=True)
class LayoutSection:
    anchor: str
    title: str
    items: tuple[LayoutItem, ...]


def _items(*values: tuple[str, str]) -> tuple[LayoutItem, ...]:
    return tuple(LayoutItem(*value) for value in values)


QUALIFYING_SECTIONS = (
    LayoutSection("results", "1. 結果の比較", _items(
        ("laptime", "予選区分別のベストラップ・セクタータイム比較"),
        ("speedfl", "ラップ条件・計測地点別の最高速度比較"),
    )),
    LayoutSection("run-history", "2. 走行履歴", _items(
        ("lap number by timing", "時刻別の走行ラップ履歴"),
        ("laptime table", "予選区分別のラップタイム一覧"),
        ("laptime by timing", "時刻別のラップタイム推移"),
        ("laptime by lap number", "ラップ番号別のラップタイム推移"),
    )),
    LayoutSection("best-lap", "3. 自己最速ラップの特徴", _items(
        ("speed and laptime", "自己最速ラップの最高速度とラップタイム"),
        ("tyre age and laptime", "自己最速ラップのタイヤ使用周回数とラップタイム"),
        ("flat out", "自己最速ラップの全開率"),
        ("ideal best", "ベストラップタイムと理論ベストタイム"),
        ("ideal best diff", "ベストラップタイムと理論ベストタイムの差"),
    )),
    LayoutSection("telemetry-comparison", "4. テレメトリー比較", _items(
        ("time distance delta", "自己最速ラップのテレメトリー比較"),
        ("speed on track", "自己最速ラップのコース上分布"),
    )),
    LayoutSection("segment-analysis", "5. 区間別分析", _items(
        ("mini segments", "ミニセグメントの配置"),
        ("mini segments durations", "ミニセグメント別の通過時間"),
        ("mini segments ranks", "ミニセグメント別の順位"),
        ("mini segments gaps to best", "ミニセグメント別の基準ラップとのタイム差"),
        ("corners", "コーナーの配置"),
        ("corners durations", "コーナー間の通過時間"),
        ("corners ranks", "コーナー間の順位"),
        ("corners gaps to best", "コーナー間の基準ラップとのタイム差"),
    )),
    LayoutSection("tyres-weather", "6. タイヤ・気象", _items(
        ("weekend tyres", "新品タイヤの投入履歴とセット数"),
        ("air temp", "気温の推移"),
        ("rainfall", "降雨の有無の推移"),
        ("track temp", "路面温度の推移"),
        ("wind speed", "風速の推移"),
    )),
)


PRACTICE_SECTIONS = (
    LayoutSection("results", "1. 結果の比較", _items(
        ("laptime", "セッション全体のベストタイム比較"),
        ("speedfl", "計測地点別の最高速度比較"),
    )),
    LayoutSection("run-history", "2. 走行履歴", _items(
        ("lap number by timing", "時刻別の走行ラップ履歴"),
        ("laptime table", "ラップタイム一覧"),
        ("laptime by timing", "時刻別のラップタイム推移"),
        ("laptime by lap number", "ラップ番号別のラップタイム推移"),
    )),
    LayoutSection("long-run-analysis", "3. ロングラン分析", _items(
        ("long run", "コンパウンド別のタイヤ使用周回数とラップタイム"),
    )),
    LayoutSection("best-lap", "4. 自己最速ラップの特徴", _items(
        ("speed and laptime", "自己最速ラップの最高速度とラップタイム"),
        ("tyre age and laptime", "自己最速ラップのタイヤ使用周回数とラップタイム"),
        ("flat out", "自己最速ラップの全開率"),
        ("ideal best", "ベストラップタイムと理論ベストタイム"),
        ("ideal best diff", "ベストラップタイムと理論ベストタイムの差"),
    )),
    LayoutSection("telemetry-comparison", "5. テレメトリー比較", _items(
        ("time distance delta", "自己最速ラップのテレメトリー比較"),
        ("speed distance", "自己最速ラップの速度推移"),
        ("throttle", "自己最速ラップのスロットル開度"),
        ("brake", "自己最速ラップのブレーキ操作"),
        ("speed on track", "自己最速ラップのコース上の速度分布"),
        ("shift on track", "自己最速ラップの使用ギア"),
    )),
    LayoutSection("segment-analysis", "6. 区間別分析", _items(
        ("mini segments", "ミニセグメントの配置"),
        ("mini segments durations", "ミニセグメント別の通過時間"),
        ("mini segments ranks", "ミニセグメント別の順位"),
        ("mini segments gaps to best", "ミニセグメント別の基準ラップとのタイム差"),
        ("corners", "コーナーの配置"),
        ("corners durations", "コーナー間の通過時間"),
        ("corners ranks", "コーナー間の順位"),
        ("corners gaps to best", "コーナー間の基準ラップとのタイム差"),
    )),
    LayoutSection("tyres-weather", "7. タイヤ・気象", _items(
        ("weekend tyres", "新品タイヤの投入履歴とセット数"),
        ("air temp", "気温の推移"),
        ("rainfall", "降雨の有無の推移"),
        ("track temp", "路面温度の推移"),
        ("wind speed", "風速の推移"),
    )),
)


RACE_SECTIONS = (
    LayoutSection("race-overview", "1. レース概要", _items(
        ("position", "周回ごとの順位推移"),
        ("laptime by lap number", "周回別のインタラクティブなラップタイム推移"),
    )),
    LayoutSection("gap-analysis", "2. ギャップ分析", _items(
        ("gap top graph", "首位とのギャップ推移"),
        ("gap top table", "首位とのギャップ一覧"),
        ("gap ahead graph", "前走車とのギャップ推移"),
        ("gap ahead table", "前走車とのギャップ一覧"),
    )),
    LayoutSection("lap-pit-analysis", "3. ラップ・ピット分析", _items(
        ("laptime graph", "周回別の静的なラップタイム推移"),
        ("laptime table", "ラップタイム一覧"),
        ("pittime table", "ピット所要時間一覧"),
    )),
    LayoutSection("start-analysis", "4. スタート分析", _items(
        ("speed first 10s", "スタート後10秒間の速度推移"),
        ("speed until turn1", "スタートから第1コーナーまでの速度推移"),
    )),
    LayoutSection("tyres", "5. タイヤ", _items(
        ("session tyres", "レース中のタイヤ使用履歴"),
        ("weekend tyres", "週末全体の新品タイヤ投入履歴"),
    )),
    LayoutSection("weather", "6. 気象", _items(
        ("air temp", "気温の推移"),
        ("rainfall", "降雨の有無の推移"),
        ("track temp", "路面温度の推移"),
        ("wind speed", "風速の推移"),
    )),
)


def layout_for_session(session_name: str) -> tuple[str, tuple[LayoutSection, ...]] | None:
    normalized = session_name.strip().lower()
    if normalized in {"qualifying", "sprint qualifying", "sprint shootout"}:
        return "Q", QUALIFYING_SECTIONS
    if normalized in {"practice 1", "practice 2", "practice 3"}:
        return "P", PRACTICE_SECTIONS
    if normalized in {"race", "sprint", "sprint race"}:
        return "R", RACE_SECTIONS
    return None


def _plain_title(title: str) -> str:
    plain = re.sub(r"^\[[QPR]-\d+(?:\.\d+)?\]\s*", "", title).strip().lower()
    return re.split(r"\s+—\s+", plain, maxsplit=1)[0]


def is_spec_output(session_name: str, relative_path: Path) -> bool:
    """Allow only declared outputs, including the five P-07 compounds."""
    selected = layout_for_session(session_name)
    if selected is None:
        return True
    prefix, sections = selected
    if relative_path.parent == Path("long_runs"):
        return prefix == "P" and relative_path.stem.lower() in {
            "soft", "medium", "hard", "intermediate", "wet",
        }
    if relative_path.parent == Path("__external__"):
        return relative_path.name == "tyres.png"
    if relative_path.parent != Path("."):
        return False
    key = relative_path.stem.lower().replace("_", " ")
    if key == "tyres":
        return prefix == "R"
    if prefix == "P" and key in {"speed distance", "throttle", "brake", "shift on track"}:
        return False  # P-14/15/16/18 are replaced by the integrated tabs.
    return any(key == item.key for section in sections for item in section.items)


def _card_key(card: str) -> tuple[str, str]:
    article = re.search(r'<article\b[^>]*id="([^"]+)"', card, re.S)
    anchor = article[1].lower() if article else ""
    heading = re.search(r"<h3>(.*?)</h3>", card, re.S)
    title = re.sub(r"<[^>]+>", "", heading[1]).strip() if heading else ""
    plain = _plain_title(title)
    display_title = re.sub(r"^\[[QPR]-\d+(?:\.\d+)?\]\s*", "", title).strip()
    if " — " in display_title:
        display_title = display_title.split(" — ", 1)[1]
    if "long-runs-long-runs-" in anchor:
        compound = anchor.split("long-runs-long-runs-", 1)[1].rsplit("-", 1)[0]
        return "long run", compound
    if re.search(r"telemetry-shift-on-track-\d+-", anchor):
        return "shift on track", display_title
    if re.search(r"telemetry-speed-on-track-\d+-", anchor):
        return "speed on track", display_title
    if plain == "tyres" and "external-tyres" in anchor:
        return "weekend tyres", display_title
    if plain == "tyres":
        return "session tyres", display_title
    return plain, display_title


def _resolve_item_key(key: str, sections: tuple[LayoutSection, ...]) -> str:
    """Accept both legacy English filenames and already-localized headings."""

    if any(key == item.key for section in sections for item in section.items):
        return key
    for section in sections:
        for item in section.items:
            if key == item.title.lower():
                return item.key
    return key


def organize_session_report_html(html: str, session_name: str) -> str:
    """Reorder a report and rebuild its navigation for the session type."""
    selected = layout_for_session(session_name)
    if selected is None:
        return html
    prefix, sections = selected
    main = re.search(r"<main>(.*?)</main>", html, re.S)
    if main is None:
        return html
    cards = re.findall(r"<article\b[^>]*>.*?</article>", main[1], re.S)
    groups: dict[str, list[tuple[str, str]]] = {}
    for card in cards:
        key, raw_title = _card_key(card)
        key = _resolve_item_key(key, sections)
        groups.setdefault(key, []).append((card, raw_title))

    nav = ['<a href="#summary">概要</a>']
    rendered_sections: list[str] = []
    item_number = 0
    long_run_order = {name: index for index, name in enumerate(
        ("soft", "medium", "hard", "intermediate", "wet"), start=1
    )}
    for section in sections:
        section_content: list[str] = []
        links: list[str] = []
        for item in section.items:
            item_number += 1
            entries = groups.pop(item.key, [])
            if prefix == "P" and item_number in {14, 15, 16, 18}:
                continue
            if item.key == "long run":
                entries.sort(key=lambda entry: long_run_order.get(entry[1].lower(), 99))
            for branch_index, (card, raw_title) in enumerate(entries):
                compound_branch = item.key == "long run" and raw_title.lower() in long_run_order
                branch_number = long_run_order.get(raw_title.lower(), branch_index + 1)
                number = f"{item_number:02d}" + (
                    f".{branch_number}" if compound_branch or len(entries) > 1 else ""
                )
                suffix = ""
                if compound_branch:
                    suffix = f" — {raw_title.title()}"
                elif len(entries) > 1:
                    suffix = f" — {raw_title}" if raw_title and raw_title != item.key else ""
                heading = f"[{prefix}-{number}] {item.title}{suffix}"
                anchor = f"{prefix.lower()}-{number.replace('.', '-') }"
                card = re.sub(r'<span id="[qpr]-\d+(?:-\d+)?"[^>]*></span>', '', card, flags=re.I)
                card = re.sub(
                    r"<h3>.*?</h3>",
                    f'<span id="{anchor}" style="display:block;scroll-margin-top:7rem"></span>'
                    f'<h3>{escape(heading)}</h3>', card, count=1, flags=re.S,
                )
                section_content.append(card)
                links.append(f'<a href="#{anchor}">{escape(heading)}</a>')
        if section_content:
            nav.append(f'<a href="#{section.anchor}">{escape(section.title)}</a>')
            rendered_sections.append(
                f'<section class="report-section" id="{section.anchor}"><h2>{escape(section.title)}</h2>'
                '<details class="figure-index"><summary>グラフ一覧</summary><ul>'
                + ''.join(f'<li>{link}</li>' for link in links)
                + '</ul></details>' + ''.join(section_content) + '</section>'
            )

    html = html[:main.start(1)] + ''.join(rendered_sections) + html[main.end(1):]
    return re.sub(
        r'<nav>.*?</nav>', lambda _: '<nav>' + ''.join(nav) + '</nav>', html, count=1, flags=re.S
    )
