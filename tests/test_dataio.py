import json
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from aquamonitor.dataio import (
    ParseError,
    build_usgs_url,
    fetch_usgs_json,
    parse_usgs_json,
)
from aquamonitor.domain import HydroError, Series

SAMPLE = Path(__file__).parent / "data" / "usgs_sample.json"


def feature(time: str, value, site: str = "USGS-123", parameter: str = "00065") -> dict:
    return {"type": "Feature", "properties": {
        "monitoring_location_id": site, "parameter_code": parameter,
        "time": time, "value": value, "unit_of_measure": "ft"}}


class TestParseUsgsJson(unittest.TestCase):

    def test_real_sample_gives_sorted_utc_observations(self) -> None:
        """A saved response of the USGS API is turned into observations."""
        result = parse_usgs_json(SAMPLE.read_text(encoding="utf-8"))

        self.assertEqual(len(result), 48)
        self.assertEqual(result[0].sensor_id, "USGS-01646500-00065")
        self.assertIsInstance(result[0].value, float)
        self.assertEqual(result[0].timestamp.utcoffset(), timedelta(0))
        stamps = [obs.timestamp for obs in result]
        self.assertEqual(stamps, sorted(stamps))

    def test_result_fits_into_series(self) -> None:
        """Observations of one sensor satisfy the chronology rule of Series."""
        result = parse_usgs_json(SAMPLE.read_text(encoding="utf-8"))

        self.assertEqual(len(Series(result[0].sensor_id, result)), 48)

    def test_null_value_is_missing_and_offset_becomes_utc(self) -> None:
        text = json.dumps({"features": [
            feature("2026-10-18T15:05:00+03:00", "3.7"),
            feature("2026-10-18T12:00:00+00:00", None),
        ]})
        result = parse_usgs_json(text)

        self.assertEqual([obs.value for obs in result], [None, 3.7])
        self.assertTrue(result[0].is_missing())
        self.assertEqual(result[1].timestamp, datetime(2026, 10, 18, 12, 5, tzinfo=timezone.utc))

    def test_empty_response_gives_empty_list(self) -> None:
        self.assertEqual(parse_usgs_json('{"features": []}'), [])

    def test_bad_input_raises_parse_error(self) -> None:
        good_time = "2026-10-18T12:00:00+00:00"
        bad_inputs = {
            "not json": "{oops",
            "empty string": "",
            "json array": "[]",
            "no features": '{"hello": 1}',
            "features not a list": '{"features": 5}',
            "feature is not an object": '{"features": [null]}',
            "no properties": '{"features": [{"type": "Feature"}]}',
            "no time": json.dumps({"features": [{"properties": {
                "monitoring_location_id": "USGS-1", "parameter_code": "00065", "value": "1"}}]}),
            "bad timestamp": json.dumps({"features": [feature("yesterday", "1")]}),
            "text value": json.dumps({"features": [feature(good_time, "Ice")]}),
        }
        for name, text in bad_inputs.items():
            with self.subTest(name), self.assertRaises(ParseError):
                parse_usgs_json(text)

    def test_non_string_input_raises_parse_error(self) -> None:
        with self.assertRaises(ParseError):
            parse_usgs_json(None)  # type: ignore[arg-type]

    def test_parse_error_belongs_to_project_hierarchy(self) -> None:
        self.assertTrue(issubclass(ParseError, HydroError))


class TestUsgsRequest(unittest.TestCase):

    def test_build_url_adds_agency_prefix(self) -> None:
        url = build_usgs_url(" 01646500 ", period="PT6H")

        self.assertIn("monitoring_location_id=USGS-01646500", url)
        self.assertIn("parameter_code=00065", url)
        self.assertIn("time=PT6H", url)

    def test_build_url_keeps_full_id_and_rejects_empty_site(self) -> None:
        self.assertIn("monitoring_location_id=USGS-01646500", build_usgs_url("USGS-01646500"))
        with self.assertRaises(ValueError):
            build_usgs_url("   ")

    def test_fetch_returns_response_text(self) -> None:
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"features": []}'
        with patch("urllib.request.urlopen", return_value=response) as urlopen:
            text = fetch_usgs_json("01646500", period="P1D", timeout=5)

        self.assertEqual(text, '{"features": []}')
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 5)
        self.assertIn("time=P1D", urlopen.call_args.args[0].full_url)

    def test_network_failure_becomes_parse_error(self) -> None:
        for failure in (urllib.error.URLError("no network"), TimeoutError("slow")):
            with self.subTest(type(failure).__name__), \
                    patch("urllib.request.urlopen", side_effect=failure):
                with self.assertRaises(ParseError):
                    fetch_usgs_json("01646500")


if __name__ == "__main__":
    unittest.main()
