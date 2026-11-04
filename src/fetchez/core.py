#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.core
~~~~~~~~~~~~~

This module is the core of the Fetchez library.

It handles the initialization of fetchers, connection pooling,
threading, and the base FetchModule class.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import time
import base64
import threading
import netrc
import io
import logging
import collections
from pathlib import Path
from tqdm.auto import tqdm
import urllib.parse
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
import concurrent.futures

import requests
import lxml.etree
import lxml.html as lh
import filelock

from . import utils
from . import __version__


CUDEM_USER_AGENT = f"Fetchez/{__version__}"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:146.0) Gecko/20100101 Firefox/146.0"
)
R_HEADERS = {"User-Agent": DEFAULT_USER_AGENT}

NAMESPACES = {
    "gmd": "http://www.isotc211.org/2005/gmd",
    "gmi": "http://www.isotc211.org/2005/gmi",
    "gco": "http://www.isotc211.org/2005/gco",
    "gml": "http://www.isotc211.org/2005/gml",
    "th": "http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0",
    "wms": "http://www.opengis.net/wms",
}

logger = logging.getLogger(__name__)

HOOK_LOCK = threading.Lock()


class FetchezError(Exception):
    """Base exception for Fetchez runtime errors."""


class FetchError(FetchezError):
    """A resource could not be acquired."""


class FetchCancelled(FetchezError):
    """An acquisition or workflow was cancelled."""


class FetchLockTimeout(FetchError):
    """Timed out waiting for a download lock."""


class HookExecutionError(FetchezError):
    """A processing hook failed."""


class PipelineExecutionError(FetchezError):
    """The pipeline could not complete successfully."""


class RetryRangeReset(Exception):
    """Retry once after discarding an invalid Range request."""


class IncompleteDownloadError(Exception):
    """A remote transfer ended before the expected byte count."""


class FetchRetryExhausted(FetchError):
    def __init__(self, url, attempts, cause):
        self.url = url
        self.attempts = attempts
        self.cause = cause

        super().__init__(
            f"Failed to fetch {url} after {attempts} attempts: "
            f"{type(cause).__name__}: {cause}"
        )


# =============================================================================
# Helper Functions
# =============================================================================
def fetches_callback(r: List[Any]):
    """Default callback for fetches processes.
    r: [url, local-fn, data-type, fetch-status-or-error-code]
    """

    pass


def validate_content_range(response, expected_start):
    header = response.headers.get("Content-Range", "")

    try:
        unit, value = header.split(" ", 1)
        range_part, total_part = value.split("/", 1)
        start_str, end_str = range_part.split("-", 1)

        start = int(start_str)
        end = int(end_str)
        total = int(total_part)

    except (ValueError, AttributeError) as exc:
        raise FetchError(f"Malformed Content-Range: {header!r}") from exc

    if unit.lower() != "bytes":
        raise FetchError(f"Invalid Content-Range unit: {unit}")

    if not (0 <= start <= end < total):
        raise FetchError(f"Invalid Content-Range bounds: {header}")

    if start != expected_start:
        raise FetchError(f"Resume mismatch: expected {expected_start}, got {start}")

    return total


def mark_entry_failed(entry, exc, *, stage, hook=None):
    entry["status"] = "failed"
    entry["error_message"] = str(exc)
    entry["error"] = {
        "stage": stage,
        "type": type(exc).__name__,
        "message": str(exc),
    }

    if hook is not None:
        entry["error"]["hook"] = hook


def urlencode_(opts: Dict) -> str:
    """Encode `opts` for use in a URL."""

    return urllib.parse.urlencode(opts)


def urlencode(opts: Dict, doseq: bool = True) -> str:
    """Encode `opts` for use in a URL.

    Args:
        opts: Dictionary of query parameters.
        doseq: If True, lists in values are encoded as separate parameters
               (e.g., {'a': [1, 2]} -> 'a=1&a=2').
    """

    return urllib.parse.urlencode(opts, doseq=doseq)


def xml2py(node) -> Optional[Dict]:
    """Parse an xml file into a python dictionary."""

    texts: Dict[Any, Any] = {}
    if node is None:
        return None

    for child in list(node):
        child_key = lxml.etree.QName(child).localname
        if "name" in child.attrib:
            child_key = child.attrib["name"]

        href = child.attrib.get("{http://www.w3.org/1999/xlink}href")

        if child.text is None or child.text.strip() == "":
            if href is not None:
                if child_key in texts:
                    texts[child_key].append(href)
                else:
                    texts[child_key] = [href]
            else:
                if child_key in texts:
                    ck = xml2py(child)
                    if ck:
                        first_key = list(ck.keys())[0]
                        texts[child_key][first_key].update(ck[first_key])
                else:
                    texts[child_key] = xml2py(child)
        else:
            if child_key in texts:
                texts[child_key].append(child.text)
            else:
                texts[child_key] = [child.text]

    return texts


def get_userpass(
    authenticator_url: str,
    env_user: Optional[str] = None,
    env_pass: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Retrieve username and password from netrc for a given URL."""

    # Environmental Variables
    if env_user and env_pass:
        _user = os.environ.get(env_user)
        _pass = os.environ.get(env_pass)
        if _user and _pass:
            return _user, _pass

    # .netrc
    username = None
    password = None
    try:
        info = netrc.netrc()
        host_auth = urllib.parse.urlparse(authenticator_url).hostname
        if host_auth is not None:
            auth_results = info.authenticators(host_auth)
            if auth_results is not None:
                username, _, password = auth_results
    except Exception as exc:
        if "No such file" not in str(exc):
            logger.error(f"Failed to parse netrc: {exc}")
        username = None
        password = None

    return username, password


def get_raw_credentials(
    url: Optional[str] = None,
    authenticator_url: str = "https://urs.earthdata.nasa.gov",
    env_user: Optional[str] = None,
    env_pass: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Get raw (username, password) from .netrc or interactive prompt.
    Optionally validate against an HTTP `url`.
    """

    credentials_valid = False
    errprefix = ""

    username, password = get_userpass(
        authenticator_url, env_user=env_user, env_pass=env_pass
    )

    while not credentials_valid:
        if not username or not password:
            logger.info("\n--- Authentication Required ---")
            logger.info(f"Destination: {authenticator_url}")
            logger.info("Please enter your credentials. If you don't have an account,")
            logger.info(f"register at: {authenticator_url}\n")

            username = utils.get_username()
            password = utils.get_password()

        if not url:
            # If no validation URL is provided, trust the input and return immediately
            return username, password

        # Validate credentials against the provided test URL
        cred_str = f"{username}:{password}"
        encoded_creds = base64.b64encode(cred_str.encode("utf-8")).decode("utf-8")

        try:
            req = Request(url)
            req.add_header("Authorization", f"Basic {encoded_creds}")
            opener = build_opener(HTTPCookieProcessor())
            opener.open(req)
            credentials_valid = True
        except HTTPError:
            logger.error(f"{errprefix}Incorrect username or password")
            errprefix = ""
            # Wipe variables so the next loop forces a manual prompt
            username = None
            password = None

    return username, password


def get_credentials(
    url: Optional[str] = None,
    authenticator_url: str = "https://urs.earthdata.nasa.gov",
    env_user: Optional[str] = None,
    env_pass: Optional[str] = None,
) -> Optional[str]:
    """Wrapper for get_raw_credentials that returns a Base64 Basic Auth string."""

    username, password = get_raw_credentials(
        url, authenticator_url, env_user=env_user, env_pass=env_pass
    )

    if username and password:
        cred_str = f"{username}:{password}"
        return base64.b64encode(cred_str.encode("utf-8")).decode("utf-8")

    return None


# =============================================================================
# XML / ISO Metadata Helper
# =============================================================================
class iso_xml:
    """Helper class for parsing ISO 19115 XML Metadata."""

    def __init__(self, url=None, xml=None, timeout=20, read_timeout=60):
        self.url = url
        self.xml_doc = None
        self.namespaces = {
            "gmd": "http://www.isotc211.org/2005/gmd",
            "gco": "http://www.isotc211.org/2005/gco",
            "gml": "http://www.opengis.net/gml",
            "gml32": "http://www.opengis.net/gml/3.2",
            "xlink": "http://www.w3.org/1999/xlink",
            "gmi": "http://www.isotc211.org/2005/gmi",
        }

        if self.url is not None:
            with Fetch(self.url).fetch_req(
                timeout=timeout, read_timeout=read_timeout
            ) as req:
                # req = Fetch(self.url).fetch_req(timeout=timeout, read_timeout=read_timeout)
                if req and req.status_code == 200:
                    self._parse(req.content)
        elif xml is not None:
            self._parse(xml)

    def _parse(self, content):
        try:
            # Use recover=True to handle slight XML errors
            parser = lxml.etree.XMLParser(recover=True)
            self.xml_doc = lxml.etree.fromstring(content, parser=parser)
        except Exception as exc:
            logger.error(f"XML Parsing failed: {exc}")
            self.xml_doc = None

    def _xpath_get(self, xpath_str):
        """Helper to safely get first text result of xpath."""

        if self.xml_doc is None:
            return None
        try:
            res = self.xml_doc.xpath(xpath_str, namespaces=self.namespaces)
            if res:
                if isinstance(res[0], str):
                    return str(res[0]).strip()
                if hasattr(res[0], "text"):
                    return str(res[0].text).strip()
            return None
        except Exception:
            return None

    def title(self):
        """Extract Title."""

        return self._xpath_get(
            ".//gmd:identificationInfo//gmd:citation//gmd:title/gco:CharacterString"
        )

    def abstract(self):
        """Extract Abstract."""

        return self._xpath_get(
            ".//gmd:identificationInfo//gmd:abstract/gco:CharacterString"
        )

    def date(self):
        """Extract Date."""

        d = self._xpath_get(".//gmd:date/gco:Date")
        if not d:
            d = self._xpath_get(".//gmd:date/gco:DateTime")
        return d

    def linkages(self):
        """Extract first valid download URL (specifically looking for Zips/Data)."""

        if self.xml_doc is None:
            return None

        try:
            urls = self.xml_doc.xpath(
                ".//gmd:distributionInfo//gmd:URL/text() | .//gmd:distributionInfo//gmd:linkage/gco:CharacterString/text()",
                namespaces=self.namespaces,
            )
            for u in urls:
                u = u.strip()
                # we want zip files (actual data) over metadata links
                if ".zip" in u.lower():
                    return u

            # return first URL if no zip found
            if urls:
                return urls[0].strip()

        except Exception:
            pass
        return None

    def polygon(self, geom=True):
        """Extract Bounding Box and return GeoJSON Polygon."""

        if self.xml_doc is None:
            return None

        out_poly = []
        try:
            # Standard ISO 19115 EX_GeographicBoundingBox
            w_node = self._xpath_get(".//gmd:westBoundLongitude/gco:Decimal")
            e_node = self._xpath_get(".//gmd:eastBoundLongitude/gco:Decimal")
            s_node = self._xpath_get(".//gmd:southBoundLatitude/gco:Decimal")
            n_node = self._xpath_get(".//gmd:northBoundLatitude/gco:Decimal")

            # Legacy FGDC CSDGM Bounding Box
            fgdc_w = self._xpath_get(".//westbc")
            fgdc_e = self._xpath_get(".//eastbc")
            fgdc_s = self._xpath_get(".//southbc")
            fgdc_n = self._xpath_get(".//northbc")

            if all(v is not None for v in [w_node, e_node, s_node, n_node]):
                w, e = float(w_node), float(e_node)
                s, n = float(s_node), float(n_node)
                out_poly = [[w, s], [e, s], [e, n], [w, n], [w, s]]

            elif all(v is not None for v in [fgdc_w, fgdc_e, fgdc_s, fgdc_n]):
                w, e = float(fgdc_w), float(fgdc_e)
                s, n = float(fgdc_s), float(fgdc_n)
                out_poly = [[w, s], [e, s], [e, n], [w, n], [w, s]]

            else:
                # Fallback to GML Polygon
                bbox = self.xml_doc.find(".//{*}Polygon", namespaces=self.namespaces)
                if not bbox:
                    return None

                nodes = bbox.findall(".//{*}pos", namespaces=self.namespaces)
                for node in nodes:
                    lat_lon = [float(x) for x in node.text.split()]
                    out_poly.append([lat_lon[1], lat_lon[0]])

                ## Close polygon
                if out_poly and (
                    out_poly[0][0] != out_poly[-1][0]
                    or out_poly[0][1] != out_poly[-1][1]
                ):
                    out_poly.append(out_poly[0])

            if geom:
                try:
                    from shapely.geometry import Polygon, mapping

                    poly = Polygon(out_poly)
                    geojson_dict = mapping(poly)
                except Exception:
                    geojson_dict = {"type": "Polygon", "coordinates": [out_poly]}
                return geojson_dict
            else:
                return out_poly

        except (IndexError, ValueError) as exc:
            logger.error(f"Could not parse polygon from xml: {exc}")
            return None


# =============================================================================
# Remote Resource Helpers
# =============================================================================
# Existence checks (url_status, get_html_page): per-request timeout, and the
# waits before each retry of a transient failure.
CHECK_TIMEOUT = 30
CHECK_RETRY_WAITS = (2, 10)

# Request errors that no retry can fix.
_PERMANENT_REQUEST_ERRORS = (
    requests.TooManyRedirects,
    requests.exceptions.InvalidURL,
    requests.exceptions.InvalidSchema,
    requests.exceptions.MissingSchema,
)

_RETRYABLE_EXCEPTIONS = (requests.exceptions.RequestException,)


def _is_transient(status: int) -> bool:
    """Statuses worth retrying: timeouts, rate limits and server errors."""

    return status in (408, 429) or (500 <= status < 600 and status != 501)


def url_status(
    url: str, timeout: float = CHECK_TIMEOUT, retry_waits=CHECK_RETRY_WAITS
) -> str:
    """Check whether a remote file exists: 'exists', 'missing' or 'unknown'.

    Uses HEAD, or a one-byte ranged GET when the server refuses HEAD (405,
    501). 404/410 is 'missing'. Other client errors (400, 401, 403, ...) and
    requests that can never succeed (redirect loops, bad URLs) are logged and
    also 'missing', since no retry would change them. Timeouts, connection
    errors, 408, 429 and 5xx are retried; only if they persist is the answer
    'unknown'.
    """

    for attempt, wait in enumerate((0, *retry_waits), 1):
        if wait:
            time.sleep(wait)
        try:
            response = requests.head(url, timeout=timeout, allow_redirects=True)
            method = "HEAD"
            if response.status_code in (405, 501):
                method = "GET"
                response = requests.get(
                    url,
                    timeout=timeout,
                    allow_redirects=True,
                    headers={"Range": "bytes=0-0"},
                    stream=True,
                )
                response.close()
        except _PERMANENT_REQUEST_ERRORS as exc:
            logger.warning(
                f"{url} cannot be fetched ({type(exc).__name__}); treating it as unavailable."
            )
            return "missing"
        except requests.RequestException as exc:
            logger.debug(f"Checking {url} failed (attempt {attempt}): {exc}")
            continue

        status = response.status_code
        if 200 <= status < 400 or (method == "GET" and status == 416):
            return "exists"
        if status in (404, 410):
            return "missing"
        if _is_transient(status):
            logger.debug(f"{method} {url} returned {status} (attempt {attempt})")
            continue
        logger.warning(f"{method} {url} returned {status}; treating it as unavailable.")
        return "missing"
    return "unknown"


def get_html_page(
    url: str, timeout: float = CHECK_TIMEOUT, retry_waits=CHECK_RETRY_WAITS
):
    """Fetch an HTML page: (page, 'exists'), (None, 'missing') or (None, 'unknown').

    Classifies responses as url_status does: 404/410 and other client errors
    are 'missing' (the latter logged), transient failures are retried and are
    'unknown' only if they persist.
    """

    for attempt, wait in enumerate((0, *retry_waits), 1):
        if wait:
            time.sleep(wait)
        try:
            response = requests.get(url, timeout=timeout)
        except _PERMANENT_REQUEST_ERRORS as exc:
            logger.warning(
                f"{url} cannot be fetched ({type(exc).__name__}); treating it as unavailable."
            )
            return None, "missing"
        except requests.RequestException as exc:
            logger.debug(f"GET {url} failed (attempt {attempt}): {exc}")
            continue

        status = response.status_code
        if status == 200:
            return lh.document_fromstring(response.text), "exists"
        if status in (404, 410):
            return None, "missing"
        if _is_transient(status):
            logger.debug(f"GET {url} returned {status} (attempt {attempt})")
            continue
        logger.warning(f"GET {url} returned {status}; treating it as unavailable.")
        return None, "missing"
    return None, "unknown"


def gdal_vsi_path(url: str, *, streaming: bool = False) -> str:
    """Return a GDAL VSI path for a local or remote resource.

    HTTP/HTTPS/FTP resources are exposed through GDAL's virtual filesystem
    so GDAL-backed consumers can perform range-based random access without
    downloading the complete resource.

    Existing VSI paths and local paths are returned unchanged.
    """

    if url.startswith("/vsi"):
        return url

    parsed = urllib.parse.urlparse(url)

    if parsed.scheme in {"http", "https", "ftp"}:
        handler = "/vsicurl_streaming/" if streaming else "/vsicurl/"
        return f"{handler}{url}"

    return url


class HttpFile(io.IOBase):
    """A file-like object backed by an HTTP URL.

    Translates read() calls into HTTP Range requests to fetch only needed bytes.
    """

    def __init__(self, url, session=None, callback=None):
        self.url = url
        self.session = session or requests.Session()
        self.callback = callback
        self.offset = 0
        self.size = self._get_size()

    def _get_size(self):
        with self.session.head(
            self.url, headers={"Accept-Encoding": "identity"}, timeout=(10, 60)
        ) as resp:
            resp.raise_for_status()
            if "Content-Length" not in resp.headers:
                raise OSError("HTTP file has no Content-Length")
            return int(resp.headers["Content-Length"])

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            self.offset = offset
        elif whence == io.SEEK_CUR:
            self.offset += offset
        elif whence == io.SEEK_END:
            self.offset = self.size + offset
        return self.offset

    def tell(self):
        return self.offset

    def read(self, size=-1):
        if size == -1:
            end = self.size - 1
        else:
            end = self.offset + size - 1

        if end >= self.size:
            end = self.size - 1

        if self.offset > end:
            return b""

        # Fetch ONLY the specific bytes requested
        headers = {
            "Range": f"bytes={self.offset}-{end}",
            "Accept-Encoding": "identity",
        }
        with self.session.get(
            self.url, headers=headers, timeout=(10, 60), stream=True
        ) as response:
            response.raise_for_status()
            expected = f"bytes {self.offset}-{end}/{self.size}"
            if (
                response.status_code != 206
                or response.headers.get("Content-Range") != expected
            ):
                raise OSError("HTTP server did not honor the requested byte range")
            if (
                response.headers.get("Content-Encoding", "identity").lower()
                != "identity"
            ):
                raise OSError("HTTP server returned an encoded byte range")
            requested_size = end - self.offset + 1
            data = response.raw.read(requested_size + 1, decode_content=False)
            if len(data) != requested_size:
                raise OSError("HTTP server returned an unexpected byte-range length")

        if self.callback:
            self.callback(len(data))

        self.offset += len(data)
        return data


# =============================================================================
# Fetch
# =============================================================================
class fetchezSession(requests.Session):
    def __init__(self, rauth=None, rheaders=None, **kwargs):
        self.rauth = rauth
        self.rheaders = rheaders or {}
        super().__init__(**kwargs)

    def rebuild_auth(self, prepared_request, response):
        """Intercept the security sweep to preserve credentials."""

        super().rebuild_auth(prepared_request, response)

        if self.rauth:
            self.rauth(prepared_request)
        elif "Authorization" in self.rheaders:
            prepared_request.headers["Authorization"] = self.rheaders["Authorization"]


class Fetch:
    """Fetch ftp/http data files with an instance-owned copy of the headers."""

    def __init__(
        self,
        url: str,
        callback=fetches_callback,
        headers: Optional[Dict] = None,
        verify: bool = True,
        allow_redirects: bool = True,
        auth: Optional[Any] = None,
        cancel_event=None,
    ):
        self.url = url
        self.callback = callback
        self.headers = dict(R_HEADERS if headers is None else headers)
        self.verify = verify
        self.allow_redirects = allow_redirects
        self.auth = auth
        self.cancel_event = cancel_event
        self.silent = logger.getEffectiveLevel() > logging.INFO

        self.session = fetchezSession(rauth=self.auth, rheaders=self.headers)

    def _execute_request(
        self,
        method: str,
        timeout_tuple: tuple,
        stream: bool = True,
        **kwargs,
    ) -> requests.Response:
        """Execute one HTTP request and classify its response."""

        if self.cancel_event is not None and self.cancel_event.is_set():
            raise FetchCancelled("Fetch cancelled")

        try:
            response = self.session.request(
                method=method,
                url=self.url,
                timeout=timeout_tuple,
                verify=self.verify,
                allow_redirects=self.allow_redirects,
                auth=self.auth,
                stream=stream,
                **kwargs,
            )

        except _PERMANENT_REQUEST_ERRORS as exc:
            raise FetchError(f"Invalid request for {self.url}: {exc}") from exc

        status = response.status_code

        # Successful response, or special statuses handled by the caller.
        if 200 <= status < 300 or status in (304, 416):
            return response

        # Retryable HTTP failure.
        if _is_transient(status):
            error = requests.HTTPError(
                f"HTTP {status} requesting {self.url}",
                response=response,
            )
            response.close()
            raise error

        # Permanent HTTP failure.
        error = requests.HTTPError(
            f"HTTP {status} requesting {self.url}",
            response=response,
        )

        response.close()

        raise FetchError(f"HTTP {status} requesting {self.url}") from error

    def _with_retries(self, operation, *, tries=5, method="GET"):
        if tries < 1:
            raise ValueError("tries must be >= 1")

        attempt = 0
        range_resets = 0

        while attempt < tries:
            self._check_cancelled()
            attempt += 1

            try:
                return operation(attempt)

            except FetchCancelled:
                raise

            except FetchError:
                raise

            except RetryRangeReset as exc:
                if range_resets >= 1:
                    raise FetchError(
                        f"Repeated HTTP 416 while recovering Range for {self.url}"
                    ) from exc

                range_resets += 1
                attempt -= 1
                continue

            except (
                requests.ConnectionError,
                requests.Timeout,
                requests.exceptions.ChunkedEncodingError,
                requests.HTTPError,
                IncompleteDownloadError,
            ) as exc:
                if isinstance(exc, requests.HTTPError):
                    response = exc.response
                    if response is None or not _is_transient(response.status_code):
                        raise FetchError(
                            f"Non-retryable HTTP error for {self.url}: {exc}"
                        ) from exc

                if method.upper() not in ("GET", "HEAD"):
                    raise FetchError(
                        f"Automatic retry is not enabled for {method}"
                    ) from exc

                if attempt == tries:
                    raise FetchRetryExhausted(
                        url=self.url,
                        attempts=attempt,
                        cause=exc,
                    ) from exc

                delay = self._retry_delay(attempt, exc)

                logger.debug(
                    "Attempt %d/%d failed for %s: %s",
                    attempt,
                    tries,
                    self.url,
                    exc,
                )

                self._wait_for_retry(delay)

        raise FetchError(f"Retry loop terminated unexpectedly for {self.url}")

    def _check_cancelled(self):
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise FetchCancelled("Fetch cancelled")

    def _wait_for_retry(self, seconds):
        if self.cancel_event is not None:
            if self.cancel_event.wait(seconds):
                raise FetchCancelled("Fetch cancelled during retry wait")
        else:
            time.sleep(seconds)

    def _retry_delay(self, attempt, exc):
        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            if exc.response.status_code == 429:
                retry_after = exc.response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    return min(int(retry_after), 120)

        return min(2 * attempt, 30)

    def fetch_req(
        self,
        method="GET",
        params=None,
        data=None,
        json=None,
        tries=5,
        timeout=30,
        read_timeout=120,
    ) -> requests.Response:
        headers = self.headers.copy()
        range_reset = False

        def attempt(_number):
            nonlocal range_reset

            response = self._execute_request(
                method=method,
                timeout_tuple=(timeout, read_timeout),
                stream=True,
                headers=headers,
                params=params,
                data=data,
                json=json,
            )

            if response.status_code == 416:
                response.close()

                if "Range" in headers and not range_reset:
                    range_reset = True
                    headers.pop("Range")
                    raise RetryRangeReset()

                raise FetchError(f"HTTP 416 without recoverable Range for {self.url}")

            if response.status_code == 304:
                response.close()
                raise FetchError(f"Unexpected HTTP 304 for {self.url}")

            return response

        return self._with_retries(
            attempt,
            tries=tries,
            method=method,
        )

    def fetch_html(self, timeout=2):
        """Fetch src_url and return it as an HTML object."""

        req = self.fetch_req(timeout=timeout)

        try:
            return lh.document_fromstring(req.text)
        finally:
            req.close()

    def fetch_xml(self, timeout=2, read_timeout=10):
        response = self.fetch_req(
            timeout=timeout,
            read_timeout=read_timeout,
        )
        try:
            return lxml.etree.fromstring(response.content)
        finally:
            response.close()

    def fetch_file(
        self,
        dst_fn: str | Path,
        method: str = "GET",
        params: Optional[Dict] = None,
        overwrite: bool = False,
        timeout: int = 30,
        read_timeout: int = 120,
        tries: int = 5,
        check_size=True,
        verbose=True,
    ) -> int:
        """Fetch src_url and save to dst_fn with resume support."""

        # check if input `url` is a file path. Either check if it exists and move on or
        # copy it to the destination directory.
        if self.url and self.url.startswith("file://"):
            src_path = Path(self.url[7:])  # Strip 'file://'

            if not src_path.is_absolute():
                src_path = Path(dst_fn).resolve().parent / src_path

            # Source == Destination
            # Just index/verify the file, not move it.
            if src_path.resolve() == Path(dst_fn).resolve():
                if src_path.exists():
                    if verbose:
                        logger.debug(f"Verified local: {src_path}")
                    return 0
                else:
                    raise IOError(f"Missing local file: {src_path}")

            # Copy from Network/Local -> Output Dir
            else:
                try:
                    import shutil

                    Path(dst_fn).parent.mkdir(parents=True, exist_ok=True)
                    if not Path(src_path).resolve() == Path(dst_fn).resolve():
                        shutil.copy2(src_path, dst_fn)
                    return 0
                except shutil.SameFileError:
                    logger.debug(
                        "Source and destination share the same; skipping copy."
                    )
                    return 0
                except Exception as exc:
                    raise FetchError(f"Local copy failed: {exc}") from exc

        # Regular file fetching here-on-out
        dst_fn = Path(dst_fn)
        dst_dir = Path(dst_fn).parent.resolve()
        dst_dir.mkdir(parents=True, exist_ok=True)

        part_fn = Path(f"{dst_fn}.part")
        lock_fn = Path(f"{dst_fn}.lock")

        if not overwrite and dst_fn.exists():
            if not check_size or dst_fn.stat().st_size > 0:
                return 0  # Exists

        lock = filelock.FileLock(lock_fn, timeout=3600)
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise FetchCancelled("Fetch Cancelled.")

        def attempt(_number):
            self._check_cancelled()

            # Recalculate on EVERY attempt because the previous attempt
            # may have written additional bytes.
            resume_pos = part_fn.stat().st_size if part_fn.exists() else 0

            headers = self.headers.copy()
            headers.pop("Range", None)

            mode = "wb"

            if resume_pos > 0:
                headers["Range"] = f"bytes={resume_pos}-"
                mode = "ab"

            response = self._execute_request(
                method=method,
                timeout_tuple=(timeout, read_timeout),
                stream=True,
                headers=headers,
                params=params,
            )

            with response:
                if response.status_code == 416:
                    if resume_pos == 0:
                        raise FetchError(
                            f"HTTP 416 without a Range request for {self.url}"
                        )

                    logger.warning(
                        "Server rejected resume for %s; restarting from beginning",
                        dst_fn.name,
                    )

                    part_fn.unlink(missing_ok=True)
                    raise RetryRangeReset()

                if response.status_code == 304:
                    if dst_fn.exists() and dst_fn.stat().st_size > 0:
                        return 0
                    raise FetchError(f"HTTP 304 without a cached file: {self.url}")

                if response.status_code not in (200, 206):
                    raise FetchError(
                        f"Unexpected HTTP {response.status_code}: {self.url}"
                    )

                if resume_pos and response.status_code == 200:
                    logger.warning(
                        "Server ignored Range for %s; restarting download",
                        dst_fn.name,
                    )
                    resume_pos = 0
                    mode = "wb"

                if response.status_code == 206:
                    total_size = validate_content_range(response, resume_pos)
                else:
                    total_size = int(response.headers.get("Content-Length", 0))

                with open(part_fn, mode) as output:
                    with tqdm(
                        desc=utils.format_dataset_id(self.url),
                        total=total_size,
                        initial=resume_pos,
                        disable=not (verbose and not self.silent),
                        unit="B",
                        unit_scale=True,
                        unit_divisor=1024,
                        leave=False,
                    ) as pbar:
                        for chunk in response.iter_content(chunk_size=8192):
                            self._check_cancelled()

                            if chunk:
                                output.write(chunk)
                                pbar.update(len(chunk))

                if check_size and total_size > 0:
                    actual_size = part_fn.stat().st_size

                    if actual_size < total_size:
                        raise IncompleteDownloadError(
                            f"Incomplete download: {actual_size}/{total_size}"
                        )

                    if actual_size > total_size:
                        raise FetchError(
                            f"Download exceeds expected size: "
                            f"{actual_size}/{total_size}"
                        )

                self._check_cancelled()

                os.replace(part_fn, dst_fn)
                return 0

        try:
            with lock:
                if not overwrite and dst_fn.exists():
                    if not check_size or dst_fn.stat().st_size > 0:
                        logger.debug(
                            f"File {dst_fn.name} was downloaded by another process. Skipping."
                        )
                        return 0

                return self._with_retries(
                    attempt,
                    tries=tries,
                    method=method,
                )

        except filelock.Timeout as exc:
            raise FetchLockTimeout(
                f"Timeout waiting for lock on {dst_fn}. Another process may be hanging."
            ) from exc

        raise FetchError("Fetch failed for unknown reason.")

    def fetch_ftp_file(
        self, dst_fn: str | Path, params: Optional[Dict] = None, overwrite: bool = False
    ):
        """Fetch an ftp file via ftplib with a progress bar."""

        import ftplib

        dst_fn = Path(dst_fn)
        status = 0

        if dst_fn.exists() and not overwrite:
            return status

        logger.info(f"Fetching remote ftp file: {self.url}...")

        dest_dir = dst_fn.parent
        dest_dir.mkdir(parents=True, exist_ok=True)

        if self.cancel_event is not None and self.cancel_event.is_set():
            raise FetchCancelled("Fetch Cancelled.")

        ftp = None

        try:
            parsed = urllib.parse.urlparse(self.url)
            host = parsed.hostname
            path = parsed.path
            username = parsed.username or "anonymous"
            password = parsed.password or "anonymous@"

            ftp = ftplib.FTP(str(host))
            ftp.login(user=username, passwd=password)

            ftp.voidcmd("TYPE I")

            try:
                total_size = ftp.size(path)
            except ftplib.error_perm:
                total_size = None

            with open(dst_fn, "wb") as local_file:
                with tqdm(
                    total=total_size,
                    unit="B",
                    unit_scale=True,
                    desc=Path(dst_fn).name,
                    leave=True,
                ) as pbar:

                    def callback(data):
                        if self.cancel_event is not None and self.cancel_event.is_set():
                            logger.warning("Download cancelled.")
                            raise FetchCancelled("FTP download cancelled")

                        local_file.write(data)
                        pbar.update(len(data))

                    ftp.retrbinary(f"RETR {path}", callback)

            logger.info(f"Fetched remote ftp file: {Path(self.url).name}.")

        except FetchCancelled:
            dst_fn.unlink(missing_ok=True)
            raise

        except Exception as exc:
            dst_fn.unlink(missing_ok=True)
            raise FetchError(f"FTP Error: {exc}") from exc

        finally:
            if ftp is not None:
                try:
                    ftp.quit()
                except Exception:
                    ftp.close()

        return status


@dataclass
class FetchExecutionContext:
    cancel_event: threading.Event = field(default_factory=threading.Event)

    def cancel(self):
        self.cancel_event.set()

    @property
    def cancelled(self):
        return self.cancel_event.is_set()


@dataclass
class FetchContext:
    """Shared context for one Fetchez pipeline execution."""

    plan: Any | None = None
    execution: FetchExecutionContext = field(default_factory=FetchExecutionContext)

    @property
    def cancelled(self):
        return self.execution.cancelled

    def cancel(self):
        self.execution.cancel()


def normalize_context(context=None) -> FetchContext:
    if context is None:
        return FetchContext()

    if isinstance(context, FetchContext):
        return context

    if isinstance(context, FetchExecutionContext):
        return FetchContext(execution=context)

    raise TypeError("context must be FetchContext or FetchExecutionContext")


def bind_context(context, modules, global_hooks):
    for module in modules:
        module.context = context
        for hook in module.hooks:
            hook.context = context

    for hook in global_hooks or []:
        hook.context = context


def clear_context(modules, global_hooks):
    for module in modules:
        module.context = None
        for hook in module.hooks:
            hook.context = None

    for hook in global_hooks or []:
        hook.context = None


def _fetch_worker(module, entry, verbose=True, context=None):
    if context is not None and context.cancelled:
        raise FetchCancelled("Fetch Cancelled.")

    return module.fetch_entry(
        entry,
        check_size=True,
        verbose=verbose,
    )


def _teardown_hooks(hooks, *, ignore_failures=False, seen=None):
    """Teardown hooks once, preserving the failure policy."""
    if seen is None:
        seen = set()

    first_error = None

    for hook in hooks:
        if id(hook) in seen:
            continue
        seen.add(id(hook))

        teardown = getattr(hook, "teardown", None)
        if not callable(teardown):
            continue

        try:
            teardown()
        except Exception as exc:
            logger.exception(
                "Teardown failed for hook '%s'",
                getattr(hook, "name", type(hook).__name__),
            )
            if first_error is None:
                first_error = exc

    if first_error is not None and not ignore_failures:
        raise RuntimeError("One or more hooks failed during teardown") from first_error


def run_fetchez(
    modules: List[Any],
    threads: int = 3,
    global_hooks: Optional[List[Any]] = None,
    ignore_failures: bool = False,
    context=None,
    discover=True,
):
    """Run Fetchez in parallel with hooks.

    Args:
        modules: List of FetchModule instances.
        threads: Number of parallel download threads.
        global_hooks: List of hooks to run globally across all entries.
        ignore_failures: If False (default), raises an exception on any failure.
                         If True, tags failed entries with status='failed' and continues.
        context: The FetchContext for the plan and execution context.
        discover: Execute module.run directly, set False if already run.
    """

    context = normalize_context(context)
    seen: set[Any] = set()

    if global_hooks is None:
        global_hooks = []

    silent = logger.getEffectiveLevel() > logging.INFO
    runtime_hooks = []

    try:
        # -- Context and Discovery --
        bind_context(context, modules, global_hooks)
        for mod in modules:
            if discover:
                try:
                    if context.execution.cancelled:
                        raise FetchCancelled("Pipeline cancelled")

                    mod.run()
                except FetchCancelled:
                    raise
                except Exception as _exc:
                    mod.results = []
                    mod._discovery_failed = True
                    if not ignore_failures:
                        raise

                    logger.exception(
                        "Module '%s' failed during discovery",
                        mod.name,
                    )
                if getattr(mod, "_discovery_failed", False):
                    mod.results = []

        # --- Module Pre-Hooks ---
        for mod in modules:
            mod_pre = [h for h in mod.hooks if h.stage == "manifest"]
            if not mod_pre:
                continue

            local_entries = [(mod, e) for e in mod.results]

            try:
                for hook in mod_pre:
                    try:
                        local_entries = hook.run(local_entries)
                        if local_entries is None:
                            local_entries = []

                        utils._log_hook_history(local_entries, hook)
                    except Exception as exc:
                        err_msg = f'Module "{mod.name}" manifest-hook "{hook.name}" failed: {exc}'
                        if not ignore_failures:
                            logger.critical(f"CRITICAL: {err_msg}")
                            raise RuntimeError(err_msg) from exc
                        logger.error(
                            f"{err_msg} (Skipping due to ignore_failures=True)"
                        )
            finally:
                _teardown_hooks(
                    [*mod_pre],
                    ignore_failures=ignore_failures,
                    seen=seen,
                )
            # Update the mod.results
            mod.results = [e for m, e in local_entries]

        all_entries = []
        for mod in modules:
            for entry in mod.results:
                if not isinstance(entry, dict):
                    err_msg = (
                        f"Skipping malformed entry in module '{mod.name}': "
                        f"Expected dict, got {type(entry).__name__} -> {entry}"
                    )
                    if ignore_failures:
                        logger.warning(err_msg)
                        continue
                    else:
                        raise ValueError(err_msg)

                all_entries.append((mod, entry))

        # --- Global Pre-Hooks ---
        global_pre = [h for h in global_hooks if h.stage == "manifest"]
        try:
            for hook in global_pre:
                try:
                    result = hook.run(all_entries)
                    if isinstance(result, list):
                        all_entries = result

                    utils._log_hook_history(all_entries, hook)
                except Exception as exc:
                    err_msg = f'Global manifest-hook "{hook.name}" failed: {exc}'
                    if not ignore_failures:
                        logger.critical(f"CRITICAL: {err_msg}")
                        raise RuntimeError(err_msg) from exc
                    logger.error(f"{err_msg} (Skipping due to ignore_failures=True)")
        finally:
            _teardown_hooks(
                [*global_pre],
                ignore_failures=ignore_failures,
                seen=seen,
            )

        total_files = len(all_entries)
        if total_files == 0:
            logger.debug("No files to fetch.")
            return []

        logger.debug(
            f"Starting parallel fetch: {total_files} files with {threads} threads."
        )
        final_results_with_owner = []
        all_hooks = [
            *global_hooks,
            *(hook for module in modules for hook in module.hooks),
        ]

        pre_collection_hooks = [
            hook
            for hook in all_hooks
            if hook.stage != "collection" and hook.stage != "manifest"
        ]

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=threads)

        aborted = False

        try:
            futures = {
                executor.submit(
                    _fetch_worker,
                    mod,
                    entry,
                    verbose=True,
                    context=context,
                ): (mod, entry)
                for mod, entry in all_entries
            }

            with tqdm(
                total=total_files,
                unit="file",
                desc="Starting Pipeline...",
                position=0,
                leave=False,
                disable=silent,
            ) as pbar:
                for future in concurrent.futures.as_completed(futures):
                    if context.cancelled:
                        raise FetchCancelled("Pipeline cancelled")

                    mod, original_entry = futures[future]

                    file_name = Path(original_entry.get("dst_fn", "item")).name

                    short_name = (
                        file_name[:30] + "..." if len(file_name) > 30 else file_name
                    )

                    pbar.set_description(f"[{mod.name}] {short_name}")
                    pbar.update(1)

                    try:
                        result = future.result()

                        if result != 0:
                            raise FetchError(
                                f"Module '{mod.name}' returned unexpected fetch result "
                                f"{result!r} for '{file_name}'. Expected 0 on success; "
                                f"failures must raise an exception."
                            )

                    except FetchCancelled:
                        context.cancel()
                        raise

                    except Exception as exc:
                        err_msg = f"Failed to fetch {file_name}: {exc}"

                        if not ignore_failures:
                            logger.critical(
                                "CRITICAL: [%s] %s",
                                mod.name,
                                err_msg,
                            )
                            context.cancel()
                            # raise PipelineExecutionError(err_msg) from exc
                            raise RuntimeError(err_msg) from exc

                        logger.error("[%s] %s (Continuing...)", mod.name, err_msg)
                        mark_entry_failed(
                            original_entry,
                            exc,
                            stage="fetch",
                        )

                        final_results_with_owner.append((mod, original_entry))
                        continue

                    # --- File Hooks ---
                    gf_hooks = [h for h in global_hooks if h.stage == "file"]
                    lf_hooks = [h for h in mod.hooks if h.stage == "file"]

                    active_file_hooks = utils.merge_hooks(lf_hooks, gf_hooks)
                    current_entries = [(mod, original_entry)]

                    hook_failed = False
                    for hook in active_file_hooks:
                        if context.cancelled:
                            raise FetchCancelled("Pipeline cancelled")
                        try:
                            current_entries = hook.run(current_entries)
                            if current_entries is None:
                                current_entries = []
                            utils._log_hook_history(current_entries, hook)
                        except Exception as exc:
                            err_msg = (
                                f'File hook "{hook.name}" failed on {file_name}: {exc}'
                            )
                            if not ignore_failures:
                                logger.critical(f"CRITICAL: [{mod.name}] {err_msg}")
                                context.cancel()
                                executor.shutdown(wait=False, cancel_futures=True)
                                raise RuntimeError(err_msg) from exc

                            logger.error(f"[{mod.name}] {err_msg}")
                            original_entry["status"] = "failed"
                            original_entry["error_message"] = str(exc)
                            hook_failed = True
                            break

                    if hook_failed:
                        final_results_with_owner.append((mod, original_entry))
                        continue

                    # --- Stream Hooks ---
                    gs_hooks = [h for h in global_hooks if h.stage == "stream"]
                    ls_hooks = [h for h in mod.hooks if h.stage == "stream"]

                    active_stream_hooks = utils.merge_hooks(ls_hooks, gs_hooks)

                    stream_init_names = {"stream-init", "stream_data"}

                    # Ensure explicit stream initializers run before other stream hooks.
                    active_stream_hooks.sort(
                        key=lambda hook: hook.name not in stream_init_names
                    )

                    if active_stream_hooks:
                        has_stream = any(
                            item.get("stream") is not None
                            for _, item in current_entries
                        )

                        has_stream_init = any(
                            hook.name in stream_init_names
                            for hook in active_stream_hooks
                        )

                        if not has_stream and not has_stream_init:
                            try:
                                from fetchez.hooks.stream_init import DataStream

                                init_hook_cls = DataStream
                                logger.debug(f"Auto-initializing stream for {mod.name}")
                                init_hook = init_hook_cls()
                                init_hook.context = context
                                active_stream_hooks.insert(0, init_hook)
                                runtime_hooks.append(init_hook)

                            except Exception as exc:
                                logger.warning(
                                    f"Could not auto-initialize stream: {exc}"
                                )

                        # Run the stream transforms.
                        for hook in active_stream_hooks:
                            if context.cancelled:
                                raise FetchCancelled("Pipeline cancelled")
                            try:
                                current_entries = hook.run(current_entries)
                                if current_entries is None:
                                    current_entries = []
                                utils._log_hook_history(current_entries, hook)
                            except Exception as exc:
                                err_msg = f'Stream hook "{hook.name}" failed on {file_name}: {exc}'
                                if not ignore_failures:
                                    logger.critical(f"CRITICAL: [{mod.name}] {err_msg}")
                                    context.cancel()
                                    executor.shutdown(wait=False, cancel_futures=True)
                                    raise RuntimeError(err_msg) from exc

                                logger.error(f"[{mod.name}] {err_msg}")
                                original_entry["status"] = "failed"
                                original_entry["error_message"] = str(exc)
                                hook_failed = True
                                break

                    if hook_failed:
                        final_results_with_owner.append((mod, original_entry))
                        continue

                    # --- Stream Exhaustion ---
                    processed_entries = []
                    for owner, item in current_entries:
                        stream = item.get("stream")
                        if stream and isinstance(
                            stream,
                            (collections.abc.Iterator, collections.abc.Generator),
                        ):
                            try:
                                logger.debug(
                                    f"Exhausting stream for {Path(item.get('dst_fn', '')).name}..."
                                )
                                collections.deque(stream, maxlen=0)
                            except Exception as exc:
                                err_msg = f"Stream processing error in {Path(item.get('dst_fn', '')).name}: {exc}"
                                if not ignore_failures:
                                    logger.critical(f"CRITICAL: [{mod.name}] {err_msg}")
                                    context.cancel()
                                    executor.shutdown(wait=False, cancel_futures=True)
                                    raise RuntimeError(err_msg) from exc

                                logger.error(f"[{mod.name}] {err_msg}")
                                item["status"] = "failed"
                                item["error_message"] = str(exc)

                        processed_entries.append((owner, item))

                    final_results_with_owner.extend(processed_entries)

        except BaseException:
            aborted = True
            context.cancel()

            logger.warning("Cancelling Fetchez pipeline...")
            raise

        finally:
            try:
                _teardown_hooks(
                    [*runtime_hooks, *pre_collection_hooks],
                    ignore_failures=ignore_failures,
                    seen=seen,
                )
            finally:
                executor.shutdown(
                    wait=not aborted,
                    cancel_futures=aborted,
                )

        # --- Collection Hooks (post) ---
        # Module-level Collection-Hooks (post)
        results_by_mod: Dict[Any, Any] = {m: [] for m in modules}
        for r_tuple in final_results_with_owner:
            owner_mod, entry = r_tuple
            if owner_mod in results_by_mod:
                results_by_mod[owner_mod].append((owner_mod, entry))

        for mod in modules:
            mod_post = [h for h in mod.hooks if h.stage == "collection"]
            if mod_post and results_by_mod[mod]:
                current_mod_entries = results_by_mod[mod]
                try:
                    for hook in mod_post:
                        try:
                            current_mod_entries = hook.run(current_mod_entries)
                            if current_mod_entries is None:
                                current_mod_entries = []
                            utils._log_hook_history(current_mod_entries, hook)
                        except Exception as exc:
                            err_msg = f'Module "{mod.name}" collection-hook "{hook.name}" failed: {exc}'
                            if not ignore_failures:
                                logger.critical(f"CRITICAL: {err_msg}")
                                raise RuntimeError(err_msg) from exc
                            logger.error(f"{err_msg} (Skipping...)")
                finally:
                    _teardown_hooks(
                        [*mod_post],
                        ignore_failures=ignore_failures,
                        seen=seen,
                    )

                results_by_mod[mod] = current_mod_entries

        # Re-flatten the lists after module-level post-hooks have modified them
        flat_results = []
        for mod_entries in results_by_mod.values():
            flat_results.extend(mod_entries)

        # Global-level Post-Hooks
        global_post = [h for h in global_hooks if h.stage == "collection"]
        try:
            for hook in global_post:
                try:
                    flat_results = hook.run(flat_results)
                    if flat_results is None:
                        flat_results = []
                    utils._log_hook_history(flat_results, hook)
                except Exception as exc:
                    err_msg = f'Global collection-hook "{hook.name}" failed: {exc}'
                    if not ignore_failures:
                        logger.critical(f"CRITICAL: {err_msg}")
                        raise RuntimeError(err_msg) from exc
                    logger.error(f"{err_msg} (Skipping...)")
        finally:
            _teardown_hooks(
                [*global_post],
                ignore_failures=ignore_failures,
                seen=seen,
            )

        return flat_results

    finally:
        clear_context(modules, [*global_hooks, *runtime_hooks])
