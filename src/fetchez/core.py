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
import queue
import netrc
import io
import logging
import collections
from tqdm import tqdm
import urllib.parse
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor
from typing import List, Dict, Optional, Any, Tuple
import concurrent.futures

import requests
import lxml.etree
import lxml.html as lh

try:
    from shapely.geometry import Polygon, mapping

    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

from . import utils
from . import spatial
from . import __version__

STOP_EVENT = threading.Event()

CUDEM_USER_AGENT = f"Fetches/{__version__}"
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


def get_userpass(authenticator_url: str) -> Tuple[Optional[str], Optional[str]]:
    """Retrieve username and password from netrc for a given URL."""

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


def get_credentials(
    url: str, authenticator_url: str = "https://urs.earthdata.nasa.gov"
) -> Optional[str]:
    """Get user credentials from .netrc or prompt for input.
    Used for EarthData, etc.
    """

    credentials = None
    errprefix = ""

    username, password = get_userpass(authenticator_url)

    while not credentials:
        if not username:
            username = utils.get_username()
            password = utils.get_password()

        cred_str = f"{username}:{password}"
        credentials = base64.b64encode(cred_str.encode("ascii")).decode("ascii")

        if url:
            try:
                req = Request(url)
                req.add_header("Authorization", f"Basic {credentials}")
                opener = build_opener(HTTPCookieProcessor())
                opener.open(req)
            except HTTPError:
                print(f"{errprefix}Incorrect username or password")
                errprefix = ""
                credentials = None
                username = None
                password = None

    return credentials


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
            # Find Bounding Box
            # bbox = self.xml_doc.xpath('.//gmd:EX_GeographicBoundingBox', namespaces=self.namespaces)
            bbox = self.xml_doc.find(".//{*}Polygon", namespaces=self.namespaces)
            if not bbox:
                return None

            nodes = bbox.findall(".//{*}pos", namespaces=self.namespaces)
            for node in nodes:
                out_poly.append([float(x) for x in node.text.split()])

            ## Close polygon
            if out_poly and (
                out_poly[0][0] != out_poly[-1][0] or out_poly[0][1] != out_poly[-1][1]
            ):
                out_poly.append(out_poly[0])

            out_poly = [[lon, lat] for lat, lon in out_poly]
            if geom:
                if HAS_SHAPELY:
                    poly = Polygon(out_poly)
                    geojson_dict = mapping(poly)
                else:
                    geojson_dict = {"type": "Polygon", "coordinates": [out_poly]}

                return geojson_dict

            else:
                return out_poly

        except (IndexError, ValueError):
            logger.error("Could not parse polygon from xml")
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
        response = self.session.get(self.url, headers=headers)
        response.raise_for_status()

        data = response.content

        if self.callback:
            self.callback(len(data))

        self.offset += len(data)
        return data


# =============================================================================
# Fetch
# =============================================================================
class Fetch:
    """Fetch class to fetch ftp/http data files"""

    def __init__(
        self,
        url: str,
        callback=fetches_callback,
        headers: Dict = R_HEADERS,
        verify: bool = True,
        allow_redirects: bool = True,
    ):
        self.url = url
        self.callback = callback
        self.headers = headers
        self.verify = verify
        self.allow_redirects = allow_redirects
        self.silent = logger.getEffectiveLevel() > logging.INFO

    def fetch_req(
        self,
        method: str = "GET",
        params: Optional[Dict] = None,
        data: Optional[Any] = None,
        json: Optional[Dict] = None,
        tries: int = 5,
        # timeout: Optional[Union[float, Tuple]] = None,
        timeout: Optional[float] = None,
        read_timeout: Optional[float] = None,
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

                req = requests.request(
                    method=method,
                    url=self.url,
                    params=params,
                    data=data,
                    json=json,
                    headers=self.headers,
                    # auth=self.auth,
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

                elif req.status_code == 416:  # Range Not Satisfiable
                    # If range fails, try fetching whole file
                    if "Range" in self.headers:
                        del self.headers["Range"]
                        continue

                elif 200 <= req.status_code <= 299:
                    return req

                else:
                    logger.error(f"Request from {req.url} returned {req.status_code}")
                    return req

            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/{tries} failed: {e}")
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
        dst_fn: str,
        params=None,
        datatype=None,
        overwrite=False,
        timeout=30,
        read_timeout=None,
        tries=5,
        check_size=True,
        verbose=True,
    ) -> int:
        """Fetch src_url and save to dst_fn with resume support."""

        # check if input `url` is a file path. Either check if it exists and move on or
        # copy it to the destination directory.
        if self.url and self.url.startswith("file://"):
            src_path = self.url[7:]  # Strip 'file://'

            # Source == Destination
            # Just index/verify the file, not move it.
            if os.path.abspath(src_path) == os.path.abspath(dst_fn):
                if os.path.exists(src_path):
                    if verbose:
                        logger.info(f"Verified local: {src_path}")
                    return 0
                else:
                    logger.error(f"Missing local file: {src_path}")
                    return -1

            # Copy from Network/Local -> Output Dir
            else:
                try:
                    import shutil

                    if not os.path.exists(os.path.dirname(dst_fn)):
                        os.makedirs(os.path.dirname(dst_fn))
                    shutil.copy2(src_path, dst_fn)
                    return 0
                except Exception as e:
                    logger.error(f"Local copy failed: {e}")
                    return -1

        # Regular file fetching here-on-out
        dst_dir = os.path.abspath(os.path.dirname(dst_fn))
        if not os.path.exists(dst_dir):
            try:
                os.makedirs(dst_dir)
            except OSError:
                pass

        part_fn = f"{dst_fn}.part"

        if not overwrite and os.path.exists(dst_fn):
            if not check_size:
                return 0  # Exists

            if os.path.getsize(dst_fn) > 0:
                return 0  # Exists

        for attempt in range(tries):
            resume_byte_pos = 0
            mode = "wb"

            # Resume if partial file exists
            if os.path.exists(part_fn):
                resume_byte_pos = os.path.getsize(part_fn)
                if resume_byte_pos > 0:
                    self.headers["Range"] = f"bytes={resume_byte_pos}-"
                    mode = "ab"

            try:
                with requests.get(
                    self.url,
                    stream=True,
                    params=params,
                    headers=self.headers,
                    timeout=(timeout, read_timeout),
                    verify=self.verify,
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
                    if check_size and total_size > 0 and resume_byte_pos == total_size:
                        ## We have the whole file in .part, just move it.
                        os.rename(part_fn, dst_fn)
                        return 0

                    # Error Codes
                    if req.status_code == 416:
                        # Range No Good: Local file is likely corrupt.
                        # Delete .part and retry from scratch (next loop iteration)
                        logger.warning(
                            f"Invalid Range for {os.path.basename(dst_fn)}. Restarting..."
                        )
                        if os.path.exists(part_fn):
                            os.remove(part_fn)
                        if "Range" in self.headers:
                            del self.headers["Range"]
                        continue

                    elif req.status_code == 401:
                        # Authentication Error
                        raise UnboundLocalError("Authentication Failed")

                    elif req.status_code not in [200, 206]:
                        # Fatal error for this attempt
                        if attempt < tries - 1:
                            time.sleep(2)
                            continue
                        raise ConnectionError(f"Status {req.status_code}")

                    with open(part_fn, mode) as f:
                        desc = utils.str_truncate_middle(self.url, n=60)
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
                                    logger.warning("Download cancelled by user.")
                                    return -1
                                if chunk:
                                    f.write(chunk)
                                    pbar.update(len(chunk))

                    # If we got here without exception, check size, if wanted
                    if check_size and total_size > 0:
                        final_size = os.path.getsize(part_fn)
                        if final_size < total_size:
                            # If smaller, the connection was most likely cut.
                            raise IOError(
                                f"Incomplete download: {final_size}/{total_size} bytes"
                            )

                        elif final_size > total_size:
                            # If larger, it was likely decompressed on the fly (GZIP).
                            logger.debug(
                                f"File size ({final_size}) > Header ({total_size}). "
                                "Assuming transparent decompression."
                            )

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
                    logger.warning(f"Download failed: {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to download {self.url}: {e}")
                    return -1

        return -1

    def fetch_ftp_file(self, dst_fn, params=None, datatype=None, overwrite=False):
        """Fetch an ftp file via ftplib with a progress bar."""

        import ftplib

        status = 0
        logger.info(f"Fetching remote ftp file: {self.url}...")

        dest_dir = os.path.dirname(dst_fn)
        if dest_dir and not os.path.exists(dest_dir):
            try:
                os.makedirs(dest_dir)
            except OSError:
                pass

        try:
            parsed = urllib.parse.urlparse(self.url)
            host = parsed.hostname
            path = parsed.path
            username = parsed.username or "anonymous"
            password = parsed.password or "anonymous@"

            ftp = ftplib.FTP(host)
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
                    desc=os.path.basename(dst_fn),
                    leave=True,
                ) as pbar:

                    def callback(data):
                        local_file.write(data)
                        pbar.update(len(data))

                    ftp.retrbinary(f"RETR {path}", callback)

            ftp.quit()
            logger.info(f"Fetched remote ftp file: {os.path.basename(self.url)}.")

        except Exception as e:
            logger.error(f"FTP Error: {e}")
            status = -1

            if os.path.exists(dst_fn):
                try:
                    os.remove(dst_fn)
                except OSError:
                    pass

        return status


# =============================================================================
# Threading & Queues
#
# `fetch_queue` and `fetch_results` have been depreciated, but left for legacy
# usage. They don't currently support hooks, but that could be added if we
# want to maintain these functions.
# =============================================================================
def fetch_queue(q: queue.Queue, stop_event: threading.Event, c: bool = True):
    """Worker for the fetch queue.
    q items: [remote_data_url, local_data_path, data-type, fetches-module, attempts, results-list]
    """

    # Modules that bypass SSL verification
    no_verify = ["mar_grav", "srtm_plus"]

    while not stop_event.is_set():
        url, local_path, data_type, module, retries, results_list = q.get()
        if stop_event.is_set():
            q.task_done()
            continue

        if not os.path.exists(os.path.dirname(local_path)):
            try:
                os.makedirs(os.path.dirname(local_path))
            except Exception:
                pass

        # fname = os.path.basename(local_path)
        # logger.debug(f"Queueing {fname}...")

        parsed_url = urllib.parse.urlparse(url)

        try:
            verify_ssl = False if module.name in no_verify else True

            if parsed_url.scheme == "ftp":
                status = Fetch(
                    url=url, callback=module.callback, headers=module.headers
                ).fetch_ftp_file(local_path)
            else:
                status = Fetch(
                    url=url,
                    headers=module.headers,
                    callback=module.callback,
                    verify=verify_ssl,
                ).fetch_file(local_path, check_size=c)

            if status == 0:
                logger.info(f"File {local_path} was fetched succesfully.")

            ## Record result
            fetch_results_entry = [url, local_path, data_type, status]
            results_list.append(fetch_results_entry)

            if callable(module.callback):
                module.callback(fetch_results_entry)

        except Exception as e:
            if retries > 0:
                q.put([url, local_path, data_type, module, retries - 1, results_list])
            else:
                logger.error(f"Failed to fetch {os.path.basename(local_path)}: {e}")
                results_list.append([url, local_path, data_type, str(e)])

                if callable(module.callback):
                    module.callback(fetch_results_entry)

        q.task_done()


class fetch_results(threading.Thread):
    """Threaded fetch runner."""

    def __init__(self, mod, check_size=True, n_threads=3, attempts=5):
        threading.Thread.__init__(self)
        self.fetch_q = queue.Queue()
        self.stop_event = threading.Event()
        self.mod = mod
        self.check_size = check_size
        self.n_threads = n_threads
        self.attempts = attempts
        self.results = []

        if len(self.mod.results) == 0:
            self.mod.run()

    def run(self):
        logger.info(f"Queuing {len(self.mod.results)} downloads...")

        for _ in range(self.n_threads):
            t = threading.Thread(
                target=fetch_queue,
                args=(self.fetch_q, self.stop_event, self.check_size),
            )
            t.daemon = True
            t.start()

        ## Queue item: [url, path, type, module, retries, results_ptr]
        for row in self.mod.results:
            if row["dst_fn"]:
                self.fetch_q.put(
                    [
                        row["url"],
                        os.path.join(self.mod._outdir, row["dst_fn"]),
                        row["data_type"],
                        self.mod,
                        self.attempts,
                        self.results,
                    ]
                )

        while not self.fetch_q.empty() and not self.stop_event.is_set():
            time.sleep(0.1)

        if not self.stop_event.is_set():
            self.fetch_q.join()

    def stop(self):
        """Stop all threads"""

        self.stop_event.set()


def _fetch_worker(module, entry, verbose=True):
    """Helper wrapper to call fetch_entry on a module."""

    try:
        return module.fetch_entry(entry, check_size=True, verbose=verbose)
    except Exception as e:
        logger.error(f"Worker failed for {entry.get('url', 'unknown')}: {e}")
        return -1


def run_fetchez(modules: List["FetchModule"], threads: int = 3, global_hooks=None):
    """Run Fetchez in parallel with hooks.

    - mod.hooks: Run ONLY on entries belonging to 'mod'.
    - global_hooks: Run on ALL entries combined.
    """

    STOP_EVENT.clear()
    if global_hooks is None:
        global_hooks = []

    silent = logger.getEffectiveLevel() > logging.INFO

    # --- Module Pre-Hooks ---
    for mod in modules:
        mod_pre = [h for h in mod.hooks if h.stage == "pre"]
        if not mod_pre:
            continue

        local_entries = [(mod, e) for e in mod.results]

        for hook in mod_pre:
            try:
                local_entries = hook.run(local_entries)
                if local_entries is None:
                    local_entries = []
            except Exception as e:
                logger.error(f'Module "{mod.name}" pre-hook "{hook.name}" failed: {e}')

        # Update the mod.results
        mod.results = [e for m, e in local_entries]

    all_entries = []
    for mod in modules:
        for entry in mod.results:
            all_entries.append((mod, entry))

    # --- Global Pre-Hooks ---
    global_pre = [h for h in global_hooks if h.stage == "pre"]
    for hook in global_pre:
        try:
            result = hook.run(all_entries)
            if isinstance(result, list):
                all_entries = result
        except Exception as e:
            logger.error(f'Global pre-hook "{hook.name}" failed: {e}')

    total_files = len(all_entries)
    if total_files == 0:
        logger.info("No files to fetch.")
        return

    logger.info(f"Starting parallel fetch: {total_files} files with {threads} threads.")
    final_results_with_owner = []

    active_hooks_full = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {
                executor.submit(_fetch_worker, mod, entry, verbose=True): (mod, entry)
                for mod, entry in all_entries
            }

            with tqdm(
                total=total_files,
                unit="file",
                desc="Fetching",
                position=0,
                leave=False,
                disable=silent,
            ) as pbar:
                for future in concurrent.futures.as_completed(futures):
                    mod, original_entry = futures[future]

                    try:
                        status = future.result()
                        original_entry.update({"status": status})
                        if status != 0:
                            logger.error(
                                f"Failed: {os.path.basename(original_entry['dst_fn'])}"
                            )
                    except Exception as e:
                        logger.error(f"Worker exception: {e}")
                        original_entry.update({"status": -1})

                    # --- 3. File Hooks ---
                    gf_hooks = [h for h in global_hooks if h.stage == "file"]
                    lf_hooks = [h for h in mod.hooks if h.stage == "file"]

                    active_hooks = utils.merge_hooks(gf_hooks, lf_hooks)
                    active_hooks_full.append(active_hooks)

                    current_entries = [(mod, original_entry)]

                    for hook in active_hooks:
                        try:
                            # Hook runs on current entry list
                            current_entries = hook.run(current_entries)
                            if current_entries is None:
                                current_entries = []
                        except Exception as e:
                            logger.error(f'File hook "{hook.name}" failed: {e}')

                    # --- STREAM DRIVER  ---
                    # If any hook set up a generator stream (e.g. SimpleStack, Filters),
                    # we must exhaust it here to trigger the processing.
                    processed_entries = []
                    for owner, item in current_entries:
                        stream = item.get("stream")
                        if stream and isinstance(
                            stream,
                            (collections.abc.Iterator, collections.abc.Generator),
                        ):
                            logger.debug(
                                f"Exhausting stream for {os.path.basename(item.get('dst_fn', ''))}..."
                            )
                            collections.deque(stream, maxlen=0)

                        processed_entries.append((owner, item))

                    final_results_with_owner.extend(processed_entries)
                    pbar.update(1)

    except KeyboardInterrupt:
        STOP_EVENT.set()
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
    results_by_mod: Dict[Any, Any] = {m: [] for m in modules}
    for r_tuple in final_results_with_owner:
        owner_mod, entry = r_tuple
        if owner_mod in results_by_mod:
            results_by_mod[owner_mod].append((owner_mod, entry))

    for mod in modules:
        mod_post = [h for h in mod.hooks if h.stage == "post"]
        if mod_post and results_by_mod[mod]:
            for hook in mod_post:
                try:
                    hook.run(results_by_mod[mod])
                except Exception as e:
                    logger.error(
                        f'Module "{mod.name}" post-hook "{hook.name}" failed: {e}'
                    )

    flat_results = final_results_with_owner
    global_post = [h for h in global_hooks if h.stage == "post"]
    for hook in global_post:
        try:
            hook.run(flat_results)
        except Exception as e:
            logger.error(f'Global post-hook "{hook.name}" failed: {e}')


# =============================================================================
# Fetch Module (Base & Default/Test Implementations)
#
# To create a sub-module, inherit from this `FetchModule` here.
# Then redefine `run` (and do whatever else). `run` should populate
# self.results, which is used for fetching. `self.results` should have
# at least `url`, `dst_fn` and `data_type` set for each fetch result,
# though any relevant info can fill the rest of it for whatever purpose...
# =============================================================================
class FetchModule:
    """Base class for all fetch modules."""

    def __init__(
        self,
        src_region=None,
        callback=fetches_callback,
        hook=None,
        outdir=None,
        name="fetches",
        min_year=None,
        max_year=None,
        weight=1.0,
        uncertainty=0.0,
        params={},
        **kwargs,
    ):
        self.region = src_region
        self.callback = callback
        self.outdir = outdir
        self.params = params
        self.status = 0
        self.results = []
        self.name = name
        self.min_year = utils.int_or(min_year)
        self.max_year = utils.int_or(max_year)
        self.headers = R_HEADERS.copy()

        if self.outdir is None:
            self._outdir = os.path.join(os.getcwd(), self.name)
        else:
            self._outdir = os.path.join(self.outdir, self.name)

        self.internal_hooks = []
        self.external_hooks = hook if hook else []

        self.weight = float(weight)
        self.uncertainty = float(uncertainty)

        # comment out for linter, but we'll be using this in the future.
        # presets = {}
        # Example structure:
        # presets = {
        #    'lidar-clean': [
        #        {'name': 'unzip'},
        #        {'name': 'filter', 'args': {'match': '.laz'}}
        #    ]
        # }

        # For dlim support, we can check these variables for
        # to do the proper processing. Set these to their correct
        # values in the sub-class.
        # Maybe with fetchez now, we can set these in `results`
        # instead...
        self.data_format = None
        self.src_srs = None
        self.title = None
        self.source = None
        self.date = None
        self.data_type = None
        self.resolution = None
        self.hdatum = None
        self.vdatum = None
        self.url = None

        # Default to whole world if region is invalid/missing
        # Set a generic region of the entire world in WGS84 if no region
        # was specified or if its an invalid region...this will result in quite
        # a lot of downloading on global datasets, so be careful with this.
        if self.region is None or not spatial.region_valid_p(self.region):
            self.region = (-180, 180, -90, 90)

        self.silent = logger.getEffectiveLevel() > logging.INFO

    @property
    def hooks(self):
        """Combine internal and external hooks in the correct execution order."""

        return self.internal_hooks + self.external_hooks

    def add_hook(self, hook_obj):
        """Add a hook instance at runtime."""

        if hasattr(hook_obj, "run"):
            self.external_hooks.append(hook_obj)
        else:
            logger.warning(
                f"Hook {hook_obj} does not appear to be a valid FetchHook class."
            )

    def run(self):
        """set `run` in a sub-module to populate `results` with urls"""

        raise NotImplementedError

    def fetch_entry(self, entry, check_size=True, retries=5, verbose=True):
        try:
            parsed_url = urllib.parse.urlparse(entry["url"])
            if parsed_url.scheme == "ftp":
                logger.info("ok")
                status = Fetch(url=entry["url"], headers=self.headers).fetch_ftp_file(
                    os.path.join(self._outdir, entry["dst_fn"])
                )
            else:
                status = Fetch(
                    url=entry["url"],
                    headers=self.headers,
                ).fetch_file(
                    os.path.join(self._outdir, entry["dst_fn"]),
                    check_size=check_size,
                    tries=retries,
                    verbose=verbose,
                )
        except Exception:
            status = -1
        return status

    def fetch_results(self):
        """fetch the gathered `results` from the sub-class"""

        for entry in self.results:
            self.fetch(entry)

    def fill_results(self, entry):
        """fill self.results with the fetch module entry"""

        self.results.append(
            {"url": entry[0], "dst_fn": entry[1], "data_type": entry[2]}
        )

    def add_entry_to_results(self, url, dst_fn, data_type, **kwargs):
        """Add fetch entries to `results`. any keyword/args can be
        added to `results`, but we need `url`, `dst_fn` and `data_type`.
        """

        # if utils.str_or(dst_fn) is not None:
        #     dst_fn = os.path.join(self._outdir, dst_fn)
        entry = {"url": url, "dst_fn": dst_fn, "data_type": data_type}
        entry.update(kwargs)
        self.results.append(entry)


# Simple Fetch Module to fetch a url.
# It will just add that url to `results`.
class HttpDataset(FetchModule):
    """Fetch an http file directly."""

    def __init__(self, url=None, **kwargs):
        super().__init__(**kwargs)
        self.url = url

        if self.url:
            self.add_entry_to_results(self.url, os.path.basename(self.url), "https")
