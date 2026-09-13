"""Read polygon footprints from remote ZIP shapefiles before downloading."""

import math
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

import requests
import shapely
from pyogrio.raw import read
from pyproj import Transformer
from shapely.ops import transform

from fetchez.core import HttpFile
from fetchez.hooks import FetchHook


class RemoteArchiveFootprintHook(FetchHook):
    """Attach WGS84 polygons and selected source attributes to each entry.

    ``layer`` is the exact path of a .shp member inside the ZIP. It may be
    omitted when there is only one shapefile. ``fields`` is a slash-separated
    list of attribute names; omit it to retain all attributes.
    """

    name = "remote_archive_footprint"
    meta_stage = "manifest"
    meta_desc = "Read footprint polygons from a remote ZIP shapefile."

    def __init__(self, layer=None, fields=None, **kwargs):
        super().__init__(**kwargs)
        self.layer = layer
        self.fields = fields.split("/") if isinstance(fields, str) else fields

    def _read_features(self, url, session):
        with TemporaryDirectory(prefix="fetchez-footprint-") as directory:
            with HttpFile(url, session=session) as remote:
                with zipfile.ZipFile(remote) as archive:
                    names = archive.namelist()
                    layers = [name for name in names if name.lower().endswith(".shp")]
                    layer = self.layer
                    if layer is None:
                        if len(layers) != 1:
                            raise ValueError(
                                f"Select a footprint layer in {url}: {layers}"
                            )
                        layer = layers[0]
                    if layer not in layers:
                        raise ValueError(f"Footprint layer not found: {layer} in {url}")
                    stem = str(PurePosixPath(layer).with_suffix(""))
                    for suffix in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
                        matches = [
                            name
                            for name in names
                            if name.lower() == (stem + suffix).lower()
                        ]
                        if not matches and suffix == ".cpg":
                            continue
                        if len(matches) != 1:
                            raise ValueError(
                                f"Missing or ambiguous {suffix}: {layer} in {url}"
                            )
                        # Never use archive member paths as local extraction paths.
                        with archive.open(matches[0]) as source:
                            with (Path(directory) / ("footprint" + suffix)).open(
                                "wb"
                            ) as target:
                                shutil.copyfileobj(source, target)
            meta, fids, geometries, columns = read(
                str(Path(directory) / "footprint.shp"),
                columns=self.fields,
                return_fids=True,
            )
        if not meta.get("crs"):
            raise ValueError(f"Footprint layer has no CRS: {layer} in {url}")
        if self.fields and set(self.fields) - set(meta["fields"]):
            raise ValueError(f"Footprint fields not found: {self.fields} in {url}")
        if geometries is None or len(geometries) == 0:
            raise ValueError(f"Footprint layer is empty: {layer} in {url}")
        project = Transformer.from_crs(meta["crs"], 4326, always_xy=True)
        features = []
        footprints = []
        for offset, wkb in enumerate(geometries):
            geometry = shapely.from_wkb(wkb)
            if (
                geometry is None
                or geometry.geom_type not in ("Polygon", "MultiPolygon")
                or geometry.is_empty
                or not geometry.is_valid
            ):
                raise ValueError(f"Invalid footprint polygon: {layer} in {url}")
            geometry = transform(project.transform, geometry)
            if not geometry.is_valid or geometry.is_empty or geometry.area <= 0:
                raise ValueError(f"Invalid projected footprint: {layer} in {url}")
            coords = shapely.get_coordinates(geometry)
            if (
                (abs(coords[:, 0]) > 180).any()
                or (abs(coords[:, 1]) > 90).any()
                or geometry.bounds[2] - geometry.bounds[0] > 180
            ):
                raise ValueError(f"Footprint crosses WGS84 limits: {layer} in {url}")
            properties = {}
            for name, column in zip(meta["fields"], columns, strict=True):
                value = column[offset]
                value = value.item() if hasattr(value, "item") else value
                if hasattr(value, "isoformat"):
                    value = value.isoformat()
                elif isinstance(value, float) and not math.isfinite(value):
                    value = None
                properties[str(name)] = value
            footprints.append(geometry)
            features.append(
                {
                    "fid": int(fids[offset]),
                    "geometry": shapely.to_wkt(geometry, rounding_precision=-1),
                    "properties": properties,
                }
            )
        return layer, shapely.union_all(footprints), features

    def run(self, entries):
        with requests.Session() as session:
            for _, entry in entries:
                layer, geometry, features = self._read_features(entry["url"], session)
                entry["geometry"] = geometry
                entry["footprint_features"] = features
                entry["footprint_layer"] = layer
        return entries
