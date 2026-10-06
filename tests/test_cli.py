"""CLI tests: every command runs against a fake adapter, zero hardware."""

import json

import pytest

from vteclogger import cli, prober
from vteclogger.elm327 import ELM327

from fake_serial import FakeSerial

# ATZ, ATE0, ATL0, ATH1, ATRV, then the protocol init (ATSP3 by default).
SESSION = ("ELM327 v1.5", "OK", "OK", "OK", "12.4V", "OK")


@pytest.fixture()
def fake_open(monkeypatch):
    """Patch cli._open and prober.ELM327 so commands talk to a fake adapter."""

    def install(*replies):
        fake = FakeSerial("COM1", timeout=0.2)
        fake.queue(*replies)

        def _fake_elm(*a, **k):
            return ELM327(
                "COM1", timeout=0.2, serial_factory=lambda *a2, **k2: fake
            )

        monkeypatch.setattr(
            cli, "_open", lambda port, baud, serial_factory=None: _fake_elm()
        )
        monkeypatch.setattr(prober, "ELM327", _fake_elm)
        return fake

    return install


def test_decode_log(capsys, tmp_path):
    log = tmp_path / "probe.jsonl"
    log.write_text(
        "\n".join(
            json.dumps(r)
            for r in [
                {"ts": 1, "attempt": "iso9141_5baud", "phase": "payload",
                 "tx": "010C", "rx": "41 0C 1A F8"},
                {"ts": 2, "attempt": "honda_mode22", "phase": "payload",
                 "tx": "2200", "rx": "62 00 AA BB"},
                {"ts": 3, "attempt": "iso9141_5baud", "phase": "init",
                 "tx": "ATSP3", "rx": "OK"},
            ]
        )
    )
    assert cli.main(["decode-log", str(log)]) == 0
    out = capsys.readouterr().out
    assert "1726" in out  # RPM decoded
    assert "raw" in out  # mode 22 captured raw
    assert "ATSP3" not in out  # init phase skipped


def test_dtc_command(fake_open, capsys):
    fake_open(*SESSION, "41 01 81 07 65 04", "43 26 46 00 00", "47 00 00")
    assert cli.main(["dtc", "--port", "COM1"]) == 0
    out = capsys.readouterr().out
    assert "P2646" in out
    assert "mil_on" in out
    assert "read-only" in out


def test_dtc_logs_to_out(fake_open, tmp_path):
    out = tmp_path / "dtc.jsonl"
    fake_open(*SESSION, "41 01 00 07 65 04", "43 00 00", "47 00 00")
    assert cli.main(["dtc", "--port", "COM1", "--out", str(out)]) == 0
    lines = out.read_text().strip().split("\n")
    assert any(json.loads(l)["tx"] == "03" for l in lines)


def test_vin_command(fake_open, capsys):
    vin_hex = " ".join(f"{b:02X}" for b in b"1HGCM82633A004352")
    fake_open(*SESSION, f"49 02 01 {vin_hex}")
    assert cli.main(["vin", "--port", "COM1"]) == 0
    assert "1HGCM82633A004352" in capsys.readouterr().out


def test_live_command_count(fake_open, capsys):
    fake_open(*SESSION, "41 0C 1A F8", "41 0C 1B 00")
    assert cli.main(["live", "--port", "COM1", "--pids", "010C",
                     "--count", "2", "--interval", "0"]) == 0
    out = capsys.readouterr().out
    assert out.count("rpm=") == 2


def test_live_writes_csv(fake_open, tmp_path):
    csv_path = tmp_path / "live.csv"
    fake_open(*SESSION, "41 0C 1A F8")
    assert cli.main(["live", "--port", "COM1", "--pids", "010C",
                     "--count", "1", "--interval", "0",
                     "--csv", str(csv_path)]) == 0
    rows = csv_path.read_text().strip().split("\n")
    assert len(rows) == 2  # header + one poll
    assert "rpm" in rows[1]


def test_honda22_command(fake_open, capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fake_open(*SESSION, "62 00 01 AA BB")
    assert cli.main(["honda22", "--port", "COM1", "--pid", "0001"]) == 0
    out = capsys.readouterr().out
    assert "raw" in out
    assert "AA BB" in out
    logs = list(tmp_path.glob("honda22-*.jsonl"))
    assert len(logs) == 1


def test_honda22_rejects_bad_pid(capsys):
    assert cli.main(["honda22", "--port", "COM1", "--pid", "ZZ"]) == 2
    assert "4 hex chars" in capsys.readouterr().err


def test_probe_command(fake_open, capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fake_open(*SESSION, "OK", "NO DATA")  # init + two payloads, rest time out
    rc = cli.main(["probe", "--port", "COM1", "--attempt", "iso9141_5baud",
                   "--out", str(tmp_path / "p.jsonl")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "iso9141_5baud" in out
    assert "answered" in out
