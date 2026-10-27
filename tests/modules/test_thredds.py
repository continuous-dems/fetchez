"""Isolated THREDDS tests: inject lightweight Fetchez stubs, no network needed."""

import importlib.util
import sys
import types
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlsplit

import pytest


NS = "http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0"

CATALOG = f'''<catalog xmlns="{NS}" xmlns:xlink="http://www.w3.org/1999/xlink">
  <service name="all" serviceType="Compound" base="">
    <service name="http" serviceType="HTTPServer" base="/thredds/fileServer/" />
    <service name="ncss" serviceType="NetcdfSubset" base="/thredds/ncss/grid/" />
    <service name="dods" serviceType="OPENDAP" base="/thredds/dodsC/" />
    <service name="wcs" serviceType="WCS" base="/thredds/wcs/" />
  </service>
  <dataset name="Container" serviceName="all">
    <geospatialCoverage><northsouth><start>30</start><size>5</size></northsouth>
      <eastwest><start>-120</start><size>5</size></eastwest></geospatialCoverage>
    <dataset name="Sample_Bathy_navd88_2020.nc" ID="bathy" urlPath="regional/bathy.nc" />
    <dataset name="Sample_Ocean_2021.nc" ID="ocean" urlPath="regional/ocean.nc" />
  </dataset>
  <catalogRef name="next" xlink:href="sub/catalog.xml" />
</catalog>'''
SUBCATALOG = f'''<catalog xmlns="{NS}">
 <service name="http" serviceType="HTTPServer" base="/thredds/fileServer/" />
 <dataset name="Extra.nc" ID="extra" serviceName="http" urlPath="regional/extra.nc"/>
</catalog>'''


@pytest.fixture
def _thredds(monkeypatch):
    fetchez = types.ModuleType("fetchez")
    fetchez.__path__ = []
    core = types.ModuleType("fetchez.core")
    cli = types.ModuleType("fetchez.cli")
    modules = types.ModuleType("fetchez.modules")
    spatial = types.ModuleType("fetchez.spatial")

    class Region:
        def __init__(self, w, e, s, n, srs=None):
            self.bounds = (w, e, s, n)

        def valid_p(self):
            w, e, s, n = self.bounds
            return w < e and s < n

        def __iter__(self):
            return iter(self.bounds)

    class FetchModule:
        def __init__(self, region=None, **kwargs):
            self._init_kwargs = {"region": region}
            self.wgs_region = region
            self.results = []
            self.status = 0

        def add_entry_to_results(self, url, dst_fn, data_type, metadata=None, **kwargs):
            self.results.append(
                dict(
                    url=url,
                    name=dst_fn,
                    data_type=data_type,
                    metadata=metadata,
                    **kwargs,
                )
            )

    cli.cli_opts = lambda **kwargs: lambda cls: cls
    spatial.Region = Region
    modules.FetchModule = FetchModule
    pages = {
        "https://example.org/thredds/catalog/regional/catalog.xml": CATALOG,
        "https://example.org/thredds/catalog/regional/sub/catalog.xml": SUBCATALOG,
    }
    calls = []

    class Fetch:
        def __init__(self, url):
            self.url = url

        def fetch_xml(self):
            calls.append(self.url)
            return ET.fromstring(pages[self.url])

    core.Fetch = Fetch
    fetchez.core = core
    for name, obj in [
        ("fetchez", fetchez),
        ("fetchez.core", core),
        ("fetchez.cli", cli),
        ("fetchez.modules", modules),
        ("fetchez.spatial", spatial),
    ]:
        monkeypatch.setitem(sys.modules, name, obj)
    spec = importlib.util.find_spec("fetchez.modules.thredds")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, Region, calls


def test_nested_catalog_and_http_services(_thredds):
    mod, Region, calls = _thredds
    m = mod.THREDDS(
        url="https://example.org/thredds/catalog/regional/catalog.xml",
        region=Region(-119, -118, 31, 32),
    ).run()
    assert len(m.results) == 3
    assert (
        m.results[0]["url"]
        == "https://example.org/thredds/fileServer/regional/bathy.nc"
    )
    assert any("/sub/catalog.xml" in u for u in calls)


def test_dataset_and_pattern_filter(_thredds):
    mod, _, _ = _thredds
    m = mod.THREDDS(
        url="https://example.org/thredds/catalog/regional/catalog.xml",
        dataset="Bathy",
        pattern="*.nc",
        recursive=False,
    ).run()
    assert len(m.results) == 1
    assert m.results[0]["metadata"]["thredds_id"] == "bathy"


def test_spatial_exclusion_and_unknown_policy(_thredds):
    mod, Region, _ = _thredds
    m = mod.THREDDS(
        url="https://example.org/thredds/catalog/regional/catalog.xml",
        region=Region(10, 11, 10, 11),
        recursive=False,
    ).run()
    assert m.results == []
    strict = mod.THREDDS(
        url="https://example.org/thredds/catalog/regional/sub/catalog.xml",
        region=Region(-119, -118, 31, 32),
        spatial="strict",
    ).run()
    assert strict.results == []
    known = mod.THREDDS(
        url="https://example.org/thredds/catalog/regional/sub/catalog.xml",
        region=Region(-119, -118, 31, 32),
    ).run()
    assert len(known.results) == 1


def test_ncss_subset_from_catalog(_thredds):
    mod, Region, _ = _thredds
    m = mod.THREDDS(
        url="https://example.org/thredds/catalog/regional/catalog.xml",
        service="NCSS",
        dataset="Bathy",
        recursive=False,
        region=Region(-119, -118, 31, 32),
        parameters={"var": "z", "addLatLon": True},
    ).run()

    assert len(m.results) == 1
    url = m.results[0]["url"]
    assert url.startswith("https://example.org/thredds/ncss/grid/regional/bathy.nc?")
    q = parse_qs(urlsplit(url).query)
    assert q["var"] == ["z"] and q["west"] == ["-119"]
    assert q["addLatLon"] == ["true"]


def test_d2c_direct_ncss_compatible_query(_thredds):
    mod, Region, _ = _thredds
    m = mod.THREDDS(
        url="https://pae-paha.pacioos.hawaii.edu/thredds/ncss/grid/dist2coast_1deg",
        service="NCSS",
        region=Region(-120, -119, 30, 31),
        parameters={"var": "dist", "addLatLon": True},
    ).run()
    assert len(m.results) == 1
    query = parse_qs(urlsplit(m.results[0]["url"]).query)
    assert query["var"] == ["dist"]
    assert query["north"] == ["31"]
    assert query["accept"] == ["netcdf"]
    assert m.results[0]["data_type"] == "netcdf"


def test_wcs_and_opendap_services(_thredds):
    mod, Region, _ = _thredds
    url = "https://example.org/thredds/catalog/regional/catalog.xml"
    wcs = mod.THREDDS(
        url=url,
        service="WCS",
        region=Region(-119, -118, 31, 32),
        parameters={"coverage": "z"},
        recursive=False,
    ).run()
    assert len(wcs.results) == 2
    assert parse_qs(urlsplit(wcs.results[0]["url"]).query)["coverage"] == ["z"]
    assert wcs.results[0]["name"].endswith(".tif")
    dap = mod.THREDDS(url=url, service="OPENDAP", recursive=False).run()
    assert len(dap.results) == 2
    assert dap.results[0]["data_type"] == "opendap"


def test_no_region_and_limit(_thredds):
    mod, _, _ = _thredds
    m = mod.THREDDS(
        url="https://example.org/thredds/catalog/regional/catalog.xml",
        recursive=False,
        limit=1,
    ).run()
    assert len(m.results) == 1


def test_catalog_cycle_bounded(_thredds):
    mod, _, calls = _thredds
    m = mod.THREDDS(
        url="https://example.org/thredds/catalog/regional/catalog.xml",
        recursive=True,
        max_catalogs=1,
    ).run()
    assert m._discovery_failed is True
    assert m.status == -1
