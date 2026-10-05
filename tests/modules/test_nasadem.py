# tests/modules/test_nasadem.py
import logging

import pytest
import requests

from fetchez.modules.nasadem import HEADERS, NASADEM

logger = logging.getLogger(__name__)

# A sample region (Colorado)
SAMPLE_REGION = (-105.5, -104.5, 39.5, 40.5)


# @pytest.mark.health
@pytest.mark.skip(reason="We don't really need this tested every time.")
def test_nasadem_url_generation():
    """Verify the module generates the correct filenames/URLs based on region."""

    mod = NASADEM(src_region=SAMPLE_REGION)
    mod.run()

    assert len(mod.results) > 0

    first_result = mod.results[0]

    assert "opentopography.s3.sdsc.edu" in first_result["url"]
    assert first_result["data_type"] == "gtif"
    assert "NASADEM_HGT_" in first_result["dst_fn"]
    assert ".tif" in first_result["dst_fn"]


# @pytest.mark.health
@pytest.mark.skip(reason="We don't really need this tested every time.")
def test_nasadem_server_alive():
    """Verify the generated URL actually exists on the remote server."""

    mod = NASADEM(src_region=SAMPLE_REGION)
    mod.run()

    if mod.results:
        target_url = mod.results[0]["url"]

        # Merge the NASADEM headers with a 0-0 range request, so we don't bug them.
        test_headers = HEADERS.copy()
        test_headers["Range"] = "bytes=0-0"

        try:
            response = requests.get(
                target_url,
                timeout=10,
                allow_redirects=True,
                headers=test_headers,
                stream=True,
            )

            # 206 = Partial Content (Range request succeeded, file exists!)
            # 200 = OK (Server ignored Range and sent the file, but it exists!)
            assert response.status_code in [200, 206], (
                f"Remote URL returned {response.status_code}. API endpoint might have changed: {target_url}"
            )

        except requests.exceptions.ConnectionError:
            pytest.fail(f"Could not connect to {target_url}. Server might be down.")
