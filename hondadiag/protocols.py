"""Probe attempts: ordered hypotheses about how to wake the ECU.

v0.1 philosophy: we do NOT assume we know the Honda protocol. Each
attempt is one hypothesis (an init sequence + a set of payloads). Every
byte the car sends back -- including silence -- is logged by the prober
for later analysis. Payloads flagged ``experimental`` are
community-reported, not verified; treat their results accordingly.

Order matters: 2000s Hondas (e.g. the 2007 Accord K24A8) predate the
2008 US CAN mandate, so ISO 9141-2 is tried FIRST. The CAN fallback is
kept because it costs one attempt and some late-2007 builds / other
markets may already answer on CAN.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

#: Generic OBD-II payloads tried on every protocol variant.
GENERIC_PAYLOADS: Tuple[str, ...] = (
    "0100",  # supported PIDs 01-20
    "0101",  # monitor status / MIL / DTC count
    "0103",  # fuel system status
    "0104",  # calculated engine load
    "0105",  # coolant temperature
    "0106",  # short-term fuel trim, bank 1
    "0107",  # long-term fuel trim, bank 1
    "010B",  # intake manifold pressure
    "010C",  # engine RPM
    "010D",  # vehicle speed
    "010E",  # timing advance
    "010F",  # intake air temperature
    "0110",  # MAF air flow rate
    "0111",  # throttle position
    "0114",  # O2 sensor, bank 1 sensor 1
    "03",    # stored DTCs
    "07",    # pending DTCs
    "0902",  # VIN
    "0600",  # on-board monitoring test list
)

#: Honda extended mode $22 probes (experimental).
HONDA_EXT22_PAYLOADS: Tuple[str, ...] = (
    "2200",  # supported Honda extended PIDs (analogous to 0100)
)

#: Default PIDs polled by the `live` command (read-only mode $01).
LIVE_PIDS: Tuple[str, ...] = (
    "010C", "010D", "0104", "0105", "0106", "0107",
    "010B", "010E", "010F", "0110", "0111",
)


@dataclass(frozen=True)
class Attempt:
    name: str
    description: str
    init: Tuple[str, ...] = ()
    payloads: Tuple[str, ...] = ()
    experimental: bool = False
    #: If True, the single payload is a bus monitor (ATMA) needing a long read.
    monitor: bool = False


PROBE_ATTEMPTS: Tuple[Attempt, ...] = (
    Attempt(
        name="iso9141_5baud",
        description="ISO 9141-2, 5-baud init (ELM327 protocol 3) + generic OBD-II",
        init=("ATSP3",),
        payloads=GENERIC_PAYLOADS,
    ),
    Attempt(
        name="kwp2000_5baud",
        description="ISO 14230-4 KWP2000, 5-baud init (protocol 4) + generic OBD-II",
        init=("ATSP4",),
        payloads=GENERIC_PAYLOADS,
    ),
    Attempt(
        name="kwp2000_fastinit",
        description="ISO 14230-4 KWP2000, fast init (protocol 5) + generic OBD-II",
        init=("ATSP5",),
        payloads=GENERIC_PAYLOADS,
    ),
    Attempt(
        name="can11_500k",
        description="ISO 15765-4 CAN, 11-bit 500 kbps (protocol 6) fallback + generic OBD-II",
        init=("ATSP6",),
        payloads=GENERIC_PAYLOADS,
    ),
    Attempt(
        name="honda_mode22",
        description="Honda extended mode $22 over K-Line (experimental)",
        init=("ATSP3", "ATH1"),
        payloads=HONDA_EXT22_PAYLOADS,
        experimental=True,
    ),
    Attempt(
        name="bus_monitor",
        description="ATMA bus monitor: capture any ECU chatter for 5 s",
        init=("ATSP3",),
        payloads=("ATMA",),
        monitor=True,
        experimental=True,
    ),
)


def get_attempt(name: str) -> Attempt:
    for attempt in PROBE_ATTEMPTS:
        if attempt.name == name:
            return attempt
    raise KeyError(f"unknown probe attempt: {name!r}")
