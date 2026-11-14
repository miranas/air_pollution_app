from backend.utils.decorators import add_timing
from typing import Tuple, Optional
import time
import requests
import logging

# import existing constants
from backend.network.config import (
    ARSO_STATIONS_URL,        # "https://www.arso.gov.si/xml/zrak/ones_zrak_urni_podatki_zadnji.xml"
    REQUEST_TIMEOUT,          # 10 seconds
)

# =================================================================================
# RETRY POLICY - transient failures are retried, permanent ones are not
# ================================================================================

MAX_ATTEMPTS = 3                              # 1 attempt + 2 retries
BACKOFF_SECONDS = (1.0, 2.0)                  # sleep before retry 1, retry 2
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
CONNECT_TIMEOUT = 3.05                        # fail fast if ARSO is unreachable


def _is_retryable(exc: requests.RequestException) -> bool:
    """Return True when retrying the same request can plausibly succeed.

    Timeout and ConnectionError are transient by nature. HTTPError carries the
    response, so retry only rate limiting (429) and server-side failures (5xx);
    other 4xx errors will not fix themselves.
    """
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    response = getattr(exc, "response", None)
    return response is not None and response.status_code in RETRYABLE_STATUS_CODES


def _fetch_once() -> str:
    """Perform one HTTP attempt and return the XML body.

    Raises:
        requests.RequestException: on timeout, connection error or HTTP error.
    """
    response = requests.get(
        ARSO_STATIONS_URL,
        timeout=(CONNECT_TIMEOUT, REQUEST_TIMEOUT),  # (connect, read)
    )
    response.encoding = "utf-8"
    response.raise_for_status()
    return response.text


# =================================================================================
# XML FETCHING - Download data from ARSO
# ================================================================================

@add_timing
def fetch_arso_xml() -> Tuple[bool, Optional[str], Optional[str]]:
    """Fetch the latest ARSO XML snapshot, retrying transient failures.

    Policy:
        - up to MAX_ATTEMPTS attempts (1 + 2 retries),
        - sleeps BACKOFF_SECONDS[attempt - 1] between retries,
        - retries Timeout, ConnectionError, HTTP 429/500/502/503/504,
        - fails immediately on other 4xx errors.

    RETURNS:
        Tuple[success[bool], xml_data[str], error[str]]
        - True, <xml>..</xml>, None on success
        - False, None, error message after the last attempt fails
    """
    last_error = "unknown error"

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            logging.info(
                "Fetching ARSO xml data (attempt %d/%d)", attempt, MAX_ATTEMPTS
            )
            xml_text = _fetch_once()
            logging.info(
                "Successfully fetched ARSO xml data Length: %d characters",
                len(xml_text),
            )
            return True, xml_text, None

        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"

            if attempt >= MAX_ATTEMPTS or not _is_retryable(exc):
                break

            delay = BACKOFF_SECONDS[attempt - 1]
            logging.warning(
                "ARSO fetch failed (attempt %d/%d): %s; retrying in %.1fs",
                attempt, MAX_ATTEMPTS, exc, delay,
            )
            time.sleep(delay)

    logging.error(
        "ARSO fetch failed after %d attempt(s): %s", attempt, last_error
    )
    return (
        False,
        None,
        f"ARSO fetch failed after {attempt} attempt(s): {last_error}",
    )
