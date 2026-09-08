#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.modules.vdatum
~~~~~~~~~~~~~~~~~~~~~~

Fetch NOAA VDatum grids, including regional tidal/orthometric packages and
multi-grid geopotential models such as xGEOID.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import re
import logging
import requests
import zipfile

from pathlib import Path
from typing import Any, Optional

from fetchez import cli
from fetchez import core
from fetchez import fred
from fetchez import utils
from fetchez.modules import FetchModule

logger = logging.getLogger(__name__)


VDATUM_DATA_URL = "https://vdatum.noaa.gov/download/data/"


KNOWN_DATUMS = {
    # Tidal datums
    "mhw",
    "mhhw",
    "mlw",
    "mllw",
    "mtl",
    "dtl",
    "msl",
    "tss",
    # Experimental / modern geopotential models
    "xgeoid16b",
    "xgeoid17b",
    "xgeoid18b",
    "xgeoid19b",
    "xgeoid20b",
    # Orthometric / legacy products
    "vertcon",
    "igld85",
    "navd88",
    "ngvd29",
}

STANDALONE_MODELS = {
    "xgeoid16b",
    "xgeoid17b",
    "xgeoid18b",
    "xgeoid19b",
    "xgeoid20b",
    "vertcon",
    "igld85",
    "navd88",
    "ngvd29",
}


@cli.cli_opts(
    help_text="NOAA VDatum Transformation Grids",
    datatype='Filter by datum/model type (e.g. "mllw", "tss", "xgeoid20b").',
    update="Force a re-scrape of the NOAA website.",
)
class VDatum(FetchModule):
    name = "vdatum"
    meta_category = "Geodesy"
    meta_desc = "NOAA VDatum Grids (Tidal & Geopotential)"
    meta_agency = "NOAA"
    meta_tags = [
        "vdatum",
        "tidal",
        "geopotential",
        "mllw",
        "xgeoid",
        "noaa",
        "vertical-datum",
        "transformation",
    ]
    meta_region = "USA / Coastal"
    meta_resolution = "Varies (Regional Grids)"
    meta_license = "Public Domain"
    meta_urls = {"home": "https://vdatum.noaa.gov/"}
    meta_aliases = ["tidal_grids", "xgeoid"]

    def __init__(
        self,
        datatype: Optional[str] = None,
        coverage: Optional[str] = None,
        update: bool = False,
        **kwargs: Any,
    ):
        super().__init__(name="vdatum", **kwargs)

        self.datatype = datatype.casefold() if datatype else None
        self.coverage = coverage.casefold() if coverage else None
        self.force_update = update

        self.fred = fred.FRED("vdatum", local=False)

    @staticmethod
    def _parse_key_values(text: str) -> dict[str, str]:
        """Parse simple ``key=value`` VDatum metadata."""

        values: dict[str, str] = {}

        for line in text.splitlines():
            line = line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()

        return values

    @staticmethod
    def _bbox_from_values(
        values: dict[str, str],
        prefix: Optional[str] = None,
    ) -> Optional[tuple[float, float, float, float]]:
        """Extract a geographic bbox from parsed VDatum metadata."""

        def get_value(name: str) -> Optional[str]:
            if prefix is None:
                # Regional .met files commonly use keys such as
                # ``tidal.minlat`` / ``tidal.maxlat``.
                for key, value in values.items():
                    if key.casefold().split(".")[-1] == name:
                        return value
                return None

            wanted = f"{prefix}.{name}".casefold()

            for key, value in values.items():
                if key.casefold() == wanted:
                    return value

            return None

        try:
            minlon = get_value("minlon")
            maxlon = get_value("maxlon")
            minlat = get_value("minlat")
            maxlat = get_value("maxlat")

            if None in (minlon, maxlon, minlat, maxlat):
                return None

            return (
                utils.x360(float(minlon)),
                utils.x360(float(maxlon)),
                float(minlat),
                float(maxlat),
            )

        except (TypeError, ValueError):
            return None

    @staticmethod
    def _bbox_geometry(
        bbox: tuple[float, float, float, float],
    ) -> dict[str, Any]:
        """Build a polygon geometry from a bbox."""

        min_x, max_x, min_y, max_y = bbox

        return {
            "type": "Polygon",
            "coordinates": [
                [
                    [min_x, min_y],
                    [max_x, min_y],
                    [max_x, max_y],
                    [min_x, max_y],
                    [min_x, min_y],
                ]
            ],
        }

    @staticmethod
    def _find_metadata_members(
        namelist: list[str],
    ) -> list[str]:
        """Return likely VDatum metadata members from an archive."""

        return sorted(
            member
            for member in namelist
            if member.casefold().endswith((".met", ".inf"))
        )

    @staticmethod
    def _find_multigrid_inf(
        archive: zipfile.ZipFile,
        namelist: list[str],
    ) -> Optional[tuple[str, dict[str, str]]]:
        """Find an INF describing a multi-grid model package.

        xGEOID packages contain an INF with a ``grids=`` declaration and
        per-grid records such as::

            grids=AS;CONUSPAC;GU;vCONUSPAC
            CONUSPAC.minlat=...
            CONUSPAC.maxlat=...
            CONUSPAC.source=core\\xgeoid20b\\CONUSPAC.gtx

        Those component grids belong to one model and should be indexed
        spatially under that model's datatype.
        """

        for member in VDatum._find_metadata_members(namelist):
            if not member.casefold().endswith(".inf"):
                continue

            try:
                text = archive.read(member).decode(
                    "utf-8",
                    errors="ignore",
                )
            except Exception:
                continue

            values = VDatum._parse_key_values(text)

            if values.get("grids"):
                return member, values

        return None

    @staticmethod
    def _component_names(
        values: dict[str, str],
    ) -> list[str]:
        """Return grid component names from a multi-grid INF."""

        grids_value = values.get("grids", "")

        return [value.strip() for value in grids_value.split(";") if value.strip()]

    @staticmethod
    def _component_value(
        values: dict[str, str],
        component: str,
        key: str,
    ) -> Optional[str]:
        """Return a component-specific INF value case-insensitively."""

        wanted = f"{component}.{key}".casefold()

        for name, value in values.items():
            if name.casefold() == wanted:
                return value

        return None

    @staticmethod
    def _component_resolution(
        values: dict[str, str],
        component: str,
    ) -> Optional[float]:
        """Return a representative grid spacing for component ranking."""

        candidates = []

        for key in (
            "spacing",
            "spacing_lat",
            "spacing_lon",
            "lat_spacing",
            "lon_spacing",
            "dlat",
            "dlon",
        ):
            value = VDatum._component_value(
                values,
                component,
                key,
            )

            if value is None:
                continue

            try:
                candidates.append(abs(float(value)))
            except ValueError:
                continue

        if not candidates:
            return None

        return max(candidates)

    @staticmethod
    def _archive_member_for_component(
        namelist: list[str],
        values: dict[str, str],
        component: str,
    ) -> Optional[str]:
        """Resolve the GTX archive member belonging to one INF component."""

        source = VDatum._component_value(
            values,
            component,
            "source",
        )

        if source:
            normalized_source = source.replace("\\", "/").casefold()

            # INF paths are sometimes relative to an internal VDatum root rather
            # than the root of the ZIP. Match by normalized suffix.
            for member in namelist:
                normalized_member = member.replace("\\", "/").casefold()

                if normalized_member.endswith(normalized_source):
                    return member

        component_name = f"{component}.gtx".casefold()

        for member in namelist:
            if Path(member).name.casefold() == component_name:
                return member

        return None

    def _index_multigrid_package(
        self,
        archive: zipfile.ZipFile,
        namelist: list[str],
        zip_name: str,
        zip_url: str,
        metadata_member: str,
        values: dict[str, str],
        model_name: str,
    ) -> bool:
        """Index a multi-grid VDatum model such as xGEOID20B."""

        # model_name = Path(zip_name).stem.casefold()
        components = self._component_names(values)

        if not components:
            return False

        logger.debug(
            "Indexing multi-grid VDatum model %s from %s",
            model_name,
            metadata_member,
        )

        indexed = 0

        for component in components:
            bbox = self._bbox_from_values(
                values,
                prefix=component,
            )

            if bbox is None:
                logger.debug(
                    "No valid bbox for %s component %s",
                    model_name,
                    component,
                )
                continue

            archive_member = self._archive_member_for_component(
                namelist,
                values,
                component,
            )

            if archive_member is None:
                logger.warning(
                    "Could not locate GTX member for %s component %s",
                    model_name,
                    component,
                )
                continue

            resolution = self._component_resolution(
                values,
                component,
            )

            self.fred.add_survey(
                self._bbox_geometry(bbox),
                Name=f"VDatum_{model_name.upper()}",
                ID=f"{model_name}:{component.casefold()}",
                Agency="NOAA",
                DataLink=zip_url,
                DataType=model_name,
                Coverage=component.casefold(),
                ArchiveMember=archive_member,
                Resolution=resolution,
                MultiGrid=True,
                DataSource="vdatum",
            )
            indexed += 1

        logger.debug(
            "Indexed %d component grids for %s",
            indexed,
            model_name,
        )

        return indexed > 0

    @staticmethod
    def _contained_regional_datums(
        namelist: list[str],
    ) -> set[str]:
        datums: set[str] = set()

        for member in namelist:
            if not member.casefold().endswith(".gtx"):
                continue

            stem = Path(member).stem.casefold()
            parts = stem.split("_")

            # Ignore uncertainty suffix.
            if parts and parts[-1] == "unc":
                parts.pop()

            if not parts:
                continue

            datum = parts[-1]

            if datum in KNOWN_DATUMS:
                datums.add(datum)

        return datums

    @staticmethod
    def _regional_grid_members(
        namelist: list[str],
    ) -> dict[str, str]:
        members: dict[str, str] = {}

        for member in namelist:
            if not member.casefold().endswith(".gtx"):
                continue

            stem = Path(member).stem.casefold()
            parts = stem.split("_")

            # Uncertainty grids are separate products; don't use them as
            # transformation surfaces.
            if parts and parts[-1] == "unc":
                continue

            if not parts:
                continue

            datum = parts[-1]

            if datum in KNOWN_DATUMS:
                members[datum] = member

        return members

    def _regional_bbox(
        self,
        archive: zipfile.ZipFile,
        namelist: list[str],
    ) -> Optional[tuple[float, float, float, float]]:
        """Find the bbox for a conventional regional VDatum package."""

        # Prefer .met because it describes the downloaded coverage itself.
        metadata_members = self._find_metadata_members(namelist)

        metadata_members.sort(
            key=lambda member: (
                not member.casefold().endswith(".met"),
                member.casefold(),
            )
        )

        for member in metadata_members:
            try:
                text = archive.read(member).decode(
                    "utf-8",
                    errors="ignore",
                )
            except Exception:
                continue

            values = self._parse_key_values(text)
            bbox = self._bbox_from_values(values)

            if bbox is not None:
                return bbox

        return None

    def _index_regional_package(
        self,
        archive: zipfile.ZipFile,
        namelist: list[str],
        zip_name: str,
        zip_url: str,
    ) -> bool:
        grid_members = self._regional_grid_members(namelist)

        if not grid_members:
            return False

        bbox = self._regional_bbox(
            archive,
            namelist,
        )

        if bbox is None:
            logger.debug(
                "No valid bbox found for regional package %s",
                zip_name,
            )
            return False

        coverage_id = Path(zip_name).stem

        for datum, archive_member in sorted(grid_members.items()):
            self.fred.add_survey(
                self._bbox_geometry(bbox),
                Name=f"VDatum_{datum.upper()}",
                ID=coverage_id,
                Agency="NOAA",
                DataLink=zip_url,
                DataType=datum,
                Coverage=coverage_id.casefold(),
                ArchiveMember=archive_member,
                MultiGrid=False,
                DataSource="vdatum",
            )

        return True

    @staticmethod
    def _package_version_key(zip_name: str) -> tuple[str, tuple[int, ...], str]:
        """Return a stable key for grouping/versioning VDatum packages.

        This helper deliberately does not discard older packages. It only parses
        trailing numeric version fields so they remain available for callers that
        need deterministic ordering.
        """

        stem = Path(zip_name).stem.casefold()
        match = re.match(r"^(.*?)(?:_([0-9]+(?:_[0-9]+)*))?$", stem)

        if not match:
            return stem, (), stem

        base = match.group(1)
        version_text = match.group(2)

        version = (
            tuple(int(value) for value in version_text.split("_"))
            if version_text
            else ()
        )

        return base, version, stem

    @staticmethod
    def _standalone_model_name(zip_name: str) -> Optional[str]:
        stem = Path(zip_name).stem.casefold()

        if stem.startswith("vdatum_"):
            stem = stem[len("vdatum_") :]

        if stem in STANDALONE_MODELS:
            return stem

        return None

    def _scrape_and_index(self) -> None:
        """Scrape NOAA VDatum packages and build the spatial FRED index."""

        logger.info("Scraping VDatum directory for grid packages...")

        response = requests.get(
            VDATUM_DATA_URL,
            timeout=60,
        )
        response.raise_for_status()

        zip_links = sorted(
            set(
                re.findall(
                    r'href="([^"]+\.zip)"',
                    response.text,
                    flags=re.IGNORECASE,
                )
            )
        )

        logger.info(
            "Found %d VDatum zip packages...",
            len(zip_links),
        )

        indexed_packages = 0

        for zip_name in zip_links:
            stem = Path(zip_name).stem.casefold()

            # Skip massive all-in-one bundles and software distributions.
            if (
                stem.startswith("vdatum_all")
                or stem.startswith("vdatum_v")
                or stem.startswith("vdatum_regional")
            ):
                continue

            zip_url = VDATUM_DATA_URL + zip_name

            logger.info(
                "Inspecting metadata for: %s",
                zip_name,
            )

            status = core.Fetch(zip_url).fetch_file(zip_name)

            if status != 0:
                logger.warning(
                    "Failed to download %s",
                    zip_name,
                )
                continue

            try:
                with zipfile.ZipFile(zip_name, "r") as archive:
                    namelist = archive.namelist()

                    model_name = self._standalone_model_name(zip_name)

                    if model_name is not None:
                        multigrid = self._find_multigrid_inf(
                            archive,
                            namelist,
                        )

                        if multigrid is None:
                            logger.warning(
                                "Standalone VDatum model %s has no multi-grid INF.",
                                zip_name,
                            )
                            continue

                        metadata_member, values = multigrid

                        indexed = self._index_multigrid_package(
                            archive,
                            namelist,
                            zip_name,
                            zip_url,
                            metadata_member,
                            values,
                            model_name=model_name,
                        )

                    else:
                        indexed = self._index_regional_package(
                            archive,
                            namelist,
                            zip_name,
                            zip_url,
                        )
                    if indexed:
                        indexed_packages += 1

            except zipfile.BadZipFile:
                logger.warning(
                    "Corrupted zip file downloaded: %s",
                    zip_name,
                )

            except Exception as exc:
                logger.warning(
                    "Failed to parse %s: %s",
                    zip_name,
                    exc,
                )

        self.fred.save()

        logger.info(
            "Successfully indexed %d VDatum packages.",
            indexed_packages,
        )

    @staticmethod
    def _result_resolution(result: dict[str, Any]) -> float:
        """Return sortable spatial resolution for an indexed component."""

        value = result.get("Resolution")

        if value is None:
            return float("inf")

        try:
            return abs(float(value))
        except (TypeError, ValueError):
            return float("inf")

    @staticmethod
    def _result_area(result: dict[str, Any]) -> float:
        """Return approximate indexed footprint area when available."""

        geom = result.get("geometry") or result.get("geom")

        if not isinstance(geom, dict):
            return float("inf")

        try:
            coordinates = geom["coordinates"][0]

            xs = [point[0] for point in coordinates]
            ys = [point[1] for point in coordinates]

            return (max(xs) - min(xs)) * (max(ys) - min(ys))

        except Exception:
            return float("inf")

    def _select_multigrid_results(
        self,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        passthrough: list[dict[str, Any]] = []

        for result in results:
            if not result.get("MultiGrid", False):
                passthrough.append(result)
                continue

            datatype = str(result.get("DataType", "")).casefold()

            grouped.setdefault(
                datatype,
                [],
            ).append(result)

        selected = passthrough.copy()

        for _datatype, candidates in grouped.items():
            candidates.sort(
                key=lambda result: (
                    self._result_resolution(result),
                    self._result_area(result),
                    str(result.get("Coverage", "")).casefold(),
                )
            )

            if candidates:
                selected.append(candidates[0])

        return selected

    def run(self):
        if self.force_update or not self.fred.features:
            self._scrape_and_index()

        if not self.fred.features:
            logger.error("VDatum index is empty. Scrape failed.")
            return self

        matches = self.fred.search(
            region=self.wgs_region,
        )

        filtered: list[dict[str, Any]] = []

        for result in matches:
            result_datatype = str(result.get("DataType", "")).casefold()

            result_coverage = str(
                result.get("Coverage", result.get("ID", ""))
            ).casefold()

            if self.datatype and self.datatype != result_datatype:
                continue

            if self.coverage and self.coverage not in result_coverage:
                continue

            filtered.append(result)

        # xGEOID-style packages can have multiple components intersecting the
        # same requested region. Select the finest matching component
        # automatically so callers only need ``datatype=xgeoid20b``.
        filtered = self._select_multigrid_results(
            filtered,
        )

        for result in filtered:
            metadata = {
                "coverage": result.get("Coverage"),
                "archive_member": result.get("ArchiveMember"),
                "resolution": result.get("Resolution"),
            }

            metadata = {
                key: value for key, value in metadata.items() if value is not None
            }

            self.add_entry_to_results(
                url=result["DataLink"],
                dst_fn=os.path.basename(result["DataLink"]),
                data_type=result["DataType"],
                agency="NOAA",
                title=f"VDatum Grid ({result['ID']})",
                metadata=metadata,
                coverage=result.get("Coverage"),
                archive_member=result.get("ArchiveMember"),
            )

        return self
