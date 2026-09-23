import logging
from urllib.parse import urljoin

from fetchez import core
from fetchez import fred
from fetchez.modules.base import FetchModule
from tqdm.auto import tqdm

logger = logging.getLogger(__name__)

DS781_BASE_URL = "https://pubs.usgs.gov/ds/781/"


class USGS_DS781(FetchModule):
    name = "usgs_ds781"
    meta_category = "Bathymetry"
    meta_desc = "USGS Data Series 781: California State Waters Map Series"
    meta_agency = "USGS"
    meta_resolution = "Varies"
    meta_license = "Public Domain"
    meta_tags = ["california", "bathymetry", "coastal", "usgs"]

    def __init__(self, update: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.force_update = update

        self.FRED = fred.FRED(name=self.name)

        if self.force_update or len(self.FRED.features) == 0:
            self.update_fred()

    def update_fred(self):
        logger.info("Building FRED index for USGS DS 781. This will take a moment...")

        main_page = core.Fetch(DS781_BASE_URL).fetch_html()
        if main_page is None:
            logger.error("Failed to fetch DS 781 main page.")
            return

        catalog_links = main_page.xpath('//a[contains(@href, "data_catalog")]/@href')
        catalog_links = list(set(catalog_links))  # Remove duplicates

        count = 0
        with tqdm(
            total=len(catalog_links), desc="Parsing Map Blocks", disable=self.silent
        ) as pbar:
            for link in catalog_links:
                pbar.update()

                block_url = urljoin(DS781_BASE_URL, link)
                block_page = core.Fetch(block_url).fetch_html()
                if block_page is None:
                    continue

                # Look for XML metadata links
                xml_links = block_page.xpath('//a[contains(@href, ".xml")]/@href')

                for xml_href in xml_links:
                    xml_url = urljoin(block_url, xml_href)

                    # Deduce the ZIP data link from the XML link
                    # e.g., Bathymetry_OffshorePacifica_metadata.xml -> Bathymetry_OffshorePacifica.zip
                    zip_url = xml_url.replace("_metadata.xml", ".zip").replace(
                        ".xml", ".zip"
                    )
                    if "metadata" in zip_url:
                        zip_url = zip_url.replace("metadata/", "data/")

                    dataset_name = (
                        xml_url.split("/")[-1]
                        .replace("_metadata.xml", "")
                        .replace(".xml", "")
                    )

                    # Skip if already in FRED
                    if any(
                        f["properties"].get("ID") == dataset_name
                        for f in self.FRED.features
                    ):
                        continue

                    try:
                        iso_meta = core.iso_xml(xml_url)
                        if iso_meta.xml_doc is not None:
                            geom = iso_meta.polygon(geom=True)
                            if geom:
                                self.FRED.add_survey(
                                    geom=geom,
                                    Name=dataset_name,
                                    ID=dataset_name,
                                    Agency="USGS",
                                    DataLink=zip_url,
                                    MetadataLink=xml_url,
                                    DataType="raster",
                                    DataSource=self.name,
                                    Info="USGS DS 781",
                                )
                                count += 1
                    except Exception as e:
                        logger.debug(f"Failed to parse metadata {xml_url}: {e}")

        if count > 0:
            logger.info(f"Added {count} new datasets to FRED.")
            self.FRED.save()

    def run(self):
        results = self.FRED.search(region=self.wgs_region, layer=self.name)

        if not results:
            logger.info("No matching USGS DS 781 datasets found for this region.")
            return self

        for surv in results:
            data_link = surv.get("DataLink")
            if data_link:
                self.add_entry_to_results(
                    url=data_link,
                    dst_fn=data_link.split("/")[-1],
                    data_type=surv.get("DataType", "raster"),
                    info=surv.get("Info", ""),
                )

        return self
