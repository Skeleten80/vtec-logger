"""Decoder tests. Expected values are straight SAE J1979 formulas."""

from vteclogger import decode


def ex(tx, rx):
    return decode.summarize_exchange(tx, rx)


def test_rpm():
    assert ex("010C", "41 0C 1A F8")["decoded"] == {"rpm": 1726.0}


def test_speed():
    assert ex("010D", "41 0D 3C")["decoded"] == {"speed_kmh": 60}


def test_coolant_temp():
    assert ex("0105", "41 05 5A")["decoded"] == {"coolant_temp_c": 50}


def test_iat():
    assert ex("010F", "41 0F 46")["decoded"] == {"iat_temp_c": 30}


def test_map():
    assert ex("010B", "41 0B 65")["decoded"] == {"map_kpa": 101}


def test_maf():
    assert ex("0110", "41 10 01 7C")["decoded"] == {"maf_gps": 3.8}


def test_throttle():
    assert ex("0111", "41 11 80")["decoded"] == {"throttle_pct": 50.2}


def test_timing_advance():
    assert ex("010E", "41 0E 80")["decoded"] == {"timing_advance_deg": 0.0}


def test_engine_load():
    assert ex("0104", "41 04 7F")["decoded"] == {"engine_load_pct": 49.8}


def test_fuel_system_status():
    assert ex("0103", "41 03 01 00")["decoded"] == {
        "fuel_system_bank1": "closed loop (O2 feedback)",
        "fuel_system_bank2": "open loop (insufficient engine temp)",
    }


def test_stft_ltft():
    assert ex("0106", "41 06 80")["decoded"] == {"stft_bank1_pct": 0.0}
    assert ex("0107", "41 07 90")["decoded"] == {"ltft_bank1_pct": 12.5}


def test_o2_b1s1():
    assert ex("0114", "41 14 64 80")["decoded"] == {
        "o2_b1s1_v": 0.5,
        "o2_b1s1_stft_pct": 0.0,
    }


def test_supported_pids():
    res = ex("0100", "41 00 FF FF FF FF")["decoded"]
    for pid in ("01", "03", "04", "05", "06", "07", "0B", "0C", "0D", "0E", "0F", "10", "11", "14"):
        assert pid in res["supported_pids_01_20"]
    assert "20" in res["supported_pids_01_20"]


def test_monitor_status_mil():
    assert ex("0101", "41 01 81 07 65 04")["decoded"] == {
        "mil_on": True,
        "dtc_count": 1,
        "monitor_status_raw": "81 07 65 04",
    }


def test_dtc_p2646_p2647():
    # P2646 = 26 46, P2647 = 26 47 in mode $03/$07 framing
    assert decode.decode_dtcs(bytes.fromhex("2646")) == ["P2646"]
    assert decode.decode_dtcs(bytes.fromhex("2647")) == ["P2647"]


def test_dtc_skips_empty_pairs():
    assert decode.decode_dtcs(bytes.fromhex("26460000")) == ["P2646"]


def test_stored_dtcs_exchange():
    assert ex("03", "43 26 46 00 00")["decoded"] == {"stored_dtcs": ["P2646"]}


def test_pending_dtcs_exchange():
    assert ex("07", "47 26 47 00 00")["decoded"] == {"pending_dtcs": ["P2647"]}


def test_vin_decode():
    vin_hex = "1HGCM82633A004352".encode("ascii").hex()
    rx = "49 02 01 " + " ".join(vin_hex[i : i + 2] for i in range(0, len(vin_hex), 2)).upper()
    assert ex("0902", rx)["decoded"] == {"vin": "1HGCM82633A004352"}


def test_mode06_generic_structure():
    data = bytes.fromhex("01 02 03 1122 3344 5566")
    res = decode.decode_mode06(data)
    entry = res["mode06_tests"][0]
    assert entry["tid"] == "01"
    assert entry["oid"] == "02"
    assert entry["unit_scaling_id"] == "03"
    assert "Honda-proprietary" in entry["note"]


def test_mode06_exchange():
    res = ex("0600", "46 01 02 03 1122 3344 5566")["decoded"]
    assert len(res["mode06_tests"]) == 1
    assert res["mode06_tests"][0]["tid"] == "01"


def test_honda_mode22_captured_raw():
    res = ex("2201", "62 01 AA BB CC")
    assert res["decoded"] == {"honda_ext22_raw": "AA BB CC"}
    assert "raw" in res["note"]


def test_unknown_pid_returns_raw():
    assert decode.decode_mode01_pid(0x99, b"\x01\x02") == {"raw": "01 02"}


def test_garbage_never_raises():
    res = ex("010C", "??? not hex ???")
    assert res["decoded"] is None
    assert res["note"]


def test_no_data_note():
    res = ex("010C", "NO DATA")
    assert res["decoded"] is None
    assert "no hex" in res["note"]
