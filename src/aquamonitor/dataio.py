import json
import math
import re
import copy
import statistics
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

from aquamonitor.domain import HydroError, Observation, SensorError, convert_units

USGS_URL = "https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous/items"

MAX_PAGES = 100

_LOG_RE = re.compile(
    r"^\s*(?P<time>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?)"
    r"\s*\|\s*(?P<site>[A-Za-z0-9-]+)"
    r"\s*\|\s*(?P<value>-?\d+(?:\.\d+)?|--)"
    r"\s*\|\s*(?P<flag>[APE])\s*$"
)
_FLAGS = {"A": "Approved", "P": "Provisional", "E": "Estimated"}


class ParseError(HydroError):
    """Data could not be read or parsed."""


def _read_url(url: str, timeout: float) -> str:
    """Downloads one URL and returns the response text.

    Raises:
        ParseError: If the network or the server fails.
    """
    request = urllib.request.Request(url, headers={"Accept": "application/geo+json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as exc:
        raise ParseError(f"cannot read {url}: {exc}") from exc


def _next_url(document: object, base_url: str) -> str | None:
    """Returns the absolute URL of the page with rel="next", or None."""
    links = document.get("links") if isinstance(document, dict) else None
    if not isinstance(links, list):
        return None
    for link in links:
        if isinstance(link, dict) and link.get("rel") == "next" and link.get("href"):
            return urllib.parse.urljoin(base_url, link["href"])
    return None


def fetch_usgs_json(site: str, parameter: str = "00065", period: str = "P7D",
                    timeout: float = 30.0) -> str:
    """Downloads measurements from the USGS Water Data API and returns the JSON text.

    Follows the `rel="next"` links, so a long period is read completely.
    One page is returned as is; several pages are merged into one FeatureCollection.
    At most MAX_PAGES pages are read.

    Raises:
        ValueError: If site is empty.
        ParseError: If the network or the server fails, a page is not valid JSON,
            the pages loop or there are more than MAX_PAGES of them.
    """
    url = build_usgs_url(site, parameter, period)
    first_text = text = _read_url(url, timeout)
    seen, features = {url}, []
    for page in range(1, MAX_PAGES + 1):
        try:
            document = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ParseError(f"page {page} is not valid JSON: {exc}") from exc
        page_features = document.get("features") if isinstance(document, dict) else None
        if not isinstance(page_features, list):
            raise ParseError(f"page {page} has no 'features' list.")
        features.extend(page_features)

        next_url = _next_url(document, url)
        if next_url is None:
            break
        if next_url in seen:
            raise ParseError(f"paging loop detected at {next_url}")
        seen.add(next_url)
        url, text = next_url, _read_url(next_url, timeout)
    else:
        raise ParseError(f"more than {MAX_PAGES} pages, stopped.")

    if page == 1:
        return first_text
    return json.dumps({"type": "FeatureCollection", "features": features,
                       "numberReturned": len(features)})


def build_usgs_url(site: str, parameter: str = "00065", period: str = "P7D") -> str:
    """Builds the request URL for the measurements of one site and parameter.

    Args:
        site: Site number ("01646500") or full id ("USGS-01646500").
        parameter: USGS parameter code, "00065" is the gauge height.
        period: ISO 8601 duration ("P7D", "PT6H") or interval "2026-10-01/2026-10-07".

    Raises:
        ValueError: If site is empty.
    """
    site = site.strip()
    if not site:
        raise ValueError("site must not be empty.")
    if "-" not in site:
        site = f"USGS-{site}"
    query = {"f": "json", "monitoring_location_id": site, "parameter_code": parameter,
             "time": period, "limit": 10_000, "skipGeometry": "true"}
    return f"{USGS_URL}?{urllib.parse.urlencode(query)}"


def parse_usgs_json(json_str: str) -> list[Observation]:
    """Parses a USGS JSON response (GeoJSON `features`) into observations.

    Timestamps become UTC and a null value becomes a missing observation
    (value None). Gauge height in feet (`unit_of_measure` "ft") is converted
    to meters; other units are kept as they are. The `approval_status` of the
    record becomes `Observation.status`. The sensor_id is "<site>-<parameter>",
    e.g. "USGS-01646500-00065".

    Returns:
        Observations sorted by sensor_id and time, so the slice of one sensor
        can be put into a Series directly. An empty response gives an empty list.

    Raises:
        ParseError: If the text is not valid JSON, has no `features` list
            or a record is malformed.
    """
    if not isinstance(json_str, str):
        raise ParseError("JSON input must be a string.")
    try:
        document = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ParseError(f"invalid JSON: {exc}") from exc
    features = document.get("features") if isinstance(document, dict) else None
    if not isinstance(features, list):
        raise ParseError("expected a JSON object with a 'features' list.")

    observations = []
    for index, feature in enumerate(features):
        try:
            props = feature["properties"]
            sensor_id = f"{props['monitoring_location_id']}-{props['parameter_code']}"
            timestamp = datetime.fromisoformat(props["time"])
            raw_value = props.get("value")
            if raw_value is None:
                value = None
            elif isinstance(raw_value, bool):
                raise ValueError("boolean is not a measurement")
            else:
                value = float(raw_value)
                if not math.isfinite(value):
                    raise ValueError(f"value is not finite: {raw_value!r}")
            if value is not None and props.get("unit_of_measure") == "ft":
                value = convert_units(value, "ft", "m")
            status = props.get("approval_status")
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            observations.append(Observation(
                timestamp.astimezone(timezone.utc), sensor_id, value, status))
        except (KeyError, TypeError, ValueError, SensorError) as exc:
            raise ParseError(f"malformed record #{index}: {exc!r}") from exc
    return sorted(observations, key=lambda obs: (obs.sensor_id, obs.timestamp))


def parse_log_line(line: str) -> Observation:
    """Parses one line of a station log into an observation.

    Value is in meters; the flag becomes the status (A=Approved, P=Provisional, E=Estimated).

    Format: ``<time> | <site> | <value or --> | <flag>``, e.g.
    ``2026-10-18 12:00:00 | 01646500 | 3.72 | A``. Time without an offset is UTC;
    ``--`` means a missing value; flag is A, P or E. The site code is the sensor_id.


    Raises:
        ParseError: If the line does not match the format or the time is invalid.
            The message contains the line.
    """
    if not isinstance(line, str):
        raise ParseError(f"log line must be a string, got {type(line).__name__}.")
    match = _LOG_RE.match(line)
    if match is None:
        raise ParseError(f"line does not match the log format: {line!r}")
    try:
        timestamp = datetime.fromisoformat(match["time"].replace(" ", "T"))
    except ValueError as exc:
        raise ParseError(f"bad timestamp in line {line!r}: {exc}") from exc
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    raw = match["value"]
    value = None if raw == "--" else float(raw)
    return Observation(timestamp.astimezone(timezone.utc), match["site"], value,
                       _FLAGS[match["flag"]])


def _find_spikes(observations: list[Observation], window: int, n_sigmas: float,
                 min_deviation: float) -> dict[int, str]:
    """Hampel filter: finds values far from the median of their neighbours.

    Observations must be sorted by (sensor_id, time); each sensor is checked
    on its own, missing values are skipped. A value is a spike when it differs
    from the median of `window` neighbours on each side by more than
    `n_sigmas` robust deviations and by more than `min_deviation`. A steady
    rise is not a spike because the median follows the trend.

    Returns:
        Index in `observations` -> reason for every spike.
    """
    groups: dict[str, list[int]] = {}
    for index, obs in enumerate(observations):
        if obs.value is not None:
            groups.setdefault(obs.sensor_id, []).append(index)
    spikes: dict[int, str] = {}
    for indexes in groups.values():
        values = [observations[i].value for i in indexes]
        for pos, index in enumerate(indexes):
            near = values[max(0, pos - window): pos + window + 1]
            centre = statistics.median(near)
            mad = statistics.median(abs(x - centre) for x in near)
            limit = max(n_sigmas * 1.4826 * mad, min_deviation)
            if abs(values[pos] - centre) > limit:
                spikes[index] = (f"spike {values[pos]}: differs from median "
                                 f"{centre:.3f} by more than {limit:.3f}")
    return spikes


def clean_observations(
        observations: list[Observation],
        min_value: float = -3.0,
        max_value: float = 30.0,
        window: int = 5,
        n_sigmas: float = 5.0,
        min_deviation: float = 0.15,
) -> tuple[list[Observation], list[str]]:
    """Cleans observations: UTC time, duplicates, out-of-range values and spikes.

    Values are in meters. Missing values (None) are gaps, not outliers, so they are kept.
    The result is sorted by (sensor_id, time).

    Args:
        observations: Observations of any sensors and time offsets.
        min_value: Lowest allowed value (inclusive).
        max_value: Highest allowed value (inclusive).
        window: Neighbours on each side that the spike check compares with.
        n_sigmas: Spike threshold in robust standard deviations.
        min_deviation: Smallest difference from the neighbours' median (meters)
            that can be a spike, so normal noise on a flat river is kept.

    Returns:
        A tuple (cleaned observations, log of rejected records, one string each).

    Raises:
        ValueError: If window, n_sigmas or min_deviation is not positive.
    """
    if window < 1 or n_sigmas <= 0 or min_deviation <= 0:
        raise ValueError("window, n_sigmas and min_deviation must be positive.")
    kept: list[Observation] = []
    rejected: list[str] = []
    seen: set[tuple[str, datetime]] = set()
    for obs in sorted(observations, key=lambda o: (o.sensor_id, o.timestamp)):
        stamp = obs.timestamp.astimezone(timezone.utc)
        label = f"{obs.sensor_id} {stamp.isoformat()}"
        if (obs.sensor_id, stamp) in seen:
            rejected.append(f"{label}: duplicate timestamp")
            continue
        seen.add((obs.sensor_id, stamp))
        if obs.value is not None and not min_value <= obs.value <= max_value:
            rejected.append(f"{label}: value {obs.value} outside [{min_value}, {max_value}]")
            continue
        if obs.timestamp.utcoffset() != timedelta(0):
            obs = copy.copy(obs)
            obs.timestamp = stamp
        kept.append(obs)
    spikes = _find_spikes(kept, window, n_sigmas, min_deviation)
    for index in sorted(spikes):
        obs = kept[index]
        rejected.append(f"{obs.sensor_id} {obs.timestamp.isoformat()}: {spikes[index]}")
    return [obs for i, obs in enumerate(kept) if i not in spikes], rejected

