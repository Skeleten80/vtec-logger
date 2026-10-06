"""Decoders for generic OBD-II responses (v0.1).

Standard SAE J1979 mode $01/$03/$07/$09 formulas only. Honda-proprietary
responses (mode $22, Honda-specific mode $06 test IDs) are passed through
RAW in v0.1 -- decoding tables get built from real probe logs (see
README roadmap).
"""

from __future__ import annotations


def _hex_bytes(text: str) -> bytes:
    cleaned = "".join(text.split())
    if len(cleaned) % 2:
        return b""
    try:
        return bytes.fromhex(cleaned)
    except ValueError:
        return b""


def _find_payload(frame: bytes, mode: int, pid: int | None = None) -> bytes | None:
    """Locate a positive response (mode+0x40, optional PID echo) in a frame."""
    want = bytes([mode + 0x40] + ([pid] if pid is not None else []))
    idx = frame.find(want)
    if idx < 0:
        return None
    return frame[idx + len(want):]


_FUEL_SYS = {
    0: "open loop (insufficient engine temp)",
    1: "closed loop (O2 feedback)",
    2: "open loop (driving conditions)",
    4: "open loop (system fault)",
    8: "closed loop (system fault)",
}


def decode_mode01_pid(pid: int, data: bytes) -> dict:
    """Decode standard mode $01 PIDs. Unknown PIDs return raw bytes."""
    if pid == 0x00 and len(data) >= 4:
        bits = int.from_bytes(data[:4], "big")
        return {
            "supported_pids_01_20": [
                f"{i:02X}" for i in range(1, 33) if bits & (1 << (32 - i))
            ]
        }
    if pid == 0x01 and len(data) >= 4:
        return {
            "mil_on": bool(data[0] & 0x80),
            "dtc_count": data[0] & 0x7F,
            "monitor_status_raw": data[:4].hex(" ").upper(),
        }
    if pid == 0x03 and len(data) >= 2:
        return {
            "fuel_system_bank1": _FUEL_SYS.get(data[0], f"unknown ({data[0]})"),
            "fuel_system_bank2": _FUEL_SYS.get(data[1], f"unknown ({data[1]})"),
        }
    if pid == 0x04 and data:
        return {"engine_load_pct": round(data[0] * 100 / 255, 1)}
    if pid == 0x05 and data:
        return {"coolant_temp_c": data[0] - 40}
    if pid in (0x06, 0x07) and data:
        name = "stft_bank1_pct" if pid == 0x06 else "ltft_bank1_pct"
        return {name: round((data[0] - 128) * 100 / 128, 1)}
    if pid == 0x0B and data:
        return {"map_kpa": data[0]}
    if pid == 0x0C and len(data) >= 2:
        return {"rpm": ((data[0] << 8) | data[1]) / 4}
    if pid == 0x0D and data:
        return {"speed_kmh": data[0]}
    if pid == 0x0E and data:
        return {"timing_advance_deg": round(data[0] / 2 - 64, 1)}
    if pid == 0x0F and data:
        return {"iat_temp_c": data[0] - 40}
    if pid == 0x10 and len(data) >= 2:
        return {"maf_gps": round(((data[0] << 8) | data[1]) / 100, 2)}
    if pid == 0x11 and data:
        return {"throttle_pct": round(data[0] * 100 / 255, 1)}
    if pid == 0x14 and len(data) >= 2:
        return {
            "o2_b1s1_v": round(data[0] / 200, 3),
            "o2_b1s1_stft_pct": round((data[1] - 128) * 100 / 128, 1),
        }
    return {"raw": data.hex(" ").upper()}


def decode_dtcs(data: bytes) -> list[str]:
    """Decode a mode $03 / $07 payload into ['P2646', ...]."""
    codes = []
    for i in range(0, len(data) - 1, 2):
        a, b = data[i], data[i + 1]
        if a == 0 and b == 0:
            continue
        first = "PCBU"[(a >> 6) & 0x03]
        codes.append(f"{first}{a >> 4 & 0x03}{a & 0x0F:X}{(b >> 4):X}{b & 0x0F:X}")
    return codes


def decode_vin(data: bytes) -> dict:
    """Decode a mode $09 PID $02 payload into the 17-char VIN."""
    if data[:1] == b"\x01":  # message-count byte precedes the VIN
        data = data[1:]
    text = "".join(chr(b) for b in data if 32 <= b < 127)
    vin = "".join(c for c in text if c.isalnum())
    if len(vin) >= 17:
        return {"vin": vin[:17]}
    return {"vin_raw": text, "note": "could not extract 17-char VIN"}


def decode_mode06(data: bytes) -> dict:
    """Parse mode $06 generically (J1979 frame structure).

    Per test (9 bytes): TID, OID, unit/scaling ID, min(2), max(2), current(2).
    Honda's TIDs are proprietary -- listed RAW, never interpreted in v0.1.
    """
    tests = []
    for i in range(0, len(data), 9):
        chunk = data[i : i + 9]
        if len(chunk) < 9:
            tests.append({"incomplete": chunk.hex(" ").upper()})
            continue
        tests.append(
            {
                "tid": f"{chunk[0]:02X}",
                "oid": f"{chunk[1]:02X}",
                "unit_scaling_id": f"{chunk[2]:02X}",
                "min_raw": chunk[3:5].hex(" ").upper(),
                "max_raw": chunk[5:7].hex(" ").upper(),
                "current_raw": chunk[7:9].hex(" ").upper(),
                "note": "Honda-proprietary test ID: captured raw (v0.1 does not interpret TIDs)",
            }
        )
    return {"mode06_tests": tests}


def summarize_exchange(tx: str, rx: str) -> dict:
    """Best-effort decode of one probe exchange. Never raises."""
    out: dict = {"tx": tx, "rx": rx, "decoded": None, "note": ""}
    try:
        frame = _hex_bytes(rx)
        if not frame:
            out["note"] = "no hex data in response"
            return out
        tx_b = _hex_bytes(tx)
        if len(tx_b) == 2 and tx_b[0] == 0x01:  # mode 01 + PID
            payload = _find_payload(frame, 0x01, tx_b[1])
            if payload is not None:
                out["decoded"] = decode_mode01_pid(tx_b[1], payload)
                return out
        if tx.strip() == "03":
            payload = _find_payload(frame, 0x03)
            if payload is not None:
                out["decoded"] = {"stored_dtcs": decode_dtcs(payload)}
                return out
        if tx.strip() == "07":
            payload = _find_payload(frame, 0x07)
            if payload is not None:
                out["decoded"] = {"pending_dtcs": decode_dtcs(payload)}
                return out
        if len(tx_b) == 2 and tx_b[0] == 0x09 and tx_b[1] == 0x02:
            payload = _find_payload(frame, 0x09, 0x02)
            if payload is not None:
                out["decoded"] = decode_vin(payload)
                return out
        if tx.strip() == "0600":
            payload = _find_payload(frame, 0x06)
            if payload is not None:
                out["decoded"] = decode_mode06(payload)
                return out
        if len(tx_b) >= 2 and tx_b[0] == 0x22:  # Honda extended
            want = bytes([0x62]) + tx_b[1:3]
            idx = frame.find(want)
            if idx >= 0:
                payload = frame[idx + len(want):]
                out["decoded"] = {"honda_ext22_raw": payload.hex(" ").upper()}
                out["note"] = "Honda proprietary payload: captured raw (v0.1 does not decode)"
                return out
        out["note"] = "unrecognized response format; captured raw"
    except Exception as exc:  # never let a decoder kill a probe session
        out["note"] = f"decoder error (non-fatal): {exc}"
    return out
