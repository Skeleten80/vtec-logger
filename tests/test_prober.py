from hondadiag import prober, protocols
from hondadiag.elm327 import ELM327

from fake_serial import FakeSerial


def make_factory(*replies):
    fake = FakeSerial("COM1", timeout=0.2)
    fake.queue(*replies)
    return fake, lambda *a, **k: fake


SESSION_REPLIES = ("ELM327 v1.5", "OK", "OK", "OK", "12.4V")  # ATZ + ATE0 ATL0 ATH1 ATRV


def test_run_probe_single_attempt_logs_everything():
    payloads = protocols.GENERIC_PAYLOADS
    replies = list(SESSION_REPLIES) + ["OK"] + ["41 00 FF FF FF FF"] * len(payloads)
    fake, factory = make_factory(*replies)
    records = prober.run_probe(
        "COM1", attempt_names=["iso9141_5baud"], serial_factory=factory,
        timeout=0.2,
    )
    # 5 session records + 1 init + one per payload
    assert len(records) == 5 + 1 + len(payloads)
    assert fake.written[5] == b"ATSP3\r"
    summary = prober.summarize(records)
    assert summary["iso9141_5baud"] == {"sent": len(payloads), "answered": len(payloads)}


def test_summary_ignores_no_data():
    fake, factory = make_factory(*SESSION_REPLIES, "OK", "NO DATA", "41 0C 1A F8")
    records = prober.run_probe(
        "COM1",
        attempt_names=["iso9141_5baud"],
        serial_factory=factory,
        timeout=0.2,
    )
    # Full GENERIC_PAYLOADS ran; only the first two payloads had queued
    # replies, the rest timed out as adapter-errors (not counted as answered).
    summary = prober.summarize(records)
    entry = summary["iso9141_5baud"]
    assert entry["sent"] == len(protocols.GENERIC_PAYLOADS)
    assert entry["answered"] == 1


def test_probe_writes_jsonl(tmp_path):
    out = tmp_path / "probe-test.jsonl"
    fake, factory = make_factory(*SESSION_REPLIES, "OK", "41 0C 1A F8")
    records = prober.run_probe(
        "COM1",
        attempt_names=["iso9141_5baud"],
        out_path=str(out),
        serial_factory=factory,
        timeout=0.2,
    )
    lines = out.read_text().strip().split("\n")
    assert len(lines) == len(records)
    import json

    first = json.loads(lines[0])
    assert first["tx"] == "ATZ"
    assert first["phase"] == "session"


def test_adapter_silence_is_non_fatal():
    fake, factory = make_factory()  # nothing queued: every command fails
    records = prober.run_probe(
        "COM1", attempt_names=["iso9141_5baud"], serial_factory=factory,
        timeout=0.2,
    )
    assert records  # session still logged
    assert all("<adapter-error" in r.rx for r in records)
    assert prober.summarize(records)["iso9141_5baud"]["answered"] == 0


def test_record_json_roundtrip():
    rec = prober.Record(ts=1.5, attempt="x", phase="payload", tx="010C", rx="41 0C 1A F8")
    import json

    assert json.loads(rec.to_json())["rx"] == "41 0C 1A F8"
