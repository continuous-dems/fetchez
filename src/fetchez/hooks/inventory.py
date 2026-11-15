#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Write manifest inventories as JSON, CSV, GeoJSON, or GeoPackage."""

import csv
import json
import logging
from pathlib import Path

from fetchez.hooks import FetchHook
from fetchez.spatial import entry_geometry
from fetchez.entry import json_safe

logger = logging.getLogger(__name__)


class Inventory(FetchHook):
    name = "inventory"
    meta_desc = "Write discovered entry metadata to JSON, CSV, GeoJSON, or GeoPackage."
    meta_stage = "finalize"
    meta_stages = ("manifest", "finalize")
    meta_category = "metadata"
    meta_effects = ["consumes-entries", "creates-artifact"]

    def __init__(
        self,
        output="inventory.json",
        out_format=None,
        layer="footprints",
        geometry_required=False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.output = Path(output)
        self.out_format = (
            out_format or self.output.suffix.lstrip(".") or "json"
        ).lower()
        self.layer = layer
        self.geometry_required = geometry_required
        if self.out_format not in {"json", "csv", "geojson", "gpkg"}:
            raise ValueError(f"Unsupported inventory format: {self.out_format}")

    def run(self, entries):
        entries = entries if entries is not None else []
        self.output.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        geometries = []

        for mod, entry in entries:
            geometry = (
                entry_geometry(entry)
                if self.out_format in {"gpkg", "geojson"}
                else None
            )
            if self.geometry_required and geometry is None:
                continue

            record = {key: value for key, value in entry.items() if key != "stream"}

            record.update(
                {
                    "module": getattr(mod, "name", type(mod).__name__),
                    "instance_id": getattr(mod, "instance_id", None),
                    "filename": entry.get("dst_fn"),
                    "url": entry.get("url"),
                    "data_type": entry.get("data_type"),
                    "date": entry.get("date", ""),
                    "geometry_type": geometry.geom_type
                    if geometry is not None
                    else None,
                    "geometry_kind": entry.get("geometry_kind"),
                    "geometry_source": entry.get("geometry_source"),
                    "geometry_crs": "EPSG:4326" if geometry is not None else None,
                }
            )
            ready = json_safe(record)
            if self.out_format in {"gpkg", "geojson"}:
                # Make vector attributes predictable; preserve the complete metadata
                # in one JSON column/property rather than a schema per provider.
                rows.append(
                    {
                        "module": str(record["module"]),
                        "instance_id": _string_or_none(record["instance_id"]),
                        "filename": _string_or_none(record["filename"]),
                        "url": _string_or_none(record["url"]),
                        "data_type": _string_or_none(record["data_type"]),
                        "date": _string_or_none(record["date"]),
                        "geometry_type": _string_or_none(record["geometry_type"]),
                        "geometry_kind": _string_or_none(record["geometry_kind"]),
                        "geometry_source": _string_or_none(record["geometry_source"]),
                        "geometry_crs": _string_or_none(record["geometry_crs"]),
                        "metadata_json": json.dumps(
                            {
                                key: value
                                for key, value in ready.items()
                                if key != "geometry"
                            },
                            ensure_ascii=False,
                            allow_nan=False,
                        ),
                    }
                )
                geometries.append(geometry)
            else:
                rows.append(ready)

        if self.out_format == "json":
            self.output.write_text(
                json.dumps(rows, indent=2, ensure_ascii=False, allow_nan=False),
                encoding="utf-8",
            )
        elif self.out_format == "csv":
            fields = sorted({key for row in rows for key in row})
            with self.output.open("w", newline="", encoding="utf-8") as dest:
                writer = csv.DictWriter(dest, fieldnames=fields)
                writer.writeheader()
                writer.writerows(
                    {key: _csv_value(value) for key, value in row.items()}
                    for row in rows
                )
        elif self.out_format == "geojson":
            from shapely.geometry import mapping

            features = []
            for properties, geometry in zip(rows, geometries, strict=True):
                features.append(
                    {
                        "type": "Feature",
                        "geometry": mapping(geometry) if geometry is not None else None,
                        "properties": properties,
                    }
                )
            self.output.write_text(
                json.dumps(
                    {"type": "FeatureCollection", "features": features},
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        else:
            try:
                import geopandas as gpd
            except ImportError as exc:
                raise ImportError(
                    "GeoPackage inventory requires geopandas and pyogrio (fetchez[raster] or your geospatial extras)"
                ) from exc
            import pandas as pd

            columns = (
                "module",
                "instance_id",
                "filename",
                "url",
                "data_type",
                "date",
                "geometry_type",
                "geometry_kind",
                "geometry_source",
                "geometry_crs",
                "metadata_json",
            )
            table = pd.DataFrame(rows, columns=columns)
            frame = gpd.GeoDataFrame(
                table,
                geometry=gpd.GeoSeries(geometries, crs="EPSG:4326"),
                crs="EPSG:4326",
            )
            # Replace the entire GPKG so old layers cannot survive an overwrite.
            if self.output.exists():
                self.output.unlink()
            frame.to_file(
                self.output, layer=self.layer, driver="GPKG", engine="pyogrio"
            )

        logger.info(
            "Entry inventory written to %s (%d entries, %d geometries)",
            self.output,
            len(rows),
            sum(g is not None for g in geometries),
        )
        return entries


def _string_or_none(value):
    return None if value is None else str(value)


def _csv_value(value):
    return (
        json.dumps(value, ensure_ascii=False)
        if isinstance(value, (dict, list))
        else value
    )
