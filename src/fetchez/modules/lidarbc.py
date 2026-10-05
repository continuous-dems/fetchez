import json
import logging

from fetchez import cli, core
from fetchez.modules import FetchModule

logger = logging.getLogger(__name__)

# The permanent ArcGIS Online Item IDs for the LidarBC Indexes
AGOL_ITEM_IDS = [
    "7e31672989dc447e88e6fc6b8dde6563",  # LidarBC - Temp index (Active)
    "5f6a1f31212a4cb2826743d2e52ef02a",  # LidarBC - Open LiDAR Data Index
    "b08ecfee3a35403e893a1b43af3b469a",  # LidarBC Public Index - Dynamic (Fallback)
]
PORTAL_API = "https://www.arcgis.com/sharing/rest/content/items/{id}?f=json"


@cli.cli_opts(
    help_text="British Columbia Open LiDAR Data (LidarBC)",
    datatype="Data type to fetch: 'pointcloud', 'dem', 'dsm', or 'all' (default)",
)
class LidarBC(FetchModule):
    name = "lidarbc"
    meta_category = "Topography"
    meta_desc = "British Columbia Open LiDAR Data Index (LidarBC)"
    meta_agency = "GeoBC / Government of British Columbia"
    meta_tags = ["lidar", "dem", "dsm", "british columbia", "canada", "point cloud"]
    meta_coverage = "British Columbia, Canada"
    meta_resolution = "Various (High-density LiDAR and derived DEMs)"
    meta_license = "Open Government Licence - British Columbia (OGL-BC)"
    meta_urls = {
        "home": "https://lidar.gov.bc.ca/",
        "portal": "https://governmentofbc.maps.arcgis.com/home/item.html?id=5f6a1f31212a4cb2826743d2e52ef02a",
    }
    meta_aliases = ["geobc"]

    def __init__(self, datatype="all", **kwargs):
        super().__init__(name="lidarbc", **kwargs)
        self.datatype = datatype.lower()

    def _get_live_featureserver(self):
        """Dynamically resolve the permanent Item ID to the live FeatureServer URL."""

        for item_id in AGOL_ITEM_IDS:
            req = core.Fetch(PORTAL_API.format(id=item_id)).fetch_req(timeout=10)
            if req:
                try:
                    data = req.json()
                    url = data.get("url")
                    if url:
                        return url.split("/FeatureServer")[0] + "/FeatureServer"
                except Exception:
                    pass
        return None

    def run(self):
        if not self.wgs_region:
            return self

        w, e, s, n = self.wgs_region

        logger.info("Resolving live LidarBC FeatureServer URL from ArcGIS Portal...")
        featureserver_url = self._get_live_featureserver()

        if not featureserver_url:
            logger.error("Could not resolve LidarBC FeatureServer from ArcGIS Online.")
            return self

        logger.info(f"Connected to live service: {featureserver_url}")

        root_req = core.Fetch(featureserver_url).fetch_req(
            params={"f": "json"}, timeout=10
        )
        layers = root_req.json().get("layers", []) if root_req else []

        geom_dict = {
            "rings": [[[w, s], [w, n], [e, n], [e, s], [w, s]]],
            "spatialReference": {"wkid": 4326},
        }

        query_params = {
            "where": "1=1",
            "geometry": json.dumps(geom_dict),
            "geometryType": "esriGeometryPolygon",
            "spatialRel": "esriSpatialRelIntersects",
            "inSR": "4326",
            "outFields": "*",
            "returnGeometry": "false",
            "f": "json",
        }

        for layer in layers:
            layer_id = layer.get("id")
            layer_name = layer.get("name", f"Layer {layer_id}")

            if "boundary" in layer_name.lower():
                continue

            layer_url = f"{featureserver_url}/{layer_id}/query"
            logger.info(f"Scanning '{layer_name}' (ID: {layer_id}) for tiles...")

            req = core.Fetch(layer_url).fetch_req(params=query_params, timeout=30)
            if req is None:
                continue

            try:
                features = req.json().get("features", [])
            except Exception:
                continue

            if not features:
                continue

            logger.info(f"Found {len(features)} intersecting tiles in '{layer_name}'.")

            for feature in features:
                attrs = feature.get("attributes", {})
                urls_to_add = []

                for key, val in attrs.items():
                    if not isinstance(val, str) or not val.startswith("http"):
                        continue

                    key_lower = key.lower()
                    val_lower = val.lower()

                    is_pc = (
                        "point" in key_lower
                        or "las" in key_lower
                        or "laz" in key_lower
                        or val_lower.endswith((".las", ".laz", ".copc", ".zlas"))
                    )
                    is_dem = (
                        "dem" in key_lower
                        or "bare" in key_lower
                        or ("tif" in val_lower and "dem" in val_lower)
                    )
                    is_dsm = (
                        "dsm" in key_lower
                        or "surface" in key_lower
                        or ("tif" in val_lower and "dsm" in val_lower)
                    )

                    if (
                        self.datatype == "all"
                        or (self.datatype == "pointcloud" and is_pc)
                        or (self.datatype == "dem" and is_dem)
                        or (self.datatype == "dsm" and is_dsm)
                    ):
                        dtype_label = (
                            "pointcloud"
                            if is_pc
                            else "dem"
                            if is_dem
                            else "dsm"
                            if is_dsm
                            else "unknown"
                        )

                        tile_name = attrs.get(
                            "MapTile",
                            attrs.get("TileName", attrs.get("Name", "lidarbc_tile")),
                        )
                        actual_filename = val.split("/")[-1]
                        if "." not in actual_filename:
                            file_ext = ".laz" if is_pc else ".tif"
                            actual_filename = f"{tile_name}_{dtype_label}{file_ext}"

                        urls_to_add.append(
                            {
                                "url": val,
                                "dst_fn": actual_filename,
                                "data_type": dtype_label,
                            }
                        )

                for item in urls_to_add:
                    self.add_entry_to_results(
                        url=item["url"],
                        dst_fn=item["dst_fn"],
                        data_type=item["data_type"],
                        agency="GeoBC",
                        title=f"LidarBC {item['data_type'].upper()}",
                    )

        return self
