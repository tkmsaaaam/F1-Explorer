"""Escaped, offline selection evidence for the existing long-run figure card."""
from html import escape
from typing import TypedDict

from f1_explorer.visualizations.domain.long_run import LongRunScope


class _RecordDriver(TypedDict):
    number: int
    name: str
    team_name: str


class DecisionRecord(TypedDict):
    """One ``asdict(LongRunDecision)`` entry serialized into figure meta."""
    driver: _RecordDriver
    stint_id: int | None
    compound: str
    lap_numbers: list[int | None]
    start_time: str | None
    scope: LongRunScope
    accepted: bool
    reasons: list[str]


REASONS = {
    "missing": "ラップ番号またはタイム欠測", "deleted": "削除済み",
    "inaccurate": "精度偽", "pit": "ピット", "track_status": "通常走行以外",
    "slow_interior": "遅い中間周（トラフィック推定）",
    "insufficient_consecutive": "連続周回不足",
    "qualifying_same_stint": "予選想定（同一Stint後続区間との比較）",
    "qualifying_other_stint": "予選想定（別Stintとの比較）",
    "automatic_long_run": "連続周回数による採用",
    "retained_short_run": "短区間・予選想定と判定せず採用",
}


def selection_details(records: list[DecisionRecord]) -> str:
    if not records:
        return ""
    rows = []
    for record in records:
        numbers = record["lap_numbers"]
        # Enumerating the actual numbers preserves gaps and missing values.
        laps = ", ".join(str(n) if n is not None else "欠測" for n in numbers)
        values = [
            record["driver"]["name"], record["stint_id"] if record["stint_id"] is not None else "不明",
            record["compound"], record["start_time"] or "不明", laps,
            "区間" if record["scope"] == "phase" else "ラップ",
            "採用" if record["accepted"] else "除外",
            " / ".join(f"{REASONS.get(r, r)} [{r}]" for r in record["reasons"]), len(numbers),
        ]
        rows.append("<tr>" + "".join(f"<td>{escape(str(v))}</td>" for v in values) + "</tr>")
    headers = ["ドライバー", "Stint", "コンパウンド", "開始時刻", "実ラップ", "判定単位",
               "採否", "理由", "標本数"]
    return (
        "<details><summary>ロングラン候補の採否一覧</summary>"
        "<p>燃料・路面進化の補正なし。トラフィックはタイム差による推定です。"
        "純粋なレースペースの総合順位を示すものではありません。"
        "ラップ単位の判定を先に、区間単位の判定を後に並べています。"
        "開始時刻は先頭ラップの開始時刻で、絶対時刻が既知ならその日時、"
        "未知ならセッション開始からの相対時刻を示します。</p>"
        "<table><thead><tr>" + "".join(f"<th>{h}</th>" for h in headers)
        + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></details>"
    )
