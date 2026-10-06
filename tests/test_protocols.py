import pytest

from hondadiag import protocols


def test_iso9141_tried_first():
    assert protocols.PROBE_ATTEMPTS[0].name == "iso9141_5baud"


def test_probe_order():
    names = [a.name for a in protocols.PROBE_ATTEMPTS]
    assert names == [
        "iso9141_5baud",
        "kwp2000_5baud",
        "kwp2000_fastinit",
        "can11_500k",
        "honda_mode22",
        "bus_monitor",
    ]


def test_iso_attempt_uses_protocol_3():
    assert protocols.get_attempt("iso9141_5baud").init == ("ATSP3",)


def test_can_fallback_uses_protocol_6():
    assert protocols.get_attempt("can11_500k").init == ("ATSP6",)


def test_honda_mode22_is_experimental():
    attempt = protocols.get_attempt("honda_mode22")
    assert attempt.experimental
    assert attempt.payloads == ("2200",)


def test_bus_monitor_flag():
    attempt = protocols.get_attempt("bus_monitor")
    assert attempt.monitor
    assert attempt.payloads == ("ATMA",)


def test_generic_payloads_cover_key_pids():
    for pid in ("010C", "010D", "0105", "0110", "0106", "0107", "03", "07", "0902"):
        assert pid in protocols.GENERIC_PAYLOADS


def test_live_pids_subset_of_generics():
    for pid in protocols.LIVE_PIDS:
        assert pid in protocols.GENERIC_PAYLOADS


def test_get_attempt_unknown_raises():
    with pytest.raises(KeyError):
        protocols.get_attempt("nope")
