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
import concurrent.futures

import requests
import lxml.etree
import lxml.html as lh
import filelock

from . import utils
from . import __version__

STOP_EVENT = threading.Event()

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


# =============================================================================
# Helper Functions
# =============================================================================
def fetches_callback(r: List[Any]):
    """Default callback for fetches processes.
    r: [url, local-fn, data-type, fetch-status-or-error-code]
    """

    pass


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
    except Exception as e:
        if "No such file" not in str(e):
            logger.error(f"Failed to parse netrc: {e}")
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
            req = Fetch(self.url).fetch_req(timeout=timeout, read_timeout=read_timeout)
            if req and req.status_code == 200:
                self._parse(req.content)
        elif xml is not None:
            self._parse(xml)

    def _parse(self, content):
        try:
            # Use recover=True to handle slight XML errors
            parser = lxml.etree.XMLParser(recover=True)
            self.xml_doc = lxml.etree.fromstring(content, parser=parser)
        except Exception as e:
            logger.error(f"XML Parsing failed: {e}")
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

        except (IndexError, ValueError) as e:
            logger.error(f"Could not parse polygon from xml: {e}")
            return None


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
        resp = self.session.head(self.url)
        if "Content-Length" not in resp.headers:
            return 0
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
        headers = {"Range": f"bytes={self.offset}-{end}"}
        response = self.session.get(self.url, headers=headers, timeout=(10, 60))
        response.raise_for_status()

        data = response.content

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
    """Fetch class to fetch ftp/http data files"""

    def __init__(
        self,
        url: str,
        callback=fetches_callback,
        headers: Dict = R_HEADERS,
        verify: bool = True,
        allow_redirects: bool = True,
        auth: Optional[Any] = None,
    ):
        self.url = url
        self.callback = callback
        self.headers = headers
        self.verify = verify
        self.allow_redirects = allow_redirects
        self.auth = auth
        self.silent = logger.getEffectiveLevel() > logging.INFO

        self.session = fetchezSession(rauth=self.auth, rheaders=self.headers)

    def fetch_req(
        self,
        method: str = "GET",
        params: Optional[Dict] = None,
        data: Optional[Any] = None,
        json: Optional[Dict] = None,
        tries: int = 5,
        # timeout: Optional[Union[float, Tuple]] = None,
        timeout: Optional[float] = 30,
        read_timeout: Optional[float] = 120,
    ) -> Optional[requests.Response]:
        """Fetch src_url and return the requests object (iterative retry)."""

        req = None
        current_timeout = timeout
        current_read_timeout = read_timeout

        for attempt in range(tries):
            try:
                # Calculate timeouts for this attempt
                tupled_timeout = (
                    current_timeout if current_timeout else None,
                    current_read_timeout if current_read_timeout else None,
                )

                req = self.session.request(
                    method=method,
                    url=self.url,
                    params=params,
                    data=data,
                    json=json,
                    headers=self.headers,
                    auth=self.auth,
                    timeout=tupled_timeout,
                    verify=self.verify,
                    allow_redirects=self.allow_redirects,
                    stream=True,  # Always stream to support large files
                )

                # Check status codes
                if req.status_code == 504:  # Gateway Timeout
                    time.sleep(2)
                    ## Increase timeouts next loop
                    if current_timeout:
                        current_timeout += 1
                    if current_read_timeout:
                        current_read_timeout += 10
                    continue

                elif req.status_code == 429:  # Too Many Requests
                    retry_after = req.headers.get("Retry-After")
                    wait_time = (
                        int(retry_after)
                        if retry_after and retry_after.isdigit()
                        else 30 * (attempt + 1)
                    )
                    logger.warning(
                        f"Rate limited (429) by {self.url}. Waiting {wait_time}s before retry..."
                    )
                    time.sleep(wait_time)
                    continue

                elif req.status_code == 416:  # Range Not Satisfiable
                    # If range fails, try fetching whole file
                    if "Range" in self.headers:
                        del self.headers["Range"]
                        continue

                elif 200 <= req.status_code <= 299:
                    return req

                else:
                    logger.error(f"Request from {req.url} returned {req.status_code}")
                    req.raise_for_status()
                    # return req

            except Exception as e:
                logger.debug(f"Attempt {attempt + 1}/{tries} failed: {e}")
                if current_timeout:
                    current_timeout *= 2
                if current_read_timeout:
                    current_read_timeout *= 2
                time.sleep(1)

        logger.error(f"Connection failed after {tries} attempts: {self.url}")
        raise ConnectionError("Maximum attempts at connecting have failed.")

    def fetch_html(self, timeout=2):
        """Fetch src_url and return it as an HTML object."""

        req = self.fetch_req(timeout=timeout)
        if req:
            return lh.document_fromstring(req.text)
        return None

    def fetch_xml(self, timeout=2, read_timeout=10):
        """Fetch src_url and return it as an XML object."""

        try:
            req = self.fetch_req(timeout=timeout, read_timeout=read_timeout)
            results = lxml.etree.fromstring(req.text.encode("utf-8"))
        except Exception:
            ## Fallback empty XML
            results = lxml.etree.fromstring(
                '<?xml version="1.0"?><!DOCTYPE _[<!ELEMENT _ EMPTY>]><_/>'.encode(
                    "utf-8"
                )
            )
        return results

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
            if src_path.is_absolute() == Path(dst_fn).resolve():
                if src_path.exists():
                    if verbose:
                        logger.debug(f"Verified local: {src_path}")
                    return 0
                else:
                    logger.error(f"Missing local file: {src_path}")
                    return -1

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
                except Exception as e:
                    logger.error(f"Local copy failed: {e}")
                    return -1

        # Regular file fetching here-on-out
        dst_fn = Path(dst_fn)
        dst_dir = Path(dst_fn).parent.resolve()
        dst_dir.mkdir(parents=True, exist_ok=True)

        part_fn = f"{dst_fn}.part"
        lock_fn = f"{dst_fn}.lock"

        if not overwrite and dst_fn.exists():
            if not check_size or dst_fn.stat().st_size > 0:
                return 0  # Exists

        lock = filelock.FileLock(lock_fn, timeout=3600)

        try:
            with lock:
                if not overwrite and dst_fn.exists():
                    if not check_size or dst_fn.stat().st_size > 0:
                        logger.debug(
                            f"File {dst_fn.name} was downloaded by another process. Skipping."
                        )
                        return 0

                for attempt in range(tries):
                    resume_byte_pos = 0
                    mode = "wb"

                    # Resume if partial file exists
                    if Path(part_fn).exists():
                        resume_byte_pos = Path(part_fn).stat().st_size
                        if resume_byte_pos > 0:
                            self.headers["Range"] = f"bytes={resume_byte_pos}-"
                            mode = "ab"

                    try:
                        with self.session.request(
                            method=method,
                            url=self.url,
                            stream=True,
                            params=params,
                            # data=data,
                            # json=json,
                            auth=self.auth,
                            headers=self.headers,
                            timeout=(timeout, read_timeout),
                            verify=self.verify,
                            allow_redirects=self.allow_redirects,
                        ) as req:
                            # Finished/Cached by Server (304) or Pre-check
                            if req.status_code == 304:
                                return 0

                            # Get Expected Size
                            remote_size = int(req.headers.get("content-length", 0))
                            total_size = remote_size

                            # Adjust expectation if this is a partial response
                            if req.status_code == 206:
                                content_range = req.headers.get("Content-Range", "")
                                if "/" in content_range:
                                    total_size = int(content_range.split("/")[-1])

                            # Check if already done (.part matches full size)
                            if (
                                check_size
                                and total_size > 0
                                and resume_byte_pos == total_size
                            ):
                                ## We have the whole file in .part, just move it.
                                os.rename(part_fn, dst_fn)
                                return 0

                            # Remove the Range header if the server doesn't support resume
                            if resume_byte_pos > 0 and req.status_code == 200:
                                logger.warning(
                                    f"Server ignored resume request for {dst_fn.name}. "
                                    "Restarting download from scratch."
                                )
                                mode = "wb"
                                resume_byte_pos = 0
                                if "Range" in self.headers:
                                    del self.headers["Range"]

                            # Error Codes
                            if req.status_code == 416:
                                # Range No Good: Local file is likely corrupt.
                                # Delete .part and retry from scratch (next loop iteration)
                                logger.debug(
                                    f"Invalid Range for {dst_fn.name}. Restarting..."
                                )
                                if Path(part_fn).exists():
                                    Path(part_fn).unlink()
                                if "Range" in self.headers:
                                    del self.headers["Range"]
                                continue

                            elif req.status_code in [401, 403]:
                                # Unauthorized / Forbidden
                                raise UnboundLocalError(
                                    "Authentication Failed / Forbidden"
                                )

                            elif req.status_code not in [200, 206]:
                                # Fatal error for this attempt
                                if attempt < tries - 1:
                                    time.sleep(2)
                                    continue
                                status_msg = f"Status {req.status_code}"
                                try:
                                    body = req.json()
                                    extras = ", ".join(
                                        f"{k}: {body[k]}"
                                        for k in ("error", "message")
                                        if k in body
                                    )
                                    if extras:
                                        status_msg += f" ({extras})"
                                except Exception:
                                    req.raise_for_status()
                                raise ConnectionError(status_msg)

                            with open(part_fn, mode) as f:
                                # desc = utils.str_truncate_middle(self.url, n=60)
                                desc = utils.format_dataset_id(self.url)
                                show_bar = verbose and not self.silent
                                with tqdm(
                                    desc=desc,
                                    total=total_size,
                                    initial=resume_byte_pos,
                                    disable=not show_bar,
                                    unit="B",
                                    unit_scale=True,
                                    unit_divisor=1024,
                                    leave=False,
                                ) as pbar:
                                    for chunk in req.iter_content(chunk_size=8192):
                                        if STOP_EVENT.is_set():
                                            logger.warning(
                                                "Download cancelled by user."
                                            )
                                            return -1
                                        if chunk:
                                            f.write(chunk)
                                            pbar.update(len(chunk))

                            # If we got here without exception, check size, if wanted
                            if check_size and total_size > 0:
                                final_size = Path(part_fn).stat().st_size
                                if final_size < total_size:
                                    # If smaller, the connection was most likely cut.
                                    raise IOError(
                                        f"Incomplete download: {final_size}/{total_size} bytes"
                                    )

                                elif final_size > total_size:
                                    # If larger, it was likely decompressed on the fly ? (GZIP).
                                    logger.debug(
                                        f"File size ({final_size}) > Header ({total_size}). "
                                        "Assuming transparent decompression."
                                    )
                                    # req.raise_for_status()

                                else:
                                    pass

                            os.rename(part_fn, dst_fn)
                            return 0

                    except (
                        requests.exceptions.RequestException,
                        IOError,
                        UnboundLocalError,
                    ) as e:
                        if attempt < tries - 1:
                            wait_time = (attempt + 1) * 2
                            logger.debug(
                                f"Download failed: {e}. Retrying in {wait_time}s..."
                            )
                            time.sleep(wait_time)
                        else:
                            logger.debug(f"Failed to download {self.url}: {e}")
                            return -1
                            # req.raise_for_status()

        except filelock.Timeout:
            logger.error(
                f"Timeout waiting for lock on {dst_fn}. Another process may be hanging."
            )
            return -1
        finally:
            if Path(lock_fn).exists():
                try:
                    Path(lock_fn).unlink()
                except OSError:
                    pass

        return -1

    def fetch_ftp_file(
        self, dst_fn: str | Path, params: Optional[Dict] = None, overwrite: bool = False
    ):
        """Fetch an ftp file via ftplib with a progress bar."""

        import ftplib

        dst_fn = Path(dst_fn)
        status = 0
        logger.info(f"Fetching remote ftp file: {self.url}...")

        dest_dir = dst_fn.parent
        dest_dir.mkdir(parents=True, exist_ok=True)

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
                        local_file.write(data)
                        pbar.update(len(data))

                    ftp.retrbinary(f"RETR {path}", callback)

            ftp.quit()
            logger.info(f"Fetched remote ftp file: {Path(self.url).name}.")

        except Exception as e:
            logger.error(f"FTP Error: {e}")
            status = -1

            if dst_fn.exists():
                dst_fn.unlink()

        return status


def _fetch_worker(module, entry, verbose=True):
    """Helper wrapper to call fetch_entry on a module."""

    # Let exceptions pass through
    return module.fetch_entry(entry, check_size=True, verbose=verbose)
    # try:
    #     return module.fetch_entry(entry, check_size=True, verbose=verbose)
    # except Exception as e:
    #     logger.error(f"Worker failed for {entry.get('url', 'unknown')}: {e}")
    #     return -1


# List[FetchModule]
def run_fetchez(
    modules: List[Any],
    threads: int = 3,
    global_hooks: Optional[List[Any]] = None,
    ignore_failures: bool = True,
):
    """Run Fetchez in parallel with hooks.

    Args:
        modules: List of FetchModule instances.
        threads: Number of parallel download threads.
        global_hooks: List of hooks to run globally across all entries.
        ignore_failures: If False (default), raises an exception on any failure.
                        If True, tags failed entries with status='failed' and continues.
    """

    STOP_EVENT.clear()
    if global_hooks is None:
        global_hooks = []

    silent = logger.getEffectiveLevel() > logging.INFO

    # --- Module Pre-Hooks ---
    for mod in modules:
        mod_pre = [h for h in mod.hooks if h.stage == "manifest"]
        if not mod_pre:
            continue

        local_entries = [(mod, e) for e in mod.results]

        for hook in mod_pre:
            try:
                local_entries = hook.run(local_entries)
                if local_entries is None:
                    local_entries = []

                utils._log_hook_history(local_entries, hook)
            except Exception as e:
                err_msg = f'Module "{mod.name}" manifest-hook "{hook.name}" failed: {e}'
                if not ignore_failures:
                    logger.critical(f"CRITICAL: {err_msg}")
                    raise RuntimeError(err_msg) from e
                logger.error(f"{err_msg} (Skipping due to ignore_failures=True)")

        # Update the mod.results
        mod.results = [e for m, e in local_entries]

    # all_entries = []
    # for mod in modules:
    #     for entry in mod.results:
    #         all_entries.append((mod, entry))

    all_entries = []
    for mod in modules:
        for entry in mod.results:
            if not isinstance(entry, dict):
                logger.warning(
                    f"Skipping malformed entry in module '{mod.name}': "
                    f"Expected dict, got {type(entry).__name__} -> {entry}"
                )
                continue

            all_entries.append((mod, entry))

    # --- Global Pre-Hooks ---
    global_pre = [h for h in global_hooks if h.stage == "manifest"]
    for hook in global_pre:
        try:
            result = hook.run(all_entries)
            if isinstance(result, list):
                all_entries = result

            utils._log_hook_history(all_entries, hook)
        except Exception as e:
            err_msg = f'Global manifest-hook "{hook.name}" failed: {e}'
            if not ignore_failures:
                logger.critical(f"CRITICAL: {err_msg}")
                raise RuntimeError(err_msg) from e
            logger.error(f"{err_msg} (Skipping due to ignore_failures=True)")

    total_files = len(all_entries)
    if total_files == 0:
        logger.debug("No files to fetch.")
        return

    logger.debug(
        f"Starting parallel fetch: {total_files} files with {threads} threads."
    )
    final_results_with_owner = []
    active_hooks_full = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        try:
            futures = {
                executor.submit(_fetch_worker, mod, entry, verbose=True): (mod, entry)
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
                    if STOP_EVENT.is_set():
                        raise KeyboardInterrupt("Pipeline aborted by user.")

                    mod, original_entry = futures[future]
                    file_name = Path(original_entry.get("dst_fn", "item")).name
                    short_name = (
                        file_name[:30] + "..." if len(file_name) > 30 else file_name
                    )
                    pbar.set_description(f"[{mod.name}] {short_name}")

                    try:
                        status = future.result()
                        if status != 0:
                            raise IOError(
                                f"Fetch worker returned non-zero status code: {status}"
                            )
                    except Exception as e:
                        err_msg = f"Failed to fetch {file_name}: {e}"
                        if not ignore_failures:
                            logger.critical(f"CRITICAL: [{mod.name}] {err_msg}")
                            STOP_EVENT.set()
                            executor.shutdown(wait=False, cancel_futures=True)
                            raise RuntimeError(err_msg) from e

                        logger.error(f"[{mod.name}] {err_msg} (Continuing...)")
                        original_entry["status"] = "failed"
                        original_entry["error_message"] = str(e)
                        final_results_with_owner.append((mod, original_entry))
                        pbar.update(1)
                        continue
                        # logger.error(f"Worker exception: {e}")
                        # original_entry.update({"status": -1})
                        # # continue

                    # --- File Hooks ---
                    gf_hooks = [h for h in global_hooks if h.stage == "file"]
                    lf_hooks = [h for h in mod.hooks if h.stage == "file"]

                    active_file_hooks = utils.merge_hooks(lf_hooks, gf_hooks)
                    active_hooks_full.append(active_file_hooks)

                    current_entries = [(mod, original_entry)]

                    hook_failed = False
                    for hook in active_file_hooks:
                        try:
                            current_entries = hook.run(current_entries)
                            if current_entries is None:
                                current_entries = []
                            utils._log_hook_history(current_entries, hook)
                        except Exception as e:
                            err_msg = (
                                f'File hook "{hook.name}" failed on {file_name}: {e}'
                            )
                            if not ignore_failures:
                                logger.critical(f"CRITICAL: [{mod.name}] {err_msg}")
                                STOP_EVENT.set()
                                executor.shutdown(wait=False, cancel_futures=True)
                                raise RuntimeError(err_msg) from e

                            logger.error(f"[{mod.name}] {err_msg}")
                            original_entry["status"] = "failed"
                            original_entry["error_message"] = str(e)
                            hook_failed = True
                            break

                    if hook_failed:
                        final_results_with_owner.append((mod, original_entry))
                        pbar.update(1)
                        continue

                    # --- Stream Hooks ---
                    gs_hooks = [h for h in global_hooks if h.stage == "stream"]
                    ls_hooks = [h for h in mod.hooks if h.stage == "stream"]

                    active_stream_hooks = utils.merge_hooks(ls_hooks, gs_hooks)

                    if active_stream_hooks:
                        # Check if a stream is already attached to any entry
                        has_stream = any(
                            item.get("stream") is not None
                            for _, item in current_entries
                        )

                        # Check if a stream initiator hook is already in the list
                        has_stream_init = any(
                            hook.name in ["stream-init", "stream_data"]
                            for hook in active_stream_hooks
                        )

                        # If we are about to run stream hooks, but there is no stream
                        # and no init hook scheduled, inject it dynamically right now!
                        if not has_stream and not has_stream_init:
                            try:
                                from fetchez.registry import HookRegistry

                                HookRegistry.load_builtins()

                                init_hook_cls = HookRegistry.get_class("stream-init")
                                if init_hook_cls:
                                    logger.debug(
                                        f"Auto-initializing stream for {file_name}"
                                    )
                                    # Insert it at the absolute front of the stream hooks list
                                    active_stream_hooks.insert(0, init_hook_cls())
                            except Exception as e:
                                logger.warning(f"Could not auto-initialize stream: {e}")

                        # Sort the hooks to guarantee 'stream-init' runs first
                        active_stream_hooks.sort(
                            key=lambda hook: (
                                0 if hook.name in ["stream-init", "stream_data"] else 1
                            )
                        )

                        # Run the stream transforms
                        for hook in active_stream_hooks:
                            try:
                                current_entries = hook.run(current_entries)
                                if current_entries is None:
                                    current_entries = []
                                utils._log_hook_history(current_entries, hook)
                            except Exception as e:
                                err_msg = f'Stream hook "{hook.name}" failed on {file_name}: {e}'
                                if not ignore_failures:
                                    logger.critical(f"CRITICAL: [{mod.name}] {err_msg}")
                                    STOP_EVENT.set()
                                    executor.shutdown(wait=False, cancel_futures=True)
                                    raise RuntimeError(err_msg) from e

                                logger.error(f"[{mod.name}] {err_msg}")
                                original_entry["status"] = "failed"
                                original_entry["error_message"] = str(e)
                                hook_failed = True
                                break

                    if hook_failed:
                        final_results_with_owner.append((mod, original_entry))
                        pbar.update(1)
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
                            except Exception as e:
                                err_msg = f"Stream processing error in {Path(item.get('dst_fn', '')).name}: {e}"
                                if not ignore_failures:
                                    logger.critical(f"CRITICAL: [{mod.name}] {err_msg}")
                                    STOP_EVENT.set()
                                    executor.shutdown(wait=False, cancel_futures=True)
                                    raise RuntimeError(err_msg) from e

                                logger.error(f"[{mod.name}] {err_msg}")
                                item["status"] = "failed"
                                item["error_message"] = str(e)
                                # logger.exception(
                                #     f"Stream processing error in {Path(item.get('dst_fn', '')).name}: {e}"
                                # )

                        processed_entries.append((owner, item))

                    final_results_with_owner.extend(processed_entries)
                    pbar.update(1)

        except KeyboardInterrupt:
            STOP_EVENT.set()
            logger.debug("KeyboardInterrupt initiated.")
            executor.shutdown(wait=False, cancel_futures=True)
            raise

        finally:
            # --- Teardown The Hook(s) ---
            logger.debug("Running teardown for all hooks...")

            all_possible_hooks = active_hooks_full
            for h in global_hooks:
                all_possible_hooks.append(h)
            for m in modules:
                for h in m.hooks:
                    all_possible_hooks.append(h)

            for hook in all_possible_hooks:
                if hasattr(hook, "teardown"):
                    try:
                        hook.teardown()
                    except Exception as e:
                        logger.error(f"Teardown failed for hook '{hook.name}': {e}")

    # --- Post Hooks ---
    # Module-level Post-Hooks
    results_by_mod: Dict[Any, Any] = {m: [] for m in modules}
    for r_tuple in final_results_with_owner:
        owner_mod, entry = r_tuple
        if owner_mod in results_by_mod:
            results_by_mod[owner_mod].append((owner_mod, entry))

    for mod in modules:
        mod_post = [h for h in mod.hooks if h.stage == "collection"]
        if mod_post and results_by_mod[mod]:
            current_mod_entries = results_by_mod[mod]
            for hook in mod_post:
                try:
                    current_mod_entries = hook.run(current_mod_entries)
                    if current_mod_entries is None:
                        current_mod_entries = []
                    utils._log_hook_history(current_mod_entries, hook)
                except Exception as e:
                    err_msg = (
                        f'Module "{mod.name}" collection-hook "{hook.name}" failed: {e}'
                    )
                    if not ignore_failures:
                        logger.critical(f"CRITICAL: {err_msg}")
                        raise RuntimeError(err_msg) from e
                    logger.error(f"{err_msg} (Skipping...)")

            results_by_mod[mod] = current_mod_entries

    # Re-flatten the lists after module-level post-hooks have modified them
    flat_results = []
    for mod_entries in results_by_mod.values():
        flat_results.extend(mod_entries)

    # Global-level Post-Hooks
    global_post = [h for h in global_hooks if h.stage == "collection"]
    for hook in global_post:
        try:
            flat_results = hook.run(flat_results)
            if flat_results is None:
                flat_results = []
            utils._log_hook_history(flat_results, hook)
        except Exception as e:
            err_msg = f'Global collection-hook "{hook.name}" failed: {e}'
            if not ignore_failures:
                logger.critical(f"CRITICAL: {err_msg}")
                raise RuntimeError(err_msg) from e
            logger.error(f"{err_msg} (Skipping...)")

    return flat_results
