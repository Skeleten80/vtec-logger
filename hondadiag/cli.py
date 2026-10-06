"""honda-diag command line interface.

v0.1 is deliberately READ-ONLY: probe the port, read DTCs, read the VIN,
poll live data, query Honda mode $22. There is intentionally NO
code-clear, actuator-test, or reprogramming command -- v0.1 cannot
brick your ECU.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time

from . import __version__, decode, prober, protocols
from .elm327 import ELM327

#: Default protocol hypothesis for the direct commands (2000s Hondas).
DEFAULT_PROTOCOL = "iso9141_5baud"


def _open(port: str, baud: int, serial_factory=None) -> ELM327:
    """One indirection so tests can swap in a fake adapter (monkeypatch)."""
    return ELM327(port, baud=baud, serial_factory=serial_factory)


def _session(port: str, baud: int, attempt_name: str, serial_factory=None):
    """Open the adapter, run session setup + protocol init, return (elm, records)."""
    elm = _open(port, baud, serial_factory)
    records: list[prober.Record] = []

    def log(phase: str, tx: str, rx: str) -> None:
        records.append(
            prober.Record(ts=time.time(), attempt=attempt_name, phase=phase, tx=tx, rx=rx)
        )

    log("session", "ATZ", prober.safe_command(elm, "ATZ", extra_timeout=2.0))
    for cmd in prober.SESSION_SETUP:
        log("session", cmd, prober.safe_command(elm, cmd))
    for cmd in protocols.get_attempt(attempt_name).init:
        log("init", cmd, prober.safe_command(elm, cmd))
    return elm, records


def _ask(elm: ELM327, records: list, attempt_name: str, tx: str) -> str:
    rx = prober.safe_command(elm, tx)
    records.append(
        prober.Record(ts=time.time(), attempt=attempt_name, phase="payload", tx=tx, rx=rx)
    )
    return rx


def _print_exchange(tx: str, rx: str) -> None:
    res = decode.summarize_exchange(tx, rx)
    print(f"{tx} -> {rx[:90]}")
    if res["decoded"]:
        print(f"    decoded: {res['decoded']}")
    if res["note"]:
        print(f"    note: {res['note']}")


def _list_ports(args) -> int:
    try:
        from serial.tools import list_ports
    except ImportError:
        print("pyserial not installed", file=sys.stderr)
        return 1
    found = False
    for port in list_ports.comports():
        print(f"{port.device:20s} {port.description}")
        found = True
    if not found:
        print("no serial ports found")
    return 0


def _probe(args) -> int:
    names = args.attempt if args.attempt else None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = args.out or f"probe-{stamp}.jsonl"
    print(f"honda-diag v{__version__}: probing {args.port} @ {args.baud} baud")
    print("Ignition ON (engine can be off for codes, running for live data).")
    records = prober.run_probe(
        port=args.port,
        baud=args.baud,
        attempt_names=names,
        atma_seconds=args.atma_seconds,
        out_path=out,
    )
    print(f"\nwrote {len(records)} exchanges -> {out}\n")
    summary = prober.summarize(records)
    width = max((len(a.name) for a in protocols.PROBE_ATTEMPTS), default=10)
    for attempt in protocols.PROBE_ATTEMPTS:
        if names and attempt.name not in names:
            continue
        entry = summary.get(attempt.name, {"sent": 0, "answered": 0})
        tag = " [experimental]" if attempt.experimental else ""
        print(f"{attempt.name:<{width}}  {entry['answered']:>2}/{entry['sent']:<2} answered{tag}")
        print(f"{' ' * width}  {attempt.description}")
    print("\nSend the .jsonl log for analysis: raw Honda responses become v0.2 decoders.")
    return 0


def _dtc(args) -> int:
    """Read-only: MIL status, stored DTCs (03), pending DTCs (07)."""
    elm, records = _session(args.port, args.baud, args.protocol)
    try:
        txs = ["0101", "03", "07"]
        for tx in txs:
            _ask(elm, records, args.protocol, tx)
    finally:
        elm.close()
    if args.out:
        prober.append_jsonl(records, args.out)
        print(f"logged -> {args.out}")
    print(f"honda-diag v{__version__}: DTC read on {args.protocol} (read-only, nothing cleared)\n")
    for rec in records:
        if rec.phase == "payload":
            _print_exchange(rec.tx, rec.rx)
    return 0


def _vin(args) -> int:
    """Read-only: mode $09 VIN."""
    elm, records = _session(args.port, args.baud, args.protocol)
    try:
        _ask(elm, records, args.protocol, "0902")
    finally:
        elm.close()
    if args.out:
        prober.append_jsonl(records, args.out)
        print(f"logged -> {args.out}")
    for rec in records:
        if rec.phase == "payload":
            _print_exchange(rec.tx, rec.rx)
    return 0


def _live(args) -> int:
    """Read-only live polling of mode $01 PIDs. Ctrl-C stops."""
    pids = args.pids or list(protocols.LIVE_PIDS)
    elm, records = _session(args.port, args.baud, args.protocol)
    csv_fh = None
    writer = None
    if args.csv:
        csv_fh = open(args.csv, "a", newline="", encoding="utf-8")
        writer = csv.writer(csv_fh)
        writer.writerow(["ts", "pid", "decoded_json"])
    print(f"honda-diag v{__version__}: live polling {len(pids)} PIDs (read-only). Ctrl-C stops.\n")
    try:
        count = 0
        while args.count == 0 or count < args.count:
            stamp = time.strftime("%H:%M:%S")
            line = {"t": stamp}
            for pid in pids:
                rx = _ask(elm, records, args.protocol, pid)
                res = decode.summarize_exchange(pid, rx)
                if res["decoded"]:
                    line.update(res["decoded"])
                if writer:
                    writer.writerow([time.time(), pid, json.dumps(res["decoded"])])
            pairs = "  ".join(f"{k}={v}" for k, v in line.items() if k != "t")
            print(f"[{stamp}] {pairs}")
            count += 1
            if args.interval > 0:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        elm.close()
        if csv_fh:
            csv_fh.close()
    return 0


def _honda22(args) -> int:
    """Raw Honda mode $22 query (experimental). Logged; NOT decoded in v0.1."""
    pid = args.pid.replace(" ", "").upper()
    if len(pid) != 4 or any(c not in "0123456789ABCDEF" for c in pid):
        print("error: --pid must be 4 hex chars, e.g. 0001", file=sys.stderr)
        return 2
    tx = "22" + pid
    elm, records = _session(args.port, args.baud, args.protocol)
    try:
        _ask(elm, records, args.protocol, tx)
    finally:
        elm.close()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = args.out or f"honda22-{stamp}.jsonl"
    prober.append_jsonl(records, out)
    print(f"honda-diag v{__version__}: mode $22 query (experimental, read-only)")
    print(f"logged -> {out}\n")
    for rec in records:
        if rec.phase == "payload":
            _print_exchange(rec.tx, rec.rx)
    return 0


def _decode_log(args) -> int:
    with open(args.log, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("phase") not in ("payload", "monitor"):
                continue
            res = decode.summarize_exchange(rec["tx"], rec["rx"])
            print(f"[{rec['attempt']}] {res['tx']} -> {res['rx'][:90]}")
            if res["decoded"]:
                print(f"    decoded: {res['decoded']}")
            if res["note"]:
                print(f"    note: {res['note']}")
    return 0


def _add_session_args(parser) -> None:
    parser.add_argument("--port", required=True, help="serial port, e.g. /dev/ttyUSB0 or COM3")
    parser.add_argument("--baud", type=int, default=38400, help="adapter baud rate (default 38400)")
    parser.add_argument(
        "--protocol",
        default=DEFAULT_PROTOCOL,
        choices=[a.name for a in protocols.PROBE_ATTEMPTS],
        help=f"protocol init to use (default {DEFAULT_PROTOCOL})",
    )
    parser.add_argument("--out", help="append exchanges to this JSONL log")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="honda-diag",
        description="Free OBD-II diagnostic tool for Honda vehicles on ISO 9141-2 (v0.1: read-only discovery instrument).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ports", help="list serial ports").set_defaults(func=_list_ports)

    probe = sub.add_parser("probe", help="probe the car's diagnostic port, log everything")
    probe.add_argument("--port", required=True, help="serial port, e.g. /dev/ttyUSB0 or COM3")
    probe.add_argument("--baud", type=int, default=38400, help="adapter baud rate (default 38400)")
    probe.add_argument(
        "--attempt",
        action="append",
        choices=[a.name for a in protocols.PROBE_ATTEMPTS],
        help="run only this attempt (repeatable); default: all",
    )
    probe.add_argument("--atma-seconds", type=float, default=5.0)
    probe.add_argument("--out", help="JSONL log path (default probe-<timestamp>.jsonl)")
    probe.set_defaults(func=_probe)

    dtc = sub.add_parser("dtc", help="read MIL status, stored and pending DTCs (read-only)")
    _add_session_args(dtc)
    dtc.set_defaults(func=_dtc)

    vin = sub.add_parser("vin", help="read the VIN via mode $09 (read-only)")
    _add_session_args(vin)
    vin.set_defaults(func=_vin)

    live = sub.add_parser("live", help="poll mode $01 PIDs continuously (read-only)")
    _add_session_args(live)
    live.add_argument(
        "--pids",
        nargs="+",
        default=None,
        help=f"mode $01 payloads to poll (default {len(protocols.LIVE_PIDS)} curated PIDs)",
    )
    live.add_argument("--interval", type=float, default=1.0, help="seconds between polls (default 1.0)")
    live.add_argument("--count", type=int, default=0, help="poll cycles (default 0 = until Ctrl-C)")
    live.add_argument("--csv", help="append decoded rows to this CSV file")
    live.set_defaults(func=_live)

    h22 = sub.add_parser(
        "honda22",
        help="raw Honda mode $22 extended-PID query (experimental, read-only)",
    )
    _add_session_args(h22)
    h22.add_argument("--pid", required=True, help="2-byte Honda PID as hex, e.g. 0001")
    h22.set_defaults(func=_honda22)

    dec = sub.add_parser("decode-log", help="best-effort decode of a probe log")
    dec.add_argument("log", help="JSONL log from a probe run")
    dec.set_defaults(func=_decode_log)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
