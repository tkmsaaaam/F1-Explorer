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
```

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
