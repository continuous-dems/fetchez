# tests/test_nasadem.py
import pytest
import requests
from fetchez.modules.nasadem import NASADEM

# we need specialized headers for this module.
from fetchez.modules.nasadem import HEADERS

# A sample region (Colorado)
# Region format: (west, east, south, north)
SAMPLE_REGION = (-105.5, -104.5, 39.5, 40.5)


@pytest.mark.skip(reason="We don't really need this tested every time.")
def test_nasadem_url_generation():
    """Verify the module generates the correct filenames/URLs
    based on the input region.
    """

    mod = NASADEM()
    mod.region = SAMPLE_REGION
    mod.run()

    # We expect NASADEM to generate tiles for this 1x1 degree area.
    # For -105.5 to -104.5 (Long) and 39.5 to 40.5 (Lat),
    # we expect tiles covering n39w106, n39w105, n40w106, n40w105
    assert len(mod.results) > 0

    first_result = mod.results[0]

    # Check that the URL looks like a NASADEM URL
    # in this case it is a .tif file, with the beinging
    # looking like: NASADEM_HGT_
    assert "opentopography.s3.sdsc.edu" in first_result["url"]
    assert first_result["data_type"] == "gtif"

    # Check filename structure (NASADEM_HGT_nXXwYYY.hgt)
    assert "NASADEM_HGT_" in first_result["dst_fn"]
    assert ".tif" in first_result["dst_fn"]


@pytest.mark.skip(reason="We don't really need this tested every time.")
def test_nasadem_server_alive():
    """Verify the generated URL actually exists on the remote server.
    This detects if the Agency/API has moved their files.
    """

    mod = NASADEM()
    mod.region = SAMPLE_REGION
    mod.run()

    # We only check the first result to be polite to the server
    if mod.results:
        target_url = mod.results[0]["url"]

        # Perform a HEAD request (checks headers without downloading the body)
        # This is fast and bandwidth-friendly.
        try:
            response = requests.head(
                target_url, timeout=5, allow_redirects=True, headers=HEADERS
            )

            # 200 = OK, 302 = Found/Redirect.
            # 403/404 means the API changed or link is dead.
            assert response.status_code in [200, 302], (
                f"Remote URL returned {response.status_code}. API endpoint might have changed: {target_url}"
            )

        except requests.exceptions.ConnectionError:
            print(f"Could not connect to {target_url}. Server might be down.")
            raise
