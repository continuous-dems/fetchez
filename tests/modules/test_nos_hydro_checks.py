"""nos_hydro must not lose surveys, or the whole module, to a busy server.

Each survey's directory pages are read and its data files checked before they
are listed. A failed request used to raise out of the module after
``fetch_req``'s retries (a 404 included), so one bad survey dropped every NOS
file for the region. Now a 404/410 means "not there" and is skipped; other
failures are retried, then logged; a file that cannot be checked is kept, and
the list is not cached.
"""

import json
import logging
from typing import ClassVar

import pytest
import requests

from fetchez import spatial
from fetchez.modules import hydronos

REGION = spatial.Region(-121.30, -120.95, 35.45, 35.80, srs="EPSG:4326")
LOGGER = "fetchez.modules.hydronos"
RANGE = "H10001-H12000"


def _survey(survey_id, bags=False):
    return {
        "attributes": {
            "SURVEY_ID": survey_id,
            "SURVEY_YEAR": 1990,
            "DOWNLOAD_URL": f"https://example.test/{RANGE}/{survey_id}",
            "BAGS_EXIST": "TRUE" if bags else "FALSE",
        }
    }


def _dir(survey_id):
    return f"{hydronos.NOS_DATA_URL}{RANGE}/{survey_id}/"


def _xyz(survey_id):
    return f"{_dir(survey_id)}GEODAS/{survey_id}.xyz.gz"


def _html(*hrefs):
    return (
        "<html><body>"
        + "".join(f'<a href="{h}">{h}</a>' for h in hrefs)
        + "</body></html>"
    )


class FakeQuery:
    """The NOS survey search: returns FakeQuery.features."""

    features: ClassVar[list] = []

    def __init__(self, url):
        self.url = url

    def fetch_req(self, params=None, **kwargs):
        payload = {"features": FakeQuery.features}

        class Response:
            status_code = 200
            text = json.dumps(payload)

            def json(self):
                return payload

        return Response()


class FakeWeb:
    """GET/HEAD answers per URL: a list of status codes, (200, html) or exceptions."""

    get_answers: ClassVar[dict] = {}
    head_answers: ClassVar[dict] = {}

    @staticmethod
    def _answer(table, url):
        queue = table.get(url, [404])
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(answer, Exception):
            raise answer
        response = requests.Response()
        if isinstance(answer, tuple):
            response.status_code, text = answer
            response._content = text.encode()
        else:
            response.status_code = answer
            response._content = b""
        return response

    @classmethod
    def get(cls, url, **kwargs):
        return cls._answer(cls.get_answers, url)

    @classmethod
    def head(cls, url, **kwargs):
        return cls._answer(cls.head_answers, url)


@pytest.fixture(autouse=True)
def fake_server(monkeypatch):
    FakeQuery.features = []
    FakeWeb.get_answers = {}
    FakeWeb.head_answers = {}
    monkeypatch.setattr(hydronos.core, "Fetch", FakeQuery)
    monkeypatch.setattr(hydronos.requests, "get", FakeWeb.get)
    monkeypatch.setattr(hydronos.requests, "head", FakeWeb.head)
    monkeypatch.setattr(hydronos.time, "sleep", lambda _: None)


def _run(tmp_path, datatype="xyz"):
    mod = hydronos.HydroNOS(src_region=REGION, outdir=str(tmp_path), datatype=datatype)
    mod.run()
    return mod


def _urls(mod):
    return sorted(r["url"] for r in mod.results)


def _cache_files(tmp_path):
    return list(tmp_path.glob("**/.fetchez_cache/*.json"))


def _geodas_survey(survey_id, head):
    FakeWeb.get_answers[_dir(survey_id)] = [(200, _html("GEODAS/"))]
    FakeWeb.head_answers[_xyz(survey_id)] = head


def test_existing_xyz_is_listed_and_cached(tmp_path):
    FakeQuery.features = [_survey("H10001")]
    _geodas_survey("H10001", [200])
    mod = _run(tmp_path)

    assert _urls(mod) == [_xyz("H10001")]
    assert mod._discovery_failed is False
    assert len(_cache_files(tmp_path)) == 1


def test_missing_xyz_is_skipped_quietly(tmp_path, caplog):
    caplog.set_level(logging.WARNING, logger=LOGGER)
    FakeQuery.features = [_survey("H10001")]
    _geodas_survey("H10001", [404])
    mod = _run(tmp_path)

    assert mod.results == []
    assert mod._discovery_failed is False
    assert not caplog.records


def test_transient_failures_are_retried(tmp_path):
    FakeQuery.features = [_survey("H10001")]
    FakeWeb.get_answers[_dir("H10001")] = [
        requests.Timeout("slow"),
        (200, _html("GEODAS/")),
    ]
    FakeWeb.head_answers[_xyz("H10001")] = [503, 200]
    mod = _run(tmp_path)

    assert _urls(mod) == [_xyz("H10001")]
    assert mod._discovery_failed is False


@pytest.mark.parametrize(
    "failure",
    [requests.Timeout("slow"), requests.ConnectionError("reset"), 503],
    ids=["timeout", "connection-error", "503"],
)
def test_unverifiable_xyz_is_kept_and_flagged(tmp_path, caplog, failure):
    caplog.set_level(logging.WARNING, logger=LOGGER)
    FakeQuery.features = [_survey("H10001")]
    _geodas_survey("H10001", [failure])
    mod = _run(tmp_path)

    assert _urls(mod) == [_xyz("H10001")]
    assert mod._discovery_failed is True
    assert any("could not check" in r.getMessage() for r in caplog.records)
    assert _cache_files(tmp_path) == []


def test_missing_survey_directory_does_not_stop_other_surveys(tmp_path, caplog):
    caplog.set_level(logging.WARNING, logger=LOGGER)
    FakeQuery.features = [_survey("H10001"), _survey("H10002")]
    FakeWeb.get_answers[_dir("H10001")] = [404]
    _geodas_survey("H10002", [200])
    mod = _run(tmp_path)

    assert _urls(mod) == [_xyz("H10002")]
    assert mod._discovery_failed is False
    assert not caplog.records


def test_unreadable_survey_directory_is_flagged_and_others_continue(tmp_path, caplog):
    caplog.set_level(logging.WARNING, logger=LOGGER)
    FakeQuery.features = [_survey("H10001"), _survey("H10002")]
    FakeWeb.get_answers[_dir("H10001")] = [requests.Timeout("slow")]
    _geodas_survey("H10002", [200])
    mod = _run(tmp_path)

    assert _urls(mod) == [_xyz("H10002")]
    assert mod._discovery_failed is True
    assert any("could not read" in r.getMessage() for r in caplog.records)
    assert _cache_files(tmp_path) == []


def test_unreadable_bag_directory_is_flagged_not_fatal(tmp_path):
    FakeQuery.features = [_survey("H10001", bags=True), _survey("H10002", bags=True)]
    FakeWeb.get_answers[f"{_dir('H10001')}BAG/"] = [503]
    FakeWeb.get_answers[f"{_dir('H10002')}BAG/"] = [(200, _html("H10002_1m.bag"))]
    mod = _run(tmp_path, datatype="bag")

    assert _urls(mod) == [f"{_dir('H10002')}BAG/H10002_1m.bag"]
    assert mod._discovery_failed is True


def test_gridded_data_checks(tmp_path):
    FakeQuery.features = [_survey("H10001"), _survey("H10002")]
    for sid in ("H10001", "H10002"):
        FakeWeb.get_answers[_dir(sid)] = [(200, _html("Gridded_Data/"))]
    FakeWeb.get_answers[f"{_dir('H10001')}Gridded_Data/"] = [
        (200, _html("a.xyz.gz", "b.xyz.gz"))
    ]
    FakeWeb.head_answers[f"{_dir('H10001')}Gridded_Data/a.xyz.gz"] = [200]
    FakeWeb.head_answers[f"{_dir('H10001')}Gridded_Data/b.xyz.gz"] = [404]
    FakeWeb.get_answers[f"{_dir('H10002')}Gridded_Data/"] = [404]
    mod = _run(tmp_path, datatype="grid")

    assert _urls(mod) == [f"{_dir('H10001')}Gridded_Data/a.xyz.gz"]
    assert mod._discovery_failed is False
