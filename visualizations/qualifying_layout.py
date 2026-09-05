"""Qualifying report sections and card order shared with the specification."""

from html import escape
import re


QUALIFYING_SECTIONS = (
    ("results", "1. 結果の比較", (
        ("Laptime", "予選全体のベストラップタイム"),
        ("Sector1Time", "セクター1の自己ベストタイム"),
        ("Sector2Time", "セクター2の自己ベストタイム"),
        ("Sector3Time", "セクター3の自己ベストタイム"),
        ("Speedfl", "フィニッシュラインの最高速度"),
        ("Speedi1", "第1中間計測地点の最高速度"),
        ("Speedi2", "第2中間計測地点の最高速度"),
        ("Speedst", "スピードトラップの最高速度"),
    )),
    ("run-history", "2. 走行履歴", (
        ("Lap Number By Timing", "時刻別の走行ラップ履歴"),
        ("Laptime Table", "予選区分別のラップタイム一覧"),
        ("Laptime By Timing", "時刻別のラップタイム推移"),
        ("Laptime By Lap Number", "ラップ番号別のラップタイム推移"),
    )),
    ("best-lap", "3. 自己最速ラップの特徴", (
        ("Speed And Laptime", "自己最速ラップの最高速度とラップタイム"),
        ("Tyre Age And Laptime", "自己最速ラップのタイヤ使用周回数とラップタイム"),
        ("Flat Out", "自己最速ラップの全開率"),
        ("Ideal Best", "ベストラップタイムと理論ベストタイム"),
        ("Ideal Best Diff", "ベストラップタイムと理論ベストタイムの差"),
    )),
    ("telemetry-comparison", "4. テレメトリー比較", (
        ("Time Distance Delta", "自己最速ラップの累積タイム差"),
        ("Speed Distance", "自己最速ラップの速度推移"),
        ("Throttle", "自己最速ラップのスロットル開度"),
        ("Brake", "自己最速ラップのブレーキ操作"),
        ("Speed On Track", "自己最速ラップのコース上の速度分布"),
        ("Shift On Track", "自己最速ラップの使用ギア"),
    )),
    ("segment-analysis", "5. 区間別分析", (
        ("Mini Segments", "ミニセグメントの配置"),
        ("Mini Segments Durations", "ミニセグメント別の通過時間"),
        ("Mini Segments Ranks", "ミニセグメント別の順位"),
        ("Mini Segments Gaps To Best", "ミニセグメント別の基準ラップとのタイム差"),
        ("Corners", "コーナーの配置"),
        ("Corners Durations", "コーナー間の通過時間"),
        ("Corners Ranks", "コーナー間の順位"),
        ("Corners Gaps To Best", "コーナー間の基準ラップとのタイム差"),
    )),
    ("tyres-weather", "6. タイヤ・気象", (
        ("Tyres", "新品タイヤの投入履歴とセット数"),
        ("Air Temp", "気温の推移"),
        ("Rainfall", "降雨の有無の推移"),
        ("Track Temp", "路面温度の推移"),
        ("Wind Speed", "風速の推移"),
    )),
)


def organize_qualifying_report_html(html: str) -> str:
    """Reorder cards and rebuild navigation without altering figure payloads.

    Works on newly generated and legacy reports. Existing article IDs stay valid;
    new q-NN anchors provide consistent per-figure links across sessions.
    Unrecognized cards are preserved in a separate section, never dropped.
    """
    main = re.search(r"<main>(.*?)</main>", html, re.S)
    if main is None:
        return html
    cards = re.findall(r"<article\b[^>]*>.*?</article>", main[1], re.S)
    groups: dict[str, list[str]] = {}
    names = {name for _, _, items in QUALIFYING_SECTIONS for name, _ in items}
    translated = {title: name for _, _, items in QUALIFYING_SECTIONS for name, title in items}
    for card in cards:
        heading = re.search(r"<h3>(.*?)</h3>", card, re.S)
        title = re.sub(r"^\[Q-[\d.]+\] ", "", heading[1]) if heading else ""
        name = title if title in names else translated.get(title, title)
        groups.setdefault(name, []).append(card)

    nav = ['<a href="#summary">概要</a>']
    sections = []
    number = 0
    for anchor, label, items in QUALIFYING_SECTIONS:
        content, links = [], []
        for name, title in items:
            number += 1
            for index, card in enumerate(groups.pop(name, [])):
                key = f"q-{number:02d}" + (f"-{index + 1}" if index else "")
                heading = f"[Q-{number:02d}] {title}"
                card = re.sub(r'<span id="q-\d+(?:-\d+)?"[^>]*></span>', '', card)
                card = re.sub(
                    r"<h3>.*?</h3>",
                    f'<span id="{key}" style="display:block;scroll-margin-top:7rem"></span>'
                    f'<h3>{escape(heading)}</h3>', card, count=1, flags=re.S,
                )
                content.append(card)
                links.append(f'<a href="#{key}">{escape(heading)}</a>')
        if content:
            nav.append(f'<a href="#{anchor}">{escape(label)}</a>')
            sections.append(
                f'<section class="report-section" id="{anchor}"><h2>{escape(label)}</h2>'
                '<details class="figure-index"><summary>グラフ一覧</summary><ul>'
                + ''.join(f'<li>{link}</li>' for link in links)
                + '</ul></details>' + ''.join(content) + '</section>'
            )
    if groups:
        nav.append('<a href="#additional-figures">その他の出力（仕様未登録）</a>')
        sections.append('<section class="report-section" id="additional-figures">'
                        '<h2>その他の出力（仕様未登録）</h2>'
                        + ''.join(card for group in groups.values() for card in group) + '</section>')
    html = html[:main.start(1)] + ''.join(sections) + html[main.end(1):]
    return re.sub(r'<nav>.*?</nav>', lambda _: '<nav>' + ''.join(nav) + '</nav>', html, count=1, flags=re.S)
