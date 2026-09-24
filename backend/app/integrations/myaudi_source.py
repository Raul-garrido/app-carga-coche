"""Isolated adapter around the unofficial MyAudi API.

Everything in this file is quarantined on purpose: it is the one part of
the app built on reverse-engineered, community-maintained access to a
vendor backend that can (and, per public issue trackers, regularly does)
change without notice. If it breaks, nothing outside this file should need
to change — the app falls back to manual SoC entry automatically (see
`battery_source.MyAudiBatterySource`).

Status as of this writing (research done Sept 2026), NOT verified against
a real account:
  - The `audiconnectpy` PyPI package (https://pypi.org/project/audiconnectpy/)
    is the actively maintained Python client backing the Home Assistant
    `audi_connect_ha` integration. It wraps the same OAuth2/OIDC flow
    documented by github.com/Grudesky/myaudi-api and
    github.com/audiconnect/audi_connect_ha.
  - Audi's backend enforces aggressive rate limiting (community reports:
    on the order of ~6 requests/hour before a temporary lockout that also
    affects the official app). This module defaults to a long minimum
    poll interval to stay well under that.
  - Multiple 2026 issues on audi_connect_ha report "Invalid credentials"
    failures traced to Play Integrity attestation checks on Audi's login
    endpoint, which a non-official client cannot always satisfy. This can
    make automatic login intermittently or permanently unavailable
    regardless of how this module is written — it is a backend-side risk,
    not a bug to fix here.
  - The exact `audiconnectpy` call signature (constructor args, method
    names) could not be confirmed from published docs at the time this
    was written. TODO before first real use: pip install the package,
    read its actual API in site-packages, and adjust `_fetch_soc_raw`
    below accordingly — do not assume this compiles/works unmodified.

Because of all of the above, this module is optional (see
requirements-myaudi.txt) and disabled unless MYAUDI_AUTO_ENABLED=true.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class MyAudiCredentials:
    username: str
    password: str
    spin: str | None = None


class MyAudiClient:
    """Thin, rate-limited wrapper. Caches the last SoC and refuses to poll
    more often than `min_poll_interval_seconds`."""

    def __init__(
        self,
        credentials: MyAudiCredentials,
        min_poll_interval_seconds: int = 900,  # 15 min; ~6 req/hour ceiling
    ):
        self._credentials = credentials
        self._min_poll_interval = min_poll_interval_seconds
        self._last_fetch_at: float = 0.0
        self._last_percent: float | None = None
        self._connection = None  # lazily created underlying client

    async def fetch_soc(self) -> float:
        now = time.monotonic()
        if self._last_percent is not None and (now - self._last_fetch_at) < self._min_poll_interval:
            return self._last_percent

        percent = await self._fetch_soc_raw()
        self._last_percent = percent
        self._last_fetch_at = now
        return percent

    async def _fetch_soc_raw(self) -> float:
        """Talk to Audi's backend. Isolated so it's the only thing that
        needs updating if the upstream API surface changes."""
        try:
            from audiconnectpy import AudiConnect  # optional dependency
        except ImportError as exc:
            raise RuntimeError(
                "audiconnectpy is not installed. Run "
                "'pip install -r requirements-myaudi.txt' or disable "
                "MYAUDI_AUTO_ENABLED and use manual SoC entry instead."
            ) from exc

        if self._connection is None:
            # NOTE: verify these constructor kwargs against the installed
            # audiconnectpy version before relying on this in production.
            self._connection = AudiConnect(
                username=self._credentials.username,
                password=self._credentials.password,
                spin=self._credentials.spin,
            )
            await self._connection.async_login()

        vehicles = await self._connection.async_get_vehicles()
        if not vehicles:
            raise RuntimeError("MyAudi account has no vehicles")
        vehicle = vehicles[0]
        # NOTE: field name (state_of_charge / battery_soc / soc_level, ...)
        # depends on the installed audiconnectpy version; verify and adjust.
        return float(vehicle.state_of_charge)
