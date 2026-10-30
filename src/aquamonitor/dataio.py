import json
import math
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from aquamonitor.domain import HydroError, Observation

USGS_URL = "https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous/items"

MAX_PAGES = 100


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
    (value None). The sensor_id is "<site>-<parameter>", e.g. "USGS-01646500-00065".

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
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            observations.append(Observation(timestamp.astimezone(timezone.utc), sensor_id, value))
        except (KeyError, TypeError, ValueError) as exc:
            raise ParseError(f"malformed record #{index}: {exc!r}") from exc
    return sorted(observations, key=lambda obs: (obs.sensor_id, obs.timestamp))
