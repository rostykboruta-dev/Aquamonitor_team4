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
    parse_log_line,
    clean_observations,
)
from aquamonitor.domain import HydroError, Series, Observation

SAMPLE = Path(__file__).parent / "data" / "usgs_sample.json"
NEXT = "https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous/items?cursor=abc"


def feature(time: str, value, site: str = "USGS-123", parameter: str = "00065") -> dict:
    return {"type": "Feature", "properties": {
        "monitoring_location_id": site, "parameter_code": parameter,
        "time": time, "value": value, "unit_of_measure": "ft"}}


def fake_response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(payload).encode("utf-8")
    return response


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

    def test_bool_and_nan_values_raise_parse_error(self) -> None:
        """True, NaN and infinity are not valid measurements."""
        for bad in (True, "NaN", "inf", float("nan")):
            with self.subTest(repr(bad)), self.assertRaises(ParseError):
                parse_usgs_json(json.dumps(
                    {"features": [feature("2026-10-18T12:00:00+00:00", bad)]}))


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


class TestUsgsPaging(unittest.TestCase):

    def test_two_pages_are_merged(self) -> None:
        """Pages linked by rel="next" become one response."""
        page1 = {"features": [feature("2026-10-18T10:00:00+00:00", "1.0")],
                 "links": [{"rel": "next", "href": NEXT}]}
        page2 = {"features": [feature("2026-10-18T10:05:00+00:00", "1.1"),
                              feature("2026-10-18T10:10:00+00:00", "1.2")],
                 "links": [{"rel": "self", "href": NEXT}]}
        with patch("urllib.request.urlopen",
                   side_effect=[fake_response(page1), fake_response(page2)]) as urlopen:
            text = fetch_usgs_json("01646500")

        self.assertEqual(urlopen.call_count, 2)
        self.assertEqual(urlopen.call_args_list[1].args[0].full_url, NEXT)
        self.assertEqual([o.value for o in parse_usgs_json(text)], [1.0, 1.1, 1.2])

    def test_paging_loop_raises_parse_error(self) -> None:
        """A next link to an already seen page is not followed forever."""
        page = {"features": [], "links": [{"rel": "next", "href": NEXT}]}
        with patch("urllib.request.urlopen",
                   side_effect=lambda *a, **k: fake_response(page)):
            with self.assertRaises(ParseError):
                fetch_usgs_json("01646500")

    def test_too_many_pages_raises_parse_error(self) -> None:
        """Endless unique pages stop at MAX_PAGES."""

        def pages(request, timeout):
            href = NEXT + "x" * len(request.full_url)  # every URL is new
            return fake_response({"features": [], "links": [{"rel": "next", "href": href}]})

        with patch("urllib.request.urlopen", side_effect=pages), \
                patch("aquamonitor.dataio.MAX_PAGES", 3):
            with self.assertRaises(ParseError):
                fetch_usgs_json("01646500")

    def test_broken_second_page_raises_parse_error(self) -> None:
        page1 = {"features": [], "links": [{"rel": "next", "href": NEXT}]}
        bad = MagicMock()
        bad.__enter__.return_value.read.return_value = b"{oops"
        with patch("urllib.request.urlopen", side_effect=[fake_response(page1), bad]):
            with self.assertRaises(ParseError):
                fetch_usgs_json("01646500")


class TestParseLogLine(unittest.TestCase):

    def test_normal_line(self) -> None:
        obs = parse_log_line("2026-10-18 12:00:00 | 01646500 | 3.72 | A")

        self.assertEqual(obs.sensor_id, "01646500")
        self.assertEqual(obs.value, 3.72)
        self.assertEqual(obs.timestamp, datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc))

    def test_missing_value_and_offset(self) -> None:
        obs = parse_log_line("2026-10-18T12:00+03:00 | 01646500 | -- | P")

        self.assertTrue(obs.is_missing())
        self.assertEqual(obs.timestamp, datetime(2026, 10, 18, 9, 0, tzinfo=timezone.utc))

    def test_bad_lines_raise_parse_error_with_context(self) -> None:
        bad_lines = ["", "garbage", "2026-10-18 12:00:00 | 01646500 | 3.7 | X",
                     "2026-10-18 12:00:00 | 01646500 | abc | A",
                     "2026-13-01 12:00:00 | 01646500 | 3.7 | A",
                     "2026-10-18 12:00:00 | 01646500 | 3.7"]
        for line in bad_lines:
            with self.subTest(line), self.assertRaises(ParseError) as ctx:
                parse_log_line(line)
            self.assertIn(line, str(ctx.exception))

    def test_non_string_raises_parse_error(self) -> None:
        with self.assertRaises(ParseError):
            parse_log_line(None)  # type: ignore[arg-type]


class TestCleanObservations(unittest.TestCase):

    def test_outlier_duplicate_and_offset(self) -> None:
        utc = timezone.utc
        plus3 = timezone(timedelta(hours=3))
        data = [
            Observation(datetime(2026, 10, 18, 12, 0, tzinfo=utc), "S1", 3.0),
            Observation(datetime(2026, 10, 18, 12, 0, tzinfo=utc), "S1", 3.1),  # duplicate
            Observation(datetime(2026, 10, 18, 12, 5, tzinfo=utc), "S1", 999.0),  # outlier
            Observation(datetime(2026, 10, 18, 15, 10, tzinfo=plus3), "S1", None),
        ]
        cleaned, rejected = clean_observations(data)

        self.assertEqual([o.value for o in cleaned], [3.0, None])
        self.assertEqual(cleaned[1].timestamp, datetime(2026, 10, 18, 12, 10, tzinfo=utc))
        self.assertEqual(len(rejected), 2)
        self.assertIn("duplicate", rejected[0])
        self.assertIn("999.0", rejected[1])

    def test_empty_input(self) -> None:
        self.assertEqual(clean_observations([]), ([], []))

    def test_boundaries_are_inclusive(self) -> None:
        now = datetime(2026, 10, 18, tzinfo=timezone.utc)
        data = [Observation(now, "S1", -10.0),
                Observation(now + timedelta(minutes=5), "S1", 100.0)]
        self.assertEqual(len(clean_observations(data)[0]), 2)


if __name__ == "__main__":
    unittest.main()
