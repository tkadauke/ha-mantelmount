"""Client for the MantelMount network adapter.

The adapter speaks two protocols:

* UDP on port 81 for status queries and movement commands. Every datagram is an
  ASCII command terminated by a carriage return. The adapter answers ``MMQ`` with a
  comma-separated status line and acknowledges other commands by echoing the
  three-letter command prefix (``MMR0`` is acknowledged with ``MMR``).
* HTTP on port 80 for the built-in web UI. ``ajax.shtml`` reports the position in
  degrees and the ALPS (auto lowering power sensing) state, and ``device.shtml``
  holds the ALPS settings form that posts to ``save_device.xml``.

The adapter runs a small embedded TCP/IP stack, so requests are serialized and
polling should stay modest.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import IntEnum
from html.parser import HTMLParser
import json
import re

import aiohttp

DEFAULT_UDP_PORT = 81
DEFAULT_HTTP_PORT = 80
DEFAULT_TIMEOUT = 2.0
DEFAULT_ATTEMPTS = 3

PRESET_COUNT = 3
POSITION_VARIABLES = ("cazim", "celev", "temp", "tvstat", "curcur")

MAC_PATTERN = re.compile(r"MAC Address:.*?([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})", re.DOTALL)
HOST_NAME_PATTERN = re.compile(r"Host Name:</b>\s*</div>\s*<div[^>]*>\s*([^<\s]+)", re.DOTALL)


class MantelMountError(Exception):
    """Base error for MantelMount communication failures."""


class MantelMountTimeoutError(MantelMountError):
    """The adapter did not answer within the timeout after all attempts."""


class MantelMountResponseError(MantelMountError):
    """The adapter answered with something that could not be understood."""


class Jog(IntEnum):
    """Arguments of the ``MMJ`` jog command."""

    STOP = 0
    RIGHT = 1
    UP = 2
    LEFT = 3
    DOWN = 4


class SmoothStart(IntEnum):
    """Values of the ``stabrel`` smooth start setting."""

    NONE = 0
    MINIMUM = 1
    MEDIUM = 2
    MAXIMUM = 3


@dataclass(frozen=True)
class MountStatus:
    """
    Parsed ``MMQ`` status reply.

    Field order follows the published Control4 and Crestron drivers. The position
    fields of the reply are not exposed because the drivers disagree on their order;
    :class:`MountPosition` reports position from the web UI instead.
    """

    error_code: int
    left_actuator: int
    right_actuator: int
    last_preset: int
    temperature: int
    tv_on: bool
    last_event_source: int
    firmware_version: int
    position_lost: bool
    tv_current: int
    left_at_limit: bool
    right_at_limit: bool
    left_motor_current: int
    right_motor_current: int

    @classmethod
    def parse(cls, reply: str) -> MountStatus:
        """
        Parse a raw ``MMQ`` reply such as ``MMQ0,0,0,0,0,0,33,0,0,693,0,69,1,1,0,4``.

        Raises :class:`MantelMountResponseError` if the reply is not a status line
        with at least sixteen integer fields.
        """
        text = reply.strip()
        if text.count("MMQ") > 1:
            text = "MMQ" + text.rsplit("MMQ", 1)[1]
        if not text.startswith("MMQ"):
            raise MantelMountResponseError(f"Not a status reply: {reply!r}")
        fields = text[3:].split(",")
        if len(fields) < 16:
            raise MantelMountResponseError(f"Status reply has {len(fields)} fields: {reply!r}")
        try:
            values = [int(field) for field in fields[:16]]
        except ValueError as err:
            raise MantelMountResponseError(f"Status reply is not numeric: {reply!r}") from err
        return cls(
            error_code=values[0],
            left_actuator=values[3],
            right_actuator=values[4],
            last_preset=values[5],
            temperature=values[6],
            tv_on=values[7] == 1,
            last_event_source=values[8],
            firmware_version=values[9],
            position_lost=values[10] != 0,
            tv_current=values[11],
            left_at_limit=values[12] == 1,
            right_at_limit=values[13] == 1,
            left_motor_current=values[14],
            right_motor_current=values[15],
        )


@dataclass(frozen=True)
class MountPosition:
    """
    Position and ALPS state reported by ``ajax.shtml``.

    Azimuth is negative to the left and positive to the right. Elevation is zero when
    stowed and negative as the mount lowers.
    """

    azimuth: float
    elevation: float
    temperature_status: str
    tv_on: bool
    tv_current: int

    @property
    def is_home(self) -> bool:
        """Whether the mount is in its stowed position."""
        return abs(self.azimuth) < 0.01 and abs(self.elevation) < 0.01

    @classmethod
    def parse(cls, body: str) -> MountPosition:
        """
        Parse the JSON array answered for ``ajax.shtml?var=cazim,celev,temp,tvstat,curcur``.

        Raises :class:`MantelMountResponseError` if the body is not such an array.
        """
        try:
            values = json.loads(body)
            return cls(
                azimuth=float(values[0]),
                elevation=float(values[1]),
                temperature_status=str(values[2]),
                tv_on=str(values[3]).lower() == "on",
                tv_current=int(values[4]),
            )
        except (ValueError, TypeError, IndexError) as err:
            raise MantelMountResponseError(f"Unexpected position reply: {body!r}") from err


@dataclass(frozen=True)
class AlpsSettings:
    """ALPS settings from the ``device.shtml`` form, with currents in milliamps."""

    enabled: bool
    tv_on_threshold: int
    tv_off_threshold: int
    smooth_start: SmoothStart


@dataclass(frozen=True)
class DeviceInfo:
    """Identity of the adapter as shown on ``network.shtml``."""

    mac: str
    host_name: str | None


class SettingsForm(HTMLParser):
    """Collects the fields of the ``save_device.xml`` form the way a browser submits them."""

    def __init__(self) -> None:
        super().__init__()
        self.fields: dict[str, str] = {}
        self._in_form = False
        self._select: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}
        if tag == "form":
            self._in_form = attributes.get("action", "").endswith("save_device.xml")
        elif not self._in_form:
            return
        elif tag == "input" and attributes.get("name"):
            self.fields[attributes["name"]] = attributes.get("value", "")
        elif tag == "select" and attributes.get("name"):
            self._select = attributes["name"]
        elif tag == "option" and self._select and "selected" in attributes:
            self.fields[self._select] = attributes.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._in_form = False
        elif tag == "select":
            self._select = None

    @classmethod
    def parse(cls, page: str) -> dict[str, str]:
        """
        Return the submitted field values of the settings form on ``page``.

        Raises :class:`MantelMountResponseError` if the ALPS fields are missing.
        """
        parser = cls()
        parser.feed(page)
        missing = {"enable_alps", "curon", "curoff", "stabrel"} - parser.fields.keys()
        if missing:
            raise MantelMountResponseError(f"Settings form is missing {sorted(missing)}")
        return parser.fields


def parse_alps_settings(fields: dict[str, str]) -> AlpsSettings:
    """
    Convert raw settings form fields into :class:`AlpsSettings`.

    Raises :class:`MantelMountResponseError` if a value is not numeric or unknown.
    """
    try:
        return AlpsSettings(
            enabled=fields["enable_alps"] == "1",
            tv_on_threshold=int(fields["curon"]),
            tv_off_threshold=int(fields["curoff"]),
            smooth_start=SmoothStart(int(fields["stabrel"])),
        )
    except (KeyError, ValueError) as err:
        raise MantelMountResponseError(f"Unexpected settings: {fields!r}") from err


def parse_device_info(page: str) -> DeviceInfo:
    """
    Read the MAC address and host name from ``network.shtml``.

    Raises :class:`MantelMountResponseError` if no MAC address is present.
    """
    mac = MAC_PATTERN.search(page)
    if mac is None:
        raise MantelMountResponseError("Network page does not show a MAC address")
    host_name = HOST_NAME_PATTERN.search(page)
    return DeviceInfo(mac=mac.group(1).lower(), host_name=host_name.group(1) if host_name else None)


class UdpReply(asyncio.DatagramProtocol):
    """Resolves a future with the first datagram received."""

    def __init__(self) -> None:
        self.reply: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    def datagram_received(self, data: bytes, addr: tuple[str | int, ...]) -> None:
        if not self.reply.done():
            self.reply.set_result(data.decode("ascii", errors="replace"))

    def error_received(self, exc: Exception) -> None:
        if not self.reply.done():
            self.reply.set_exception(MantelMountError(str(exc)))


class MantelMountClient:
    """
    Talks to one MantelMount adapter.

    All requests share one lock because the adapter handles one exchange at a time
    reliably. UDP exchanges are retried because datagrams can be lost.
    """

    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession,
        *,
        udp_port: int = DEFAULT_UDP_PORT,
        http_port: int = DEFAULT_HTTP_PORT,
        timeout: float = DEFAULT_TIMEOUT,
        attempts: int = DEFAULT_ATTEMPTS,
    ) -> None:
        self.host = host
        self._session = session
        self._udp_port = udp_port
        self._http_port = http_port
        self._timeout = timeout
        self._attempts = attempts
        self._lock = asyncio.Lock()

    @property
    def base_url(self) -> str:
        """Base URL of the adapter's web UI."""
        return f"http://{self.host}" if self._http_port == 80 else f"http://{self.host}:{self._http_port}"

    async def async_get_status(self) -> MountStatus:
        """Query ``MMQ``; raises :class:`MantelMountError` on failure."""
        return MountStatus.parse(await self._async_exchange("MMQ", "MMQ"))

    async def async_get_position(self) -> MountPosition:
        """Read position and ALPS state; raises :class:`MantelMountError` on failure."""
        return MountPosition.parse(await self._async_http_get(f"/ajax.shtml?var={','.join(POSITION_VARIABLES)}"))

    async def async_get_alps_settings(self) -> AlpsSettings:
        """Read the ALPS settings; raises :class:`MantelMountError` on failure."""
        return parse_alps_settings(SettingsForm.parse(await self._async_http_get("/device.shtml")))

    async def async_get_device_info(self) -> DeviceInfo:
        """Read the MAC address and host name; raises :class:`MantelMountError` on failure."""
        return parse_device_info(await self._async_http_get("/network.shtml"))

    async def async_set_alps_settings(
        self,
        *,
        enabled: bool | None = None,
        tv_on_threshold: int | None = None,
        tv_off_threshold: int | None = None,
        smooth_start: SmoothStart | None = None,
    ) -> AlpsSettings:
        """
        Change some ALPS settings and return the settings the adapter reports afterwards.

        The form is re-read first and posted back in full, so unspecified settings keep
        their current values. Raises :class:`ValueError` if the resulting on threshold is
        not above the off threshold, and :class:`MantelMountError` if the adapter does
        not apply the change.
        """
        fields = SettingsForm.parse(await self._async_http_get("/device.shtml"))
        if enabled is not None:
            fields["enable_alps"] = "1" if enabled else "0"
        if tv_on_threshold is not None:
            fields["curon"] = str(tv_on_threshold)
        if tv_off_threshold is not None:
            fields["curoff"] = str(tv_off_threshold)
        if smooth_start is not None:
            fields["stabrel"] = str(int(smooth_start))
        requested = parse_alps_settings(fields)
        if requested.tv_on_threshold <= requested.tv_off_threshold:
            raise ValueError("The TV on threshold must be higher than the TV off threshold")
        await self._async_http_post("/save_device.xml", fields)
        applied = await self.async_get_alps_settings()
        if applied != requested:
            raise MantelMountResponseError(f"Adapter reports {applied} after saving {requested}")
        return applied

    async def async_recall_preset(self, preset: int) -> None:
        """
        Move to a stored position; ``0`` is the stowed home position.

        Raises :class:`ValueError` for presets outside ``0..PRESET_COUNT``.
        """
        if not 0 <= preset <= PRESET_COUNT:
            raise ValueError(f"Preset must be between 0 and {PRESET_COUNT}")
        await self._async_exchange(f"MMR{preset}", "MMR")

    async def async_save_preset(self, preset: int) -> None:
        """
        Store the current position as a preset.

        Raises :class:`ValueError` for presets outside ``1..PRESET_COUNT``.
        """
        if not 1 <= preset <= PRESET_COUNT:
            raise ValueError(f"Preset must be between 1 and {PRESET_COUNT}")
        await self._async_exchange(f"MMS{preset}", "MMS")

    async def async_jog(self, direction: Jog) -> None:
        """
        Nudge the mount one step, or stop it with :attr:`Jog.STOP`.

        Unlike other commands a jog is sent once and never retried, because a lost
        acknowledgement would otherwise turn into a second step.
        """
        await self._async_exchange(f"MMJ{int(direction)}", "MMJ", attempts=1)

    async def async_stop(self) -> None:
        """Stop any movement."""
        await self._async_exchange(f"MMJ{int(Jog.STOP)}", "MMJ")

    async def _async_exchange(self, command: str, expected_prefix: str, *, attempts: int | None = None) -> str:
        async with self._lock:
            last_error: MantelMountError = MantelMountTimeoutError(f"No reply to {command}")
            for _ in range(attempts or self._attempts):
                try:
                    reply = await self._async_send_datagram(command)
                except TimeoutError:
                    last_error = MantelMountTimeoutError(f"No reply to {command} from {self.host}")
                    continue
                except (OSError, MantelMountError) as err:
                    last_error = MantelMountError(f"Sending {command} to {self.host} failed: {err}")
                    continue
                if reply.strip().startswith(expected_prefix):
                    return reply.strip()
                last_error = MantelMountResponseError(f"Unexpected reply to {command}: {reply!r}")
            raise last_error

    async def _async_send_datagram(self, command: str) -> str:
        loop = asyncio.get_running_loop()
        transport, protocol = await loop.create_datagram_endpoint(UdpReply, remote_addr=(self.host, self._udp_port))
        try:
            transport.sendto(f"{command}\r".encode("ascii"))
            return await asyncio.wait_for(protocol.reply, self._timeout)
        finally:
            transport.close()

    async def _async_http_get(self, path: str) -> str:
        async with self._lock:
            try:
                async with self._session.get(
                    self.base_url + path, timeout=aiohttp.ClientTimeout(total=self._timeout * 3)
                ) as response:
                    response.raise_for_status()
                    return await response.text(errors="replace")
            except TimeoutError as err:
                raise MantelMountTimeoutError(f"GET {path} from {self.host} timed out") from err
            except aiohttp.ClientError as err:
                raise MantelMountError(f"GET {path} from {self.host} failed: {err}") from err

    async def _async_http_post(self, path: str, fields: dict[str, str]) -> None:
        async with self._lock:
            try:
                async with self._session.post(
                    self.base_url + path, data=fields, timeout=aiohttp.ClientTimeout(total=self._timeout * 3)
                ) as response:
                    response.raise_for_status()
                    await response.read()
            except TimeoutError as err:
                raise MantelMountTimeoutError(f"POST {path} to {self.host} timed out") from err
            except aiohttp.ClientError as err:
                raise MantelMountError(f"POST {path} to {self.host} failed: {err}") from err
