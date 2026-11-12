# F1-Explorer

F1-Explorer is a data analysis and visualization toolkit for Formula 1 data, leveraging the FastF1 library. It provides
tools for both historical session analysis and real-time telemetry tracking during live race sessions.

## Data sources

* [FastF1](https://docs.fastf1.dev/) provides session results, lap timing, and telemetry used by the analysis tools.
* The [Formula 1 Live Timing archive (2025 season index)](https://livetiming.formula1.com/static/2025/Index.json) provides timing data used to estimate mini-segment boundaries. The code selects the season index for the year being analyzed.

---

## Project Structure

The repository is organized into the following components:

### Analysis entrypoints

* **[analyze_practice.py](analyze_practice.py)**: Script for analyzing Free Practice sessions. It focuses on long-run
  pace and consistency.
* **[analyze_qualifying.py](analyze_qualifying.py)**: Script for analyzing Qualifying sessions, including flying lap
  comparisons.
* **[analyze_season.py](analyze_season.py)**: Script for visualizing season-long trends, such as championship points
  transitions.
* **[f1_explorer/](f1_explorer/)**: Shared configuration, analysis state, constants and separator logic.
* **[f1_explorer/visualizations/](f1_explorer/visualizations/)**: A directory containing core visualization methods. The analysis scripts above
  call functions from
  this directory to generate plots.
* **[segment_analysis.py](f1_explorer/visualizations/segment_analysis.py)**: Segment layouts, maps, and tables. Numerical metrics remain in segment_metrics.py.
* **[templates/template.html](templates/template.html)**: Shared HTML layout and browser behavior for session reports.

### Live tracking

* **[live.py](live.py)**: Subscribes to the live data stream during race sessions, receiving JSON-like text information.
* **[tracker/](tracker)**: Contains tools to parse the data received by live.py and visualize it as graphs in real-time.

---

## Setup

### Prerequisites

Use a Python version compatible with the pinned dependencies in `requirements.txt`. The primary dependency is the **FastF1** library.

### Installation

Clone the repository and install the dependencies listed in [requirements.txt](requirements.txt):

```bash
pip install -r requirements.txt
```

## Tests and coverage

Install development dependencies in a virtual environment from the repository root:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

Node.js must be available on PATH for the report HTML JavaScript tests.
Those tests are skipped when Node.js is unavailable.

Run a focused test or the full suite through Coverage.py, then print the summary:

```bash
.venv/bin/python -m pytest tests/test_report.py -q -W error::DeprecationWarning
.venv/bin/python -m coverage run -m pytest tests -q -W error::DeprecationWarning
.venv/bin/python -m coverage report -m
```

To generate a detailed HTML coverage report, run:

```bash
.venv/bin/python -m coverage html
```

Open `htmlcov/index.html` in a browser to view it. The `-W` option makes
deprecation warnings fail the test run.

## Configuration

Before running the scripts, create a local configuration file:

1. Locate the [sample.config.json](sample.config.json) file in the root directory.
2. Create a copy of it and rename it to [config.json](config.json).
3. Edit [config.json](config.json) to include your specific settings (such as cache directory paths or API credentials
   if required).

```bash
cp sample.config.json config.json
```

Set `F1_LOG_LEVEL` to a Python logging level such as `DEBUG`, `INFO`, or
`WARNING` to control standard Python logging, including FastF1, Kaleido, and
Choreographer. This does not change the application's structlog output. Without this
environment variable, FastF1, Kaleido, and Choreographer logs default to
`WARNING`.

## Usage

### Historical Data Analysis

Run entrypoints from the repository root so relative paths for `config.json`, `cache/`, and outputs resolve correctly:

```bash
# For Free Practice analysis
python analyze_practice.py

# For Qualifying analysis
python analyze_qualifying.py

# For Season points and trends
python analyze_season.py

# Run multiple sessions from a JSON plan
python analyze_batch.py sample.analysis-plan.json
```

Season analysis is written as a self-contained offline report at
`reports/<year>/season.html`. Interactive charts and the points/events table
images are embedded in that single HTML file.
The points table retains the sprint points total and lists points for each venue
below it in sprint calendar order. The championship total includes both race and sprint points.

The season report also includes recorded completed-lap counts for FP1–FP3,
SQ, S, Q and R, plus estimated qualifying-attack attempts for each practice
and qualifying segment. Attack estimates compare a driver's laps and first
sector against that driver's best accurate lap and first sector on the same
compound. In practice, four or more consecutive representative laps are
marked as purpose-uncertain to avoid counting a long run as repeated attacks.
Deleted laps and partial laps can count when their timing supports an attempt.
These estimates do not identify every aborted lap; their thresholds are
documented in [specs/SEASON.md](specs/SEASON.md). The report distinguishes
missing data, non-participation, and provisional totals.

Race and Sprint gap tables use actual lap numbers from 1 through the last
recorded lap across all drivers. Missing laps or comparison cars display `---`;
the leader's gap to the car ahead is also `---`, while its gap to the leader is zero.
All four Race/Sprint gap charts and tables follow the official session result
order. Drivers without a result rank follow in fastest-lap order, computed
excluding deleted laps; ties and drivers without either rank are ordered by
driver-number string.

A lap that records a number stays eligible even when its lap time,
session-elapsed time, or position is missing. Each chart shows the laps whose
own required values exist and never substitutes zero or interpolated times:
missing positions leave a line gap in the lap-position history, laps missing
only their lap time still appear in position and gap charts, and laps without
a session-elapsed time or position provide no gap value (`---` in the tables,
line gaps in the graphs).

Session analyses write independent offline reports to
`reports/<year>/<round>_<location>/<session>/report.html`. Open
`reports/index.html` to select a year, Grand Prix, and session. The index is
updated when a session report is written. To rebuild it from existing reports,
run `python -m f1_explorer.visualizations.report_index` from the repository root.

The pit-time table counts stops with matching consecutive laps and complete,
chronologically ordered pit-in, lap-start, and pit-out timestamps. With no valid
stops, it shows count 0 and `—` for the mean, minimum, and maximum. Missing lap
times are shown as `—` while valid pit durations remain in the statistics.

Optional flat-out and ideal-best charts omit drivers whose telemetry or sector
times do not contain the required finite, positive measurements. Missing telemetry
samples are not bridged to calculate flat-out ratios. Circuit-dependent charts are
skipped when the fastest lap has no finite, positive distance sample; the report
continues without those charts.

Session analyses save only `laptime_table.png` for every session and
`laptime_graph.png` for Sprint/Race.
The retained PNGs are written directly to `images/<year>/` as
`<round>_<session>_laptime_table.png` and
`<round>_<session>_laptime_graph.png`. Session names use the existing directory
names with spaces removed, for example `images/2026/15_Practice1_laptime_table.png`
and `images/2026/15_Race_laptime_graph.png`.

All other charts, including weather,
segment maps, and race tyre history, are embedded as interactive Plotly figure
data without generating PNGs. Images can be downloaded from the charts'
camera button while viewing the report offline. Existing PNG files are retained, but unused PNGs
are excluded from the new success manifest. Visualization calls outside an
active session report continue to save their images.

Practice, Qualifying, and Sprint Qualifying telemetry comparisons, track maps,
and segment tables include every driver with a valid personal fastest lap,
without a session-wide lap-time cutoff. Selection follows FastF1's default
`pick_fastest()` rules and requires a finite, positive lap time. Drivers appear
in personal-fastest order, with ties ordered by driver-number string. Missing
telemetry omits the affected series or leaves table cells missing; it does not
change the fastest-lap reference to another driver.

The five-tab telemetry comparison for Practice, Qualifying, and Sprint Qualifying
interpolates time deltas on the fastest lap's distance grid, starting at 0 m in
5 m steps and stopping before its last valid distance. Deltas appear only within
both drivers' measured distance ranges; unobserved ends remain gaps. Nonfinite
samples are removed and duplicate distances keep their first sample. Backward
distance or time progress, or fewer than two comparable grid points, omits only
that driver's delta. An unavailable reference leaves all deltas unavailable;
other channels remain usable. These are interpolated telemetry differences,
not official sector times, and lap endpoints are not adjusted to match lap times.

Practice, Qualifying, and Sprint Qualifying track maps show one driver at a time.
Switching speed/gear keeps the selected driver when data is available, and changing
drivers keeps the selected metric. Each metric has its own driver list; switching
to an unavailable combination selects the first valid driver, or displays
“有効なデータなし” when the metric has no data.

### Batch analysis

`analyze_batch.py` accepts a JSON array of years, rounds and sessions. It
updates only `Year`, `Round` and `Session` in `config.json`, runs each analyzer
sequentially, and restores those three fields afterwards. Other changes made
by an analyzer, such as newly generated circuit separators, are retained.

```json
[
  {
    "year": 2026,
    "gp": [
      {"number": 13, "sessions": ["FP1", "FP2", "Q", "R"]}
    ]
  }
]
```

Supported session names are `FP1`, `FP2`, `FP3`, `Q`, `SQ`, `S` and `R`.
Useful options are `--dry-run`, `--force`, `--refresh-separators`,
`--fail-fast` and `--keep-last-config`.

The Practice, Qualifying (including SQ), and Race (including Sprint) commands
exit with code 0 after successful analysis or a normal skip (a future session
or an unchanged report). Future sessions are skipped before loading lap data.
For an existing session, each command loads FastF1 data before checking whether
the report can be reused. A report is reusable only when the final loaded
session status is `Finished`, its normalized event/results/laps/weather/status/
track-status/car/position inputs match the successful manifest, and every
recorded output still exists. Reuse also requires matching analysis source,
Python and installed dependency versions, effective configuration, and the
year/round/session/entrypoint identity. Git commit and dirty state are diagnostic
information only. Race and Sprint also include race-control messages.
Missing or unsupported inputs and non-finished sessions are analyzed
again and do not create a reusable success manifest. Input comparison covers
the data FastF1 returned; it cannot detect upstream corrections that FastF1 has
not fetched, and offline use cannot fetch them. `--force` always re-analyzes the
loaded data but does not refresh FastF1's upstream cache or guarantee corrected
data. When refreshed source data is required, follow
[Refreshing source data](#refreshing-source-data) below before `--force`.
Invalid configuration, the wrong session category, and session lookup failures
exit with code 1. Unhandled loading, analysis, or report/manifest write errors
also exit nonzero, without writing a new success manifest. Once regeneration
starts, its previous success manifest is removed; failed runs cannot reuse it.
The new manifest lists only files explicitly produced by that run, including
the report, required PNGs, and Race logs. Prior chart files are kept but do not
make a failed or incomplete run reusable. Optional chart omissions and separator-save warnings remain
recoverable and do not by themselves fail the analysis.

The batch exits with code 1 if any analyzer fails. It continues with the next
job by default; `--fail-fast` stops at the first failure. Normal skips are not
counted as failures. In either case, the original session selection is restored
unless `--keep-last-config` is specified.

Within one batch, completed weekends can reuse the tyre aggregate across session
reports. The cache lives only for that batch, is checked against the local
FastF1 event files and analysis inputs, and is removed when the batch exits.
The currently analyzed session is reused for the aggregate when available.

### Refreshing source data

The following procedure was checked against FastF1 3.9.0. FastF1 stores HTTP
responses in a stage 1 SQLite cache and parsed API data in stage 2 `.ff1pkl`
files. Normal loading can reuse both; the HTTP cache uses a 12-hour expiry,
cache-control, and stale responses on request errors. Cache file timestamps,
sizes, and report creation times do not establish upstream freshness.

`fastf1.Cache.configure(cache_dir=..., force_renew=True)` immediately clears
the entire stage 1 cache at that location. While enabled in that Python
process, it also bypasses existing stage 2 entries and overwrites them when
their data is loaded. It is not limited to one session. The analysis entrypoints
configure `./cache`, so setting `FASTF1_CACHE` alone does not isolate them.
Use a temporary project copy with an empty cache to preserve local data.

From the repository root, with the project's dependencies installed in `.venv`:

```bash
F1_REFRESH_ROOT="$PWD"
F1_REFRESH_COPY="$(mktemp -d)/F1-Explorer"
mkdir -p "$F1_REFRESH_COPY"
rsync -a --exclude='.git/' --exclude='.venv/' --exclude='cache/' \
  --exclude='images/' --exclude='reports/' --exclude='live/' \
  --exclude='htmlcov/' --exclude='tmp/' --exclude='__pycache__/' \
  "$F1_REFRESH_ROOT/" "$F1_REFRESH_COPY/"
ln -s "$F1_REFRESH_ROOT/.venv" "$F1_REFRESH_COPY/.venv"
mkdir -p "$F1_REFRESH_COPY/cache"
cd "$F1_REFRESH_COPY"
```

This copies the current code, including uncommitted changes and `config.json`,
but excludes existing caches and generated reports. In this copy's
`config.json`, select the intended `Year`, `Round`, and `Session`, then prefetch:

```bash
.venv/bin/python - <<'PY'
import json
import fastf1

with open("config.json", encoding="utf-8") as config_file:
    selected = json.load(config_file)
fastf1.Cache.configure(cache_dir="./cache", force_renew=True)
session = fastf1.get_session(selected["Year"], selected["Round"], selected["Session"])
session.load()
print("loaded", session.event["EventName"], session.name, "laps", len(session.laps))
print(session.session_status.tail())
PY
```

Inspect the logs and loaded inputs for request failures, missing data, and rate
limits. FastF1 can suppress individual loading exceptions, so exit code 0 alone
does not confirm a complete refresh. After a successful prefetch, run the
appropriate analyzer in the same copy, using the same `./cache`:

```bash
.venv/bin/python analyze_qualifying.py --force
```

Use `analyze_practice.py` for Practice or `analyze_race.py` for Race/Sprint.
The new process reuses the refreshed cache without inheriting the prefetch
process's force-renew flag. Confirm that the report's `.analysis-manifest.json`
was written: a reusable success requires final status `Finished`, a complete
input fingerprint, and all recorded outputs. An unchanged fingerprint is
expected when the provider has made no correction. The resulting reports stay
in the temporary copy until you explicitly copy them elsewhere.

The refresh covers the selected session's metadata, driver/results inputs,
session and track status, lap count and timing/tyres, car and position telemetry,
weather, and race-control messages loaded by `Session.load()`. It does not
guarantee refresh of every auxiliary source used by a report, such as the event
schedule, Jolpica results, circuit information, or the Live Timing archive used
for separator estimation. Weekend tyre aggregates can load FP1–FP3, SQ, S, Q,
and R; prefetch each session whose updated inputs are needed.

Refreshing requires network access. Do not combine force renewal with offline
mode: clearing the HTTP cache removes its fallback responses, and a failed
prefetch can leave partial data. Discard a failed temporary cache and retry
after connectivity recovers. Offline mode and force-renew flags apply only to
their Python process. Request only the sessions needed and respect provider
rate limits; an upstream correction that has not yet been published cannot be
detected by this procedure.

`Cache.delete_response(url)` removes only one HTTP response and leaves parsed
stage 2 data intact; it is not a session refresh. Avoid `Cache.clear_cache()`
for this workflow: deep clearing can delete stage 2 files even offline, and its
directory argument and active HTTP backend can refer to different locations.
Saved separators remain unchanged by `--force`; replace them only with
`--refresh-separators` when explicitly intended.

### Exporting OpenTelemetry data

The Practice, Qualifying, and Race entrypoints create OpenTelemetry spans. To
export them, install
`opentelemetry-distro` and `opentelemetry-exporter-otlp` in the same virtual
environment as the project, then run the analyzer through
`opentelemetry-instrument`. The OpenTelemetry API and SDK in
`requirements.txt` alone do not provide that command or an OTLP exporter.
Install the additional packages if they are not already in `.venv`:

```bash
.venv/bin/python -m pip install opentelemetry-distro opentelemetry-exporter-otlp
```

The following example sends traces, metrics, and standard Python logging to a
local OTLP/HTTP receiver on port 4318:

```bash
OTEL_SERVICE_NAME=f1-explorer \
OTEL_TRACES_EXPORTER=otlp \
OTEL_METRICS_EXPORTER=otlp \
OTEL_LOGS_EXPORTER=otlp \
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
OTEL_PYTHON_LOG_AUTO_INSTRUMENTATION=true \
PYTHONUNBUFFERED=1 \
.venv/bin/opentelemetry-instrument .venv/bin/python \
analyze_batch.py batch.json --refresh-separators --force
```

Run this from the repository root with the OTLP receiver already listening.
Replace `batch.json` with your plan file, or replace the final command with an
individual analyzer such as `analyze_practice.py --force`. The base endpoint
above sends each signal to `/v1/traces`, `/v1/metrics`, or `/v1/logs`.
If using signal-specific `OTEL_EXPORTER_OTLP_*_ENDPOINT` variables instead,
include the corresponding `/v1/...` path in each HTTP URL. For a receiver that
accepts gRPC traces on port 4317, set
`OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=grpc` and
`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://localhost:4317`; the other signals
can remain on HTTP/4318.

The configured exporter sends metrics only when an instrument creates them.
The existing analysis spans provide trace timings, but the scripts do not yet
record phase-duration metrics. Standard Python logging can be exported; the
application's `structlog` JSON messages are written to stdout and are not
automatically included in OTLP logs. Use `F1_LOG_LEVEL=INFO` for more library
logging, or `DEBUG` only when diagnosing a problem because Matplotlib and
Kaleido can produce large volumes of debug logs.

See the [OpenTelemetry Python zero-code setup](https://opentelemetry.io/docs/zero-code/python/),
[agent configuration](https://opentelemetry.io/docs/zero-code/python/configuration/),
and [OTLP endpoint rules](https://opentelemetry.io/docs/specs/otel/protocol/exporter/).

To explicitly re-estimate a saved circuit separator, use
`python analyze_practice.py --refresh-separators` (or the qualifying
entrypoint).  Automatic boundaries are stored in the `separators` object by
year and `session.event.Location` and are shared by Practice and Qualifying:

```json
"separators": {
  "2025": {
    "Yas Marina Circuit": {
      "schema_version": 1,
      "boundaries": [
        {"distance": 412.3, "sector": 0, "segment": 7},
        {"distance": 887.1, "sector": 1, "segment": 3}
      ]
    }
  }
}
```

Each structured boundary retains its Live Timing sector and mini-segment
identity. Older locations containing a flat distance array remain readable.
The mini-segment map and all three segment tables derive their distance list
from the same structured boundary set. Sector markers use the final stored
boundary in sector 0 or 1; only legacy arrays use the FastF1 telemetry
position fallback.

Existing `separator`/`Separator` and `corners`/`Corners` settings remain
supported as legacy fallbacks. A saved year/location value is not changed by
`--force`; only `--refresh-separators` can replace it. Failed or insufficient
archive data leaves the configuration untouched and uses corner-based
boundaries.

Live Timing and FastF1 clocks are not joined by their absolute timestamps.
Each sector of a valid driver/lap is normalized independently to 0–100% of
sector elapsed time; a Live Timing mini-sector completion percentage is
interpolated within the matching FastF1 sector telemetry to obtain distance.
When TimingData exposes an explicit sector completion update, it defines that
sector's end time; the last mini-segment completion is used only when the
explicit update is absent. FastF1 interpolation is clamped to the matching
sector's start/end distance, so a preceding sector's pace cannot move a later
sector boundary.
The stored separator values are distances in metres. Live Timing laps are accepted only
when consecutive lap boundaries agree with the reported lap time (within 5%
or 2 seconds) and mini-sector progress is monotonic. Separator entries must be
positive, finite distances: zero or negative entries are ignored, both when
stored as plain numbers and as structured boundary records.

## Implementation Details

* **FastF1 Integration**: The project is primarily built on the **FastF1** library, which provides access to F1
  telemetry, lap timing, and session results.
* **Analysis & Visualization**:
    * Post-session scripts (`analyze_*.py`) utilize modular methods defined within
      the [f1_explorer/visualizations/](f1_explorer/visualizations/) directory to
      ensure consistent plotting logic across different session types.
    * These tools transform raw API data into intuitive visual formats for performance comparison and trend analysis.
* **Live Data Processing**:
    * **Data Subscription**: [live.py](live.py) manages the connection to the live session feed, handling the ingestion
      of
      JSON-like text information.
    * **Real-time Parsing**: The [tracker/](tracker/) module is designed for low-latency parsing of the incoming stream,
      enabling
      the visualization of telemetry and timing data while the session is in progress.

サーキット情報の取得に失敗してもセッションレポートの生成は継続します。コーナー情報が必須の図は省略し、その他の図はコーナー注記なしで生成します。取得例外は警告ログに記録します。

週末の新品タイヤ投入履歴は、各セッションで FreshTyre が明示的に True の記録をスティントごとに1件集計します。欠測は新品投入の記録なしとして除外します。

ラップ番号別・時刻別ラップタイム図は、最小タイムが欠測・非有限なら理由をログに残して省略します。時刻別PNGのY軸は小数秒を切り捨てずに計算します。

テレメトリー比較はタブごとにY軸の範囲と目盛りを更新し、データのない項目は「欠測」と表示します。

ロングラン候補はタイヤStintと走行区間を区別し、実ラップ番号を保持します。凡例に実ラップ範囲と採用・表示周回数、ホバーに実ラップ番号とタイヤ年齢を表示します。タイヤ年齢の重複は保持し、欠測点は描画せず前後の線を切ります。

ロングラン図の折りたたみ「採否一覧」で、元ラップ番号・Stint・開始時刻・採否理由と標本数を確認できます。燃料・路面進化の補正はなく、トラフィック判定はタイム差からの推定です。
