# Interface Specification (docs/spec.md)

---

## 1. Data Model (`src/aquamonitor/domain.py`)

### Exceptions
* `HydroError(Exception)` — base exception of the project; also raised for invalid `Station` / `Basin` data.
* `SensorError(HydroError)` — invalid sensor, observation, unit or value (including a value outside the allowed range).
* `CalibrationError(SensorError)` — invalid calibration offset.
* `MissingDataError(HydroError)` — chronology violation in a `Series` (an earlier or a duplicate timestamp).
* `ThresholdError(HydroError)` — value out of critical limits (not raised yet, planned for the threshold model).

### Units
* Project units: water level in **meters** (`m`), precipitation in millimeters (`mm`), temperature in `degC`.
* USGS reports gauge height in feet, so values from a source in other units are converted on input.
* `UNIT_FACTORS: dict[tuple[str, str], float]` — `("ft", "m"): 0.3048`, `("in", "mm"): 25.4`.
* `convert_units(value: float, from_unit: str, to_unit: str) -> float` — returns the value unchanged for the same unit;
  a non-number or an unknown pair of units raises `SensorError`.

### Classes
* **`Sensor(sensor_id: str, name: str, unit: str, calibration_offset: float = 0.0)`**
  * `apply_calibration(raw_value: float) -> float` — applies calibration offset.
  * `validate_value(value: float) -> None` — accepts any number; subclasses override it to reject values.
  * `measure(timestamp: datetime, raw_value: float | None, status: str | None = None, unit: str | None = None) -> Observation`
    — converts `raw_value` from `unit` to the sensor unit, applies the calibration offset (given in the sensor unit),
    validates the value and returns an observation of this sensor; `None` stays a missing value.
* **`LevelGauge(Sensor)`**: water level gauge in meters (`unit="m"`).
  * `max_depth: float = 15.0` — descriptive only, must be positive; not used for validation.
  * `level_range: tuple[float, float] | None = None` — allowed (minimum, maximum) level taken from the configuration;
    a level outside it raises `SensorError`; `None` disables the check.
* **`RainGauge(Sensor)`**: precipitation sensor (`unit="mm"`).
* **`TemperatureSensor(Sensor)`**: temperature sensor (`unit="degC"`).
* **`Observation(timestamp: datetime, sensor_id: str, value: float | None, status: str | None = None)`**
  * `timestamp` must contain time zone information (`tzinfo`); `value` is a number (not `bool`) or `None`.
  * `status` — data status from the source (`"Provisional"`, `"Approved"`), a non-empty string or `None`.
  * `is_missing() -> bool` — returns `True` if `value is None`.
* **`Series(sensor_id: str, observations: list[Observation] | None = None)`**
  * `add_observation(obs: Observation)` — checks `sensor_id` and that time strictly increases
    (`MissingDataError` for an earlier or a duplicate timestamp).
  * `values() -> list[float | None]` — returns all values.
  * `timestamps() -> list[datetime]` — returns all timestamps.
  * `get_valid_observations() -> list[Observation]` — returns observations without missing values.
  * `count_missing() -> int` — returns number of missing values.
  * `len(series)` and `for obs in series` — number of observations and iteration in chronological order.
* **`Station(code: str, name: str, latitude: float | None = None, longitude: float | None = None)`** — composition of sensors.
  * `add_sensor(sensor: Sensor)`, `get_sensor(sensor_id: str) -> Sensor`, `sensors -> list[Sensor]`, `len(station)`.
  * Empty code or name, latitude outside ±90 or longitude outside ±180 raise `HydroError`;
    a duplicate or unknown sensor raises `SensorError`.
* **`Basin(name: str)`** — collection of stations.
  * `add_station(station: Station)`, `get_station(code: str) -> Station`, `stations -> list[Station]`, `len(basin)`.
  * Empty name, duplicate or unknown station raise `HydroError`.

---

## 2. Data Module (`src/aquamonitor/dataio.py`)

**Implemented**
* `ParseError(HydroError)` — read or parse error (network failures too).
* `build_usgs_url(site, parameter="00065", period="P7D") -> str` — request URL; site "01646500" becomes "USGS-01646500".
* `fetch_usgs_json(site, parameter="00065", period="P7D", timeout=30.0) -> str` — follows `rel="next"` (up to `MAX_PAGES`), merges pages into one FeatureCollection.
* `parse_usgs_json(json_str) -> list[Observation]` — UTC time, `null` -> `None`, sorted by `(sensor_id, time)`. `sensor_id` = `<site>-<parameter>`, e.g. `USGS-01646500-00065`. Values in feet (`unit_of_measure == "ft"`) are converted to meters with `convert_units`; other units stay as they are. `approval_status` goes to `Observation.status`. Returns all sensors together; filter one `sensor_id` before creating a `Series`.
* `parse_log_line(line) -> Observation` — format: `<time> | <site> | <value or --> | <flag A/P/E>`, e.g. `2026-10-18 12:00:00 | 01646500 | 3.72 | A`. No offset = UTC, `--` = missing, value in meters, `sensor_id` = site code, flag becomes status (A=Approved, P=Provisional, E=Estimated). Errors: `ParseError` with the line text.
* `clean_observations(observations, min_value=-3.0, max_value=30.0, window=5, n_sigmas=5.0, min_deviation=0.15) -> tuple[list[Observation], list[str]]` — values in meters; UTC, drops duplicate timestamps, out-of-range values and spikes (Hampel filter per sensor: a value farther than `n_sigmas` robust deviations and `min_deviation` from the median of `window` neighbours on each side); `None` is kept. Returns (cleaned, log of rejected with the reason). Non-positive `window`, `n_sigmas` or `min_deviation` raise `ValueError`. `Series` rejects duplicate timestamps, so call this before creating a `Series`.
* Data sources checked on 2026-11-01: USGS Water Data API and NOAA NCEI Access Data Service (daily `PRCP` in mm) answer; Kaggle downloads need an account and an API key.


---

## 3. Computational Core (`src/aquamonitor/core.py`)

* `moving_average(values: list[float], window: int) -> list[float]` — calculates moving average.
* `moving_median(values: list[float], window: int) -> list[float]` — calculates moving median.
* `moving_std(values: list[float], window: int) -> list[float]` — calculates moving sample standard deviation (N - 1); a window of one element gives 0.0.
* `linear_interpolate(series: Series, max_gap: timedelta | None = None) -> list[float]` — restores missing values (`None`) in a `Series`; a gap longer than `max_gap` raises `MissingDataError`.
* `calculate_metrics(y_true: list[float], y_pred: list[float]) -> dict[str, float]` — returns `{"RMSE", "MAE", "MAPE", "R2"}`; MAPE is in percent and skips points where the true value is 0; MAPE and R2 are `NaN` when they are undefined; empty lists or different lengths raise `ValueError`.

Added in week 2 (role C):
* `linear_interpolate` fills `None` linearly in real time between the known neighbours; gaps at the start or the end
  take the nearest known value; an empty series gives `[]`; a series with no known values raises `MissingDataError`;
  a non-`Series` argument raises `TypeError`.
* `nearest_interpolate(series: Series) -> list[float]` — fills `None` with the nearest known value in time
  (the earlier one on a tie); same errors as `linear_interpolate`.
* `interpolation_error(series: Series, method: str = "linear", every: int = 5) -> float` — hides every `every`-th
  known point inside the series, interpolates (`"linear"` or `"nearest"`) and returns the mean absolute error
  on the hidden points; bad `method`, `every < 2` or a too short series raise `ValueError`.
* `naive_forecast(values: list[float], horizon: int) -> list[float]` — repeats the last value `horizon` times
  (baseline for Demonstration 1); `horizon` is counted in steps of the series.
* `hours_to_steps(timestamps: list[datetime], hours: float) -> int` — converts a horizon in hours to steps using
  the median interval between timestamps (5-minute data: 12 hours = 144 steps).

Added in week 3 (role C):
* `evaluate_forecast(values: list[float], horizon: int, forecaster=naive_forecast) -> dict[str, float]` — holds out the last `horizon` points, forecasts them from the rest and returns the `calculate_metrics` result; this is what `forecast` in the CLI calls for Demonstration 1. The series must be longer than `horizon` and without gaps.
* `walk_forward(values: list[float], horizon: int, min_train: int, forecaster=naive_forecast) -> dict[str, float]` — moves the cut forward by `horizon` points from `min_train`, forecasts the next `horizon` points each time and averages the metrics (windows where a metric is `NaN` are left out of its average); a too short series raises `ValueError`.
* `forecast_timestamps(timestamps: list[datetime], steps: int) -> list[datetime]` — times of the next `steps` forecast points, step = median interval; used to draw "facts + forecast" on the time axis.


---

## 4. Analytics (`src/aquamonitor/analytics.py`)

* `Period = Literal["day", "week", "month"]`.
* `aggregate_by_period(series: Series, period: Period = "day") -> dict[str, dict[str, float | int | None]]`
  — groups observations by period and computes statistics.
  * Keys: `"YYYY-MM-DD"` (day), `"YYYY-Www"` (ISO 8601 week, e.g. 2025-12-29 belongs to `"2026-W01"`), `"YYYY-MM"` (month);
    grouping uses the time zone of the timestamps (UTC for USGS data); keys go in chronological order.
  * Values: `{"min", "max", "avg", "count", "missing_count"}`; `min`/`max`/`avg` are rounded to 2 digits and are
    `None` for a period in which every value is missing.
  * An unknown `period` raises `ValueError` (checked before the loop, so also for an empty series).
* `generate_console_report(series: Series, period: Period = "day") -> str` — returns the summary table as text;
  it does not print (the CLI prints it). A `None` statistic is shown as `-`.

Planned (week 3, role D):
* `build_time_series_plot(...)` — PNG line plot "observed + forecast" (matplotlib, `Agg` backend).
* A histogram of levels and one common plot style used by both plots.

---

## 5. Infrastructure and CLI (`src/aquamonitor/infra.py`, `cli.py`)

### `infra.py`
* `logger` — the `"aquamonitor"` logger used by the whole package.
* `setup_logging(log_filename: str = "aquamonitor.log") -> None` — writes INFO and higher to the file
  (UTF-8, `asctime levelname name: message`); called once at the start of `main()`.
* `@timed` — logs the execution time of the function at INFO, also when it raises.
* `@log_call` — logs every call and, if the function raises, the exception with its traceback, then re-raises it.

### `cli.py`
* `load_config(config_path: str) -> dict[str, Any]`
  * `.json` — one object with the settings at the top level; a JSON that is broken or is not an object raises `ValueError`.
  * `.ini` — the `[aquamonitor]` section; values stay strings; a broken file raises `ValueError`.
  * A missing file or a missing `[aquamonitor]` section logs a warning and returns `{}`; another extension raises `ValueError`.
  * Keys used now: `period` (for `fetch`), `group_by` (for `report`), `horizon` in hours (for `forecast`);
    a command-line argument wins over the configuration.
* `main() -> None` — `aquamonitor [--config FILE] <command>`, default `--config config.json`:
  * `fetch --site CODE [--period P7D] --out FILE` — downloads gauge height (`00065`) with `fetch_usgs_json`
    and saves the JSON text to `FILE`.
  * `report --input FILE [--sensor ID] [--group-by day|week|month]` — reads a saved USGS JSON file,
    runs `parse_usgs_json` and `clean_observations`, and prints `generate_console_report` (default `day`).
  * `forecast --input FILE [--sensor ID] [--horizon HOURS]` — reads and cleans the file, fills gaps with
    `linear_interpolate`, converts hours to steps with `hours_to_steps` and prints a naive forecast (default 12 hours).
  * `--sensor` is required only when the file holds several sensors.
  * The number of rejected records is printed to stderr as `[CLEAN] Rejected N records`; details go to the log.
* Exit codes: `0` success; `1` — `HydroError`, `ValueError` or `OSError` (message `Error: ...` on stderr, no traceback)
  or no command given (help is printed); `2` — invalid arguments (argparse).
* Installation: `pip install -e .` provides the `aquamonitor` command; `python -m aquamonitor` runs the same `main()`.

Planned (week 3, role E):
* `forecast` prints RMSE/MAE of the naive forecast on the held-out last hours (needs `calculate_metrics`, role C).
* `@retry(n)` for network errors in `fetch`, `@cached`; `level_range` for `LevelGauge` read from the configuration.
