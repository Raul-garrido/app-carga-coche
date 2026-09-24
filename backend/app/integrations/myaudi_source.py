"""Isolated adapter around MyAudi, built on the `carconnectivity` framework
(https://github.com/tillsteinbach/CarConnectivity) plus its Audi connector
(https://github.com/acfischer42/CarConnectivity-connector-audi).

This replaces an earlier attempt based on a package called `audiconnectpy`,
which turned out **not to exist on PyPI at all** (confirmed 404 fetching
https://pypi.org/pypi/audiconnectpy/json — an earlier research pass had
taken a search-engine summary at face value without actually installing
it). `carconnectivity` and `carconnectivity-connector-audi` were verified
for real: both installed cleanly with pip, and everything this module
relies on (class names, methods, enum values, config shape) was read
directly out of the installed package source, not guessed from docs.
None of this has been run against a real Audi account — there's no test
account available. Treat first use as a real integration test.

Design, still true to the original plan:
  - Quarantined here so a breaking change upstream doesn't ripple into the
    rest of the app.
  - Falls back to manual SoC entry automatically on any failure (see
    battery_source.MyAudiBatterySource).
  - `carconnectivity` itself owns a background thread once started
    (`CarConnectivity.startup()`) that polls Audi's backend on its own
    schedule and already backs off 15 minutes on a 429 (rate limit) — see
    `_background_loop` in the installed connector's `connector.py`. This
    class does not poll the network itself; it just reads whatever the
    background thread has already fetched into memory.
  - `interval` (seconds between polls) has a hard minimum of 180s enforced
    by the connector itself; MYAUDI_MIN_POLL_INTERVAL_SECONDS is clamped
    to that floor.

Requires `pip install -r requirements-myaudi.txt` and a filled-in `.env`
(MYAUDI_USERNAME, MYAUDI_PASSWORD, optionally MYAUDI_SPIN) with
MYAUDI_AUTO_ENABLED=true. SPIN is only used for vehicle commands
(lock/climate/etc.), not for reading charge status, so it's optional here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

LOG = logging.getLogger(__name__)


@dataclass
class MyAudiCredentials:
    username: str
    password: str
    spin: Optional[str] = None


@dataclass(frozen=True)
class MyAudiStatus:
    percent: float
    charging: bool
    remaining_minutes: Optional[int]


class MyAudiClient:
    def __init__(
        self,
        credentials: MyAudiCredentials,
        tokenstore_file: Path,
        cache_file: Path,
        poll_interval_seconds: int = 300,
    ):
        self._credentials = credentials
        self._tokenstore_file = str(tokenstore_file)
        self._cache_file = str(cache_file)
        # The Audi connector rejects an interval below 180s outright.
        self._poll_interval_seconds = max(poll_interval_seconds, 180)
        self._car_connectivity = None

    def start(self) -> None:
        """Create the CarConnectivity instance and start its background
        polling thread. Call once, at app startup."""
        try:
            from carconnectivity.carconnectivity import CarConnectivity
        except ImportError as exc:
            raise RuntimeError(
                "carconnectivity is not installed. Run "
                "'pip install -r requirements-myaudi.txt' or disable "
                "MYAUDI_AUTO_ENABLED and use manual SoC entry instead."
            ) from exc

        connector_config = {
            "username": self._credentials.username,
            "password": self._credentials.password,
            "interval": self._poll_interval_seconds,
        }
        if self._credentials.spin:
            connector_config["spin"] = self._credentials.spin

        config = {"carConnectivity": {"connectors": [{"type": "audi", "config": connector_config}]}}
        self._car_connectivity = CarConnectivity(
            config=config,
            tokenstore_file=self._tokenstore_file,
            cache_file=self._cache_file,
        )
        self._car_connectivity.startup()

    def stop(self) -> None:
        if self._car_connectivity is not None:
            self._car_connectivity.shutdown()
            self._car_connectivity = None

    def get_status(self) -> MyAudiStatus:
        """Read whatever the background thread has already fetched. Does
        not itself make a network call, so it's cheap to call often."""
        from carconnectivity.charging import Charging
        from carconnectivity.drive import ElectricDrive

        if self._car_connectivity is None:
            raise RuntimeError("MyAudiClient.start() was not called")

        vehicles = self._car_connectivity.garage.list_vehicles()
        if not vehicles:
            raise RuntimeError("No vehicles on this MyAudi account yet (still fetching?)")
        vehicle = vehicles[0]

        electric_drive = next(
            (d for d in vehicle.drives.drives.values() if isinstance(d, ElectricDrive)), None
        )
        if electric_drive is None or electric_drive.level.value is None:
            raise RuntimeError("No electric drive / battery level reported yet")
        percent = float(electric_drive.level.value)

        charging_state = vehicle.charging.state.value
        charging = charging_state == Charging.ChargingState.CHARGING

        remaining_minutes = None
        estimated = vehicle.charging.estimated_date_reached.value
        if charging and estimated is not None:
            now = datetime.now(tz=estimated.tzinfo or timezone.utc)
            remaining_minutes = max(int((estimated - now).total_seconds() // 60), 0)

        return MyAudiStatus(percent=percent, charging=charging, remaining_minutes=remaining_minutes)
