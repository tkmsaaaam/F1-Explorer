# F1-Explorer

F1-Explorer is a data analysis and visualization toolkit for Formula 1 data, leveraging the FastF1 library. It provides
tools for both historical session analysis and real-time telemetry tracking during live race sessions.

---

## Project Structure

The repository is organized into the following components:

### Analysis Scripts

* **[analyze_practice.py](analyze_practice.py)**: Script for analyzing Free Practice sessions. It focuses on long-run
  pace and consistency.
* **[analyze_qualifying.py](analyze_qualifying.py)**: Script for analyzing Qualifying sessions, including flying lap
  comparisons.
* **[analyze_season.py](analyze_season.py)**: Script for visualizing season-long trends, such as championship points
  transitions.
* **[visualizations/](visualizations/)**: A directory containing core visualization methods. The analysis scripts above
  call functions from
  this directory to generate plots.

### Live Tracking System

* **[live.py](live.py)**: Subscribes to the live data stream during race sessions, receiving JSON-like text information.
* **[tracker/](tracker)**: Contains tools to parse the data received by live.py and visualize it as graphs in real-time.

---

## Setup

### Prerequisites

This project requires Python 3.8 or higher. The primary dependency is the **FastF1** library.

### Installation

Clone the repository and install the dependencies listed in [requirements.txt](requirements.txtgi):

```bash
pip install -r requirements.txt
```

## Configuration

Before running the scripts, you must set up your local configuration file:

1. Locate the [sample.config.json](sample.config.json) file in the root directory.
2. Create a copy of it and rename it to [config.json](config.json).
3. Edit [config.json](config.json) to include your specific settings (such as cache directory paths or API credentials
   if required).

```bash
cp sample.config.json config.json
```

## Usage

### Historical Data Analysis

To analyze completed sessions or season-wide data, run the corresponding script:

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
or 2 seconds) and mini-sector progress is monotonic.

## Implementation Details

* **FastF1 Integration**: The project is primarily built on the **FastF1** library, which provides access to F1
  telemetry, lap timing, and session results.
* **Analysis & Visualization**:
    * Post-session scripts (`analyze_*.py`) utilize modular methods defined within
      the [visualizations/](visualizations/) directory to
      ensure consistent plotting logic across different session types.
    * These tools transform raw API data into intuitive visual formats for performance comparison and trend analysis.
* **Live Data Processing**:
    * **Data Subscription**: [live.py](live.py) manages the connection to the live session feed, handling the ingestion
      of
      JSON-like text information.
    * **Real-time Parsing**: The [tracker/](tracker/) module is designed for low-latency parsing of the incoming stream,
      enabling
      the visualization of telemetry and timing data while the session is in progress.
