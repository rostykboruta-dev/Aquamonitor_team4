# Interface Specification (docs/spec.md)

---

## 1. Data Model (`src/aquamonitor/domain.py`)

### Exceptions
* `HydroError(Exception)` — base exception of the project.
* `SensorError(HydroError)` — error related to sensor or invalid parameters.
* `CalibrationError(SensorError)` — calibration error.
* `MissingDataError(HydroError)` — missing data or chronology violation.
* `ThresholdError(HydroError)` — value out of critical limits.

### Classes
* **`Sensor(sensor_id: str, name: str, unit: str, calibration_offset: float = 0.0)`**
  * `apply_calibration(raw_value: float) -> float` — applies calibration offset.
* **`LevelGauge(Sensor)`**: water level gauge (`max_depth: float = 15.0`).
* **`RainGauge(Sensor)`**: precipitation sensor (`unit="mm"`).
* **`TemperatureSensor(Sensor)`**: temperature sensor (`unit="degC"`).
* **`Observation(timestamp: datetime, sensor_id: str, value: float | None)`**
  * `timestamp` must contain time zone information (`tzinfo`).
  * `is_missing() -> bool` — returns `True` if `value is None`.
* **`Series(sensor_id: str, observations: list[Observation] | None = None)`**
  * `add_observation(obs: Observation)` — adds an observation with `sensor_id` and time order validation.
  * `values() -> list[float | None]` — returns all values.
  * `timestamps() -> list[datetime]` — returns all timestamps.
  * `get_valid_observations() -> list[Observation]` — returns observations without missing values.
  * `count_missing() -> int` — returns number of missing values.

---

## 2. Data Module (`src/aquamonitor/dataio.py`)

* **Exception**: `ParseError(HydroError)` — raised on reading or parsing error.
* **Functions**:
  * `parse_usgs_json(json_str: str) -> list[Observation]` — parses a JSON string into a list of `Observation` objects with UTC time zone.
  * `parse_log_line(line: str) -> Observation` — parses a single log line using a regular expression.
  * `clean_observations(observations: list[Observation]) -> tuple[list[Observation], list[str]]` — detects outliers and returns cleaned data alongside a list of rejected records.

---

## 3. Computational Core (`src/aquamonitor/core.py`)

* `moving_average(values: list[float], window: int) -> list[float]` — calculates moving average.
* `moving_median(values: list[float], window: int) -> list[float]` — calculates moving median.
* `linear_interpolate(series: Series) -> list[float]` — restores missing values (`None`) in a `Series`.
* `calculate_metrics(y_true: list[float], y_pred: list[float]) -> dict[str, float]` — returns a dictionary of evaluation metrics with keys `{"RMSE": float, "MAE": float}`.

---

## 4. Analytics (`src/aquamonitor/analytics.py`)

* `aggregate_series_stats(series: Series) -> dict[str, float | int]` — calculates aggregate statistics and returns a dictionary in the format `{"min": float, "max": float, "avg": float, "count": int, "missing_count": int}`.
* `build_time_series_plot(series: Series, output_path: str) -> None` — builds and saves a line plot of levels over time in PNG format at `output_path`.

---

## 5. Infrastructure and CLI (`src/aquamonitor/infra.py`, `cli.py`)

* `@timed` — decorator to measure function execution time.
* `setup_logging(log_filename: str = "aquamonitor.log") -> None` — configures logging.
* `load_config(config_path: str) -> dict` — loads configuration settings from a JSON file.
* **CLI Commands**:
  * `aquamonitor fetch --input <file_path>`
  * `aquamonitor report --input <file_path>`