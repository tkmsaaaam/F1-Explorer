# F1-Explorer Agent Guide

## Project and References

A Python project that analyzes lap and telemetry data from FastF1 to generate charts and offline HTML reports.

- Refer to `README.md` for setup, usage, and configuration details.
- For session-specific changes, review the relevant specification in `specs/PRACTICE.md`, `specs/QUALIFYING.md`, or `specs/RACE.md`, along with existing tests.
- If the specification and implementation differ, identify discrepancies relevant to the request before making changes.

## Code Organization

- `analyze_*.py`, `compare.py`: Analysis entrypoints and orchestration.
- `f1_explorer/`: Configuration, analysis state, constants, shared utilities, and segment boundary estimation.
- `visualizations/`: Metric calculations, charts, and report generation. Reuse existing helpers for shared styles and output handling.
- `templates/template.html`: Shared HTML and browser behavior for session reports.
- `live.py`, `track.py`, `tracker/`: Live data collection, analysis, and visualization.
- `tests/`: Tests run with pytest. Preserve the existing unittest style where used.

## Implementation Guidelines

- Follow the naming, type annotations, and style of surrounding code, and keep changes relevant to the request.
- Handle missing values, empty data, and invalid laps in FastF1 / pandas. Make time and distance units and comparison criteria explicit; do not treat missing data as a measured zero.
- Keep session reports self-contained and viewable offline. Do not introduce external CDN dependencies.
- When changing configuration handling, check compatibility with existing keys and legacy formats, and preserve unrelated settings.
- Do not replace saved segment boundaries with `--force`. Re-estimation belongs to `--refresh-separators`; see `README.md` for details.
- Update the relevant README, specifications, and samples when usage or output behavior changes.

## Running and Validating Changes

Run commands from the repository root so relative paths resolve correctly. Use the Python interpreter from the existing `.venv` when available.

```bash
# Install dependencies when setup is needed
python -m pip install -r requirements.txt

# Run relevant tests (adjust the filename for the change)
python -m pytest tests/test_report.py -q -W error::DeprecationWarning

# Run the full test suite with coverage
python -m coverage run -m pytest tests -q -W error::DeprecationWarning
python -m coverage report -m
```

- If pytest is missing from the environment, install it for development. It is not currently listed explicitly in `requirements.txt`.
- Add or update tests that verify behavior changes and bug fixes. Test execution is unnecessary for documentation-only changes.
- Run relevant tests first, and also run the full suite when changes affect shared logic or multiple sessions. Do not suppress DeprecationWarning without justification.
- Use small synthetic datasets, mocks, and temporary directories in tests. Avoid dependencies on external APIs or a personal `config.json`.
- Report JavaScript tests require Node.js. Mention skipped checks in the completion report.
- When changing chart or HTML appearance, display the output when possible to verify layout and interactions.
- Analysis scripts fetch data and update configuration or outputs. Do not run them without a specific purpose as a substitute for tests.

## Preserving Local Data and Work

- Check `git status` before starting work and preserve the user's uncommitted changes.
- `config.json` contains local settings. Copy `sample.config.json` only when a new configuration file is needed; do not overwrite an existing file.
- Keep local data and generated artifacts such as `cache/`, `images/`, `reports/`, `live/`, and `htmlcov/` out of ordinary code changes.
- Dependencies are pinned in `requirements.txt`. Update only those needed for the change.
- On completion, briefly describe the changes, validation performed, and anything left unverified.
