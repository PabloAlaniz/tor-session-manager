"""
Destination-block detection.

Many sites block Tor exit IPs outright — with a 403/429, a Cloudflare
"checking your browser" interstitial, or a CAPTCHA challenge. This module
inspects a ``requests.Response`` and reports whether it looks blocked, so the
client can rotate to a fresh exit and retry.

Detection is heuristic by nature (a legitimate 403 can look like a block), so
the markers and statuses are deliberately specific and overridable per call.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# HTTP statuses that commonly indicate a block / challenge / rate limit.
BLOCK_STATUS = {403, 429, 503}

# Specific body markers for challenge / CAPTCHA interstitials. Kept specific
# to avoid false positives on pages that merely mention "captcha".
CHALLENGE_MARKERS = (
    "just a moment...",
    "attention required! | cloudflare",
    "cf-browser-verification",
    "cf-chl",
    "checking your browser before",
    "please verify you are a human",
    "g-recaptcha",
    "h-captcha",
    "captcha-delivery",
)

# How much of the body to scan for markers.
_BODY_SCAN_LIMIT = 20000


def detect_block(response, markers=None, statuses=None) -> Optional[str]:
    """
    Return a short reason if ``response`` looks blocked, else None.

    Args:
        response: A ``requests.Response`` (or any object exposing
            ``status_code``, ``headers`` and ``text``).
        markers: Override for the challenge body markers (defaults to
            ``CHALLENGE_MARKERS``).
        statuses: Override for the block HTTP statuses (defaults to
            ``BLOCK_STATUS``).

    Returns:
        A short reason string (e.g. ``"http_403"``, ``"cloudflare_503"``,
        ``"challenge:just a moment..."``, ``"http_429_rate_limited"``), or None
        if the response does not look blocked.
    """
    markers = CHALLENGE_MARKERS if markers is None else markers
    statuses = BLOCK_STATUS if statuses is None else statuses

    status = getattr(response, "status_code", None)
    headers = getattr(response, "headers", {}) or {}
    server = str(headers.get("Server", "")).lower()

    try:
        body = (response.text or "")[:_BODY_SCAN_LIMIT].lower()
    except Exception:  # noqa: BLE001 - body may be unavailable
        body = ""

    for marker in markers:
        if marker in body:
            return f"challenge:{marker}"

    if status in statuses:
        if status == 429:
            return "http_429_rate_limited"
        if "cloudflare" in server:
            return f"cloudflare_{status}"
        return f"http_{status}"

    return None
