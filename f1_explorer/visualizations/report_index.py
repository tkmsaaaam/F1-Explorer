"""Build an offline directory of generated session reports."""

from __future__ import annotations

from html import escape
import json
from pathlib import Path
import re
from urllib.parse import quote


def _sort_grand_prix(name: str) -> tuple[int, str]:
    match = re.match(r"^(\d+)_", name)
    return (int(match.group(1)) if match else 10_000, name)


def build_index(root: str | Path = "reports") -> Path:
    """Index existing reports without reading or changing their contents."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, str]] = []
    for year_dir in sorted(root.iterdir(), key=lambda path: path.name, reverse=True):
        if not year_dir.is_dir() or not re.fullmatch(r"\d{4}", year_dir.name):
            continue
        for gp_dir in sorted((path for path in year_dir.iterdir() if path.is_dir()),
                             key=lambda path: _sort_grand_prix(path.name)):
            for session_dir in sorted(path for path in gp_dir.iterdir() if path.is_dir()):
                report = session_dir / "report.html"
                if report.is_file():
                    relative = report.relative_to(root)
                    entries.append({
                        "year": year_dir.name,
                        "gp": gp_dir.name,
                        "session": session_dir.name,
                        "url": "/".join(quote(part) for part in relative.parts),
                    })

    # Escaping '<' also prevents a file name from ending the JSON script tag.
    payload = json.dumps(entries, ensure_ascii=False).replace("<", "\\u003c")
    options = "".join(
        f'<option value="{escape(year, quote=True)}">{escape(year)}</option>'
        for year in dict.fromkeys(entry["year"] for entry in entries)
    )
    html = f'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>F1 Explorer — Reports</title>
<style>
:root {{ font-family: system-ui, sans-serif; color-scheme: light; }}
body {{ margin: 0; background: #f5f7fa; color: #202124; }}
header {{ background: #18202a; color: #fff; padding: 1.5rem max(1rem, calc((100vw - 900px)/2)); }}
h1 {{ margin: 0; font-size: 1.6rem; }}
main {{ max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
.picker {{ display: grid; gap: 1rem; grid-template-columns: repeat(3, minmax(0, 1fr)); padding: 1.5rem; background: white; border: 1px solid #d9dee5; border-radius: 8px; }}
label {{ display: grid; gap: .4rem; font-weight: 600; }}
select {{ min-width: 0; padding: .65rem; font: inherit; }}
.open {{ display: inline-block; margin-top: 1.5rem; padding: .75rem 1rem; background: #145da0; color: white; border-radius: 6px; text-decoration: none; font-weight: 600; }}
.open[aria-disabled="true"] {{ opacity: .5; pointer-events: none; }}
@media (max-width: 650px) {{ .picker {{ grid-template-columns: 1fr; }} }}
</style></head><body>
<header><h1>F1 Explorer — Reports</h1></header>
<main><p>年、グランプリ、セッションを選択してください。</p>
<div class="picker"><label>年<select id="year">{options}</select></label><label>グランプリ<select id="gp"></select></label><label>セッション<select id="session"></select></label></div>
<a class="open" id="open" href="#" aria-disabled="true">レポートを開く</a>
<p id="empty" hidden>レポートはまだありません。</p></main>
<script type="application/json" id="reports">{payload}</script>
<script>
(() => {{
  const reports = JSON.parse(document.getElementById("reports").textContent);
  const year = document.getElementById("year"), gp = document.getElementById("gp");
  const session = document.getElementById("session"), open = document.getElementById("open");
  document.getElementById("empty").hidden = reports.length > 0;
  const fill = (node, values) => {{
    node.replaceChildren(...values.map(value => new Option(value, value)));
    node.disabled = values.length === 0;
  }};
  const updateLink = () => {{
    const match = reports.find(item => item.year === year.value && item.gp === gp.value && item.session === session.value);
    open.href = match ? match.url : "#";
    open.setAttribute("aria-disabled", match ? "false" : "true");
  }};
  const updateSession = () => {{
    fill(session, reports.filter(item => item.year === year.value && item.gp === gp.value).map(item => item.session));
    updateLink();
  }};
  const updateGp = () => {{
    fill(gp, [...new Set(reports.filter(item => item.year === year.value).map(item => item.gp))]);
    updateSession();
  }};
  year.addEventListener("change", updateGp);
  gp.addEventListener("change", updateSession);
  session.addEventListener("change", updateLink);
  updateGp();
}})();
</script></body></html>
'''
    target = root / "index.html"
    target.write_text(html, encoding="utf-8")
    return target


if __name__ == "__main__":
    build_index()
