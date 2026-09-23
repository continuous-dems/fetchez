"""Validate/retry individual strict TNM product pages before accepting them.

A successful HTTP response is not necessarily a complete TNM API response.
This is the strict product-discovery page validator; legacy queries are unchanged.
"""

import hashlib
import logging
import time

logger = logging.getLogger(__name__)


def _page_errors(data, offset, expected_total, seen_urls):
    """Explain why a page cannot safely enter the discovery manifest."""
    if not isinstance(data, dict):
        return [f"JSON root is {type(data).__name__}, not an object"]
    total = data.get("total")
    items = data.get("items")
    errors = []
    if type(total) is not int or total < 0:
        errors.append(f"total is {total!r} (expected a nonnegative integer)")
    if not isinstance(items, list):
        errors.append(f"items is {type(items).__name__} (expected list)")
        return errors
    if type(total) is int and total >= 0:
        if offset + len(items) > total:
            errors.append(
                f"offset + count = {offset + len(items)} exceeds total {total}"
            )
        if offset < total and not items:
            errors.append(f"empty page before total {total}")
        if expected_total is not None and total != expected_total:
            errors.append(f"total changed from {expected_total} to {total}")
    page_urls = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"item {index} is not an object")
            continue
        url = item.get("downloadURL")
        if not isinstance(url, str) or not url.strip():
            errors.append(f"item {index} lacks a download URL")
        elif url in seen_urls or url in page_urls:
            errors.append(f"item {index} has a repeated download URL")
        else:
            page_urls.add(url)
    return errors


def _api_error_detail(data):
    """Capture a bounded server explanation, never a whole JSON response/URL."""
    if not isinstance(data, dict):
        return None
    if not (data.get("error") or data.get("toastType") == "error"):
        return None
    message = data.get("toastMessage") or data.get("errorMessage")
    if not isinstance(message, str):
        message = "unspecified upstream error"
    message = " ".join(message.split())[:300]
    return f"TNM API returned an explicit error response: {message}"


def fetch_strict_page(
    fetch, params, offset, expected_total, seen_urls, dataset, attempts=3
):
    """Return a fully checked response or fail closed with actionable context.

    Invalid HTTP-200 pages are retried at the *same* offset. No entry is added
    until the page passes. Transport failures, non-200 statuses, and explicit
    API errors retain the existing TNM error-handling path.
    """
    if attempts < 1:
        raise ValueError("TNM strict page attempts must be positive")
    for attempt in range(1, attempts + 1):
        response = fetch(params=params)
        if response is None or response.status_code != 200:
            return response
        if "All dataset queries failed" in response.text:
            return response
        try:
            data = response.json()
        except (ValueError, TypeError) as exc:
            errors = [f"invalid JSON: {type(exc).__name__}"]
            data = None
        else:
            if isinstance(data, dict) and data.get("errorMessage"):
                return response
            api_error = _api_error_detail(data)
            if api_error is not None:
                # An explicit API error is not a transient *incomplete page*.
                # Do not spend three tries and several full dem-devel reruns
                # treating the same rejected request as damaged pagination.
                response.close()
                raise ValueError(f"{api_error}; dataset={dataset!r} offset={offset}")
            errors = _page_errors(data, offset, expected_total, seen_urls)
        if not errors:
            return response
        # Bounded diagnostics: no full response body or individual source URLs.
        fingerprint = hashlib.sha256(response.content).hexdigest()[:16]
        count = (
            len(data["items"])
            if isinstance(data, dict) and isinstance(data.get("items"), list)
            else None
        )
        detail = (
            f"TNM API returned an incomplete or invalid page: "
            f"dataset={dataset!r} offset={offset} "
            f"expected_total={expected_total!r} "
            f"attempt={attempt}/{attempts} "
            f"keys={sorted(data) if isinstance(data, dict) else []} "
            f"items_count={count} "
            f"response_sha256_prefix={fingerprint} "
            f"reasons={'; '.join(errors[:5])}"
        )
        response.close()
        if attempt == attempts:
            raise ValueError(detail)
        logger.warning("%s; retrying the same page", detail)
        time.sleep(min(attempt, 2))
    raise AssertionError("unreachable")
