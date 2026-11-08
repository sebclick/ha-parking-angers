"""HTTP client for the data.angers.fr open data API (no Home Assistant dependency)."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from typing import Any

import aiohttp

from .const import (
    API_BASE_URL,
    API_LIMIT,
    API_TIMEOUT,
    DEPRECATION_HEADER,
    MAX_NAME_LENGTH,
    MAX_RESPONSE_BYTES,
    REALTIME_DATASET,
    REFERENCE_DATASET,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)


class ParkingAngersError(Exception):
    """Base error."""


class ParkingAngersConnectionError(ParkingAngersError):
    """Timeout, DNS failure or server error."""


class ParkingAngersRateLimitError(ParkingAngersError):
    """Quota exceeded (HTTP 429)."""

    def __init__(self, message: str, retry_after: datetime | None = None) -> None:
        """Initialise with the instant the quota is reset, if known."""
        super().__init__(message)
        self.retry_after = retry_after


class ParkingAngersResponseError(ParkingAngersError):
    """Client error, invalid JSON or unexpected schema."""


def _parse_reset(value: str | None) -> datetime | None:
    """Parse ``X-RateLimit-Reset`` (epoch seconds or ISO 8601)."""
    if not value:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=UTC)
    except ValueError, OverflowError, OSError:
        pass
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class ParkingAngersApi:
    """Client for the Angers car park datasets."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialise with an aiohttp session."""
        self._session = session
        self._deprecation_logged = False
        self.last_availability_raw: dict[str, Any] | None = None

    async def _get_records(self, dataset: str) -> dict[str, Any]:
        url = f"{API_BASE_URL}/{dataset}/records"
        try:
            async with self._session.get(
                url,
                params={"limit": API_LIMIT},
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
            ) as resp:
                if DEPRECATION_HEADER in resp.headers and not self._deprecation_logged:
                    self._deprecation_logged = True
                    _LOGGER.warning(
                        "data.angers.fr announces the deprecation of the API used by "
                        "this integration: %s",
                        resp.headers[DEPRECATION_HEADER],
                    )
                if resp.status == 429:
                    raise ParkingAngersRateLimitError(
                        "API quota exceeded",
                        _parse_reset(resp.headers.get("X-RateLimit-Reset")),
                    )
                if resp.status >= 500:
                    raise ParkingAngersConnectionError(
                        f"Server error {resp.status} on {dataset}"
                    )
                payload = await self._read_json(resp, dataset)
                if resp.status >= 400:
                    detail = payload if isinstance(payload, dict) else {}
                    raise ParkingAngersResponseError(
                        f"HTTP {resp.status} on {dataset}: "
                        f"{detail.get('error_code')} {detail.get('message')}"
                    )
        except (TimeoutError, aiohttp.ClientError) as err:
            raise ParkingAngersConnectionError(
                f"Error connecting to {dataset}: {err!r}"
            ) from err

        if not isinstance(payload, dict) or not isinstance(
            payload.get("results"), list
        ):
            raise ParkingAngersResponseError(f"Unexpected schema from {dataset}")
        total = payload.get("total_count")
        if isinstance(total, int) and total > API_LIMIT:
            _LOGGER.warning(
                "%s returned %s records, only the first %s are used",
                dataset,
                total,
                API_LIMIT,
            )
        return payload

    @staticmethod
    async def _read_json(resp: aiohttp.ClientResponse, dataset: str) -> Any:
        """Read and decode the body, refusing oversized responses."""
        body = bytearray()
        async for chunk in resp.content.iter_chunked(64 * 1024):
            body.extend(chunk)
            if len(body) > MAX_RESPONSE_BYTES:
                raise ParkingAngersResponseError(
                    f"Response from {dataset} exceeds {MAX_RESPONSE_BYTES} bytes"
                )
        try:
            return json.loads(body)
        except ValueError as err:
            raise ParkingAngersResponseError(f"Invalid JSON from {dataset}") from err

    async def async_get_availability(self) -> dict[str, int]:
        """Return the number of free spaces by real-time ``nom``."""
        payload = await self._get_records(REALTIME_DATASET)
        self.last_availability_raw = payload
        result: dict[str, int] = {}
        for record in payload["results"]:
            if not isinstance(record, dict):
                _LOGGER.debug("Ignoring invalid record: %r", record)
                continue
            name = record.get("nom")
            available = record.get("disponible")
            if (
                not isinstance(name, str)
                or not name.strip()
                or len(name.strip()) > MAX_NAME_LENGTH
            ):
                _LOGGER.debug("Ignoring record with invalid nom: %r", record)
                continue
            if (
                not isinstance(available, int)
                or isinstance(available, bool)
                or available < 0
            ):
                _LOGGER.debug("Ignoring record with invalid disponible: %r", record)
                continue
            result[name.strip()] = available
        return result

    async def async_get_reference(self) -> dict[str, dict[str, Any]]:
        """Return raw reference records by ``id``."""
        payload = await self._get_records(REFERENCE_DATASET)
        result: dict[str, dict[str, Any]] = {}
        for record in payload["results"]:
            if isinstance(record, dict) and isinstance(record.get("id"), str):
                result[record["id"]] = record
            else:
                _LOGGER.debug("Ignoring reference record without id: %r", record)
        return result
