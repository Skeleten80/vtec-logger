# vtec-logger

Free, open-source OBD-II diagnostic tooling for Honda vehicles on
**ISO 9141-2 K-Line** — e.g. a 2007 Honda Accord with the K24A8 2.4L
i-VTEC (7th gen), whose ECU predates the 2008 US CAN mandate.

## Honest status: v0.1 is a discovery instrument

Honda's proprietary diagnostics (mode `$22` extended PIDs, Honda-specific
mode `$06` test IDs) are only *partially* documented by the enthusiast
community. v0.1 does not pretend to decode them. Instead it:

1. Probes the diagnostic port with every init sequence the community knows
   (ISO 9141-2 5-baud init **first**, KWP2000 variants, CAN fallback,
   Honda extended mode `$22`, bus monitor),
2. Logs **every byte** exchanged to a timestamped JSONL file,
3. Decodes whatever *generic* OBD-II the ECU happens to speak (RPM, speed,
   fuel trims, coolant, MAF, O2, stored + pending DTCs, VIN…),
4. Captures Honda-proprietary responses **raw** so decoding tables can be
   built from real logs.

**v0.1 is deliberately read-only.** There is no code-clear, actuator-test,
or reprogramming command. It cannot brick your ECU.

## Hardware

- Any ELM327-compatible adapter (USB recommended; Bluetooth/Wi-Fi also work
  if they expose a serial port).
- **Get a v1.5 clone, not v2.1.** The v2.1 clones are notorious for broken
  firmware that lies about supported AT commands. (~$15–25.)
- The car's DLC: under the driver's side dash, next to the kick panel.
  K-Line is pin 7. Ignition ON; engine can be off for codes, running for
  live data.

## Install

```bash
cd vtec-logger
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Usage

```bash
# find the adapter's serial port
.venv/bin/vtec-logger ports

# probe everything, log to probe-<timestamp>.jsonl
.venv/bin/vtec-logger probe --port /dev/ttyUSB0

# probe only one attempt
.venv/bin/vtec-logger probe --port /dev/ttyUSB0 --attempt iso9141_5baud

# read MIL status + stored + pending DTCs (read-only)
.venv/bin/vtec-logger dtc --port /dev/ttyUSB0

# read the VIN
.venv/bin/vtec-logger vin --port /dev/ttyUSB0

# poll live data (10 polls, 1 s apart, also to CSV)
.venv/bin/vtec-logger live --port /dev/ttyUSB0 --count 10 --csv live-20261006.csv

# raw Honda mode $22 query (experimental, logged, not decoded)
.venv/bin/vtec-logger honda22 --port /dev/ttyUSB0 --pid 0001

# best-effort decode of a saved log
.venv/bin/vtec-logger decode-log probe-20261006-120000.jsonl
```

Probe attempts:

| attempt | what it tries |
|---|---|
| `iso9141_5baud` | ISO 9141-2, 5-baud init (ELM327 protocol 3) + generic OBD-II |
| `kwp2000_5baud` | KWP2000, 5-baud init (protocol 4) + generic OBD-II |
| `kwp2000_fastinit` | KWP2000, fast init (protocol 5) + generic OBD-II |
| `can11_500k` | CAN 11-bit 500 kbps (protocol 6) fallback + generic OBD-II |
| `honda_mode22` *(experimental)* | Honda extended mode `$22` over K-Line |
| `bus_monitor` *(experimental)* | `ATMA`: capture any ECU chatter for 5 s |

The `probe` command prints a per-attempt hit summary (`answered/sent`).
**Send the `.jsonl` log back for analysis** — real Honda responses in it
are what v0.2 decoders get built from.

Generic mode `$01` PIDs decoded in v0.1: supported-PID map, monitor
status/MIL, fuel system status, engine load, coolant temp, STFT/LTFT bank 1,
MAP, RPM, vehicle speed, timing advance, IAT, MAF, throttle position, and
O2 bank 1 sensor 1 (voltage + STFT).

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

All hardware access is behind an injectable serial factory (and a
monkeypatchable `_open` in the CLI); the suite runs with zero hardware
attached.

## Roadmap

- **v0.2** — decode tables for Honda mode `$22` responses, built from real probe logs
- **v0.3** — smarter `live`: Honda-specific PIDs once decoded + alert thresholds
- **v0.4** — DTC read/clear as explicit, confirmed user actions (never automatic)

## Protocol notes

- Physical layer: ISO 9141-2, 10.4 kbaud, K-Line on DLC pin 7.
- Init: 5-baud init (ELM327 protocol 3) or KWP2000 variants (protocols
  4/5). The ELM327 handles the timing.
- Generic payloads use standard SAE J1979 mode `$01`/`$03`/`$07`/`$09` framing.
- Honda extended diagnostics (mode `$22`) use proprietary PID layouts;
  v0.1 captures them raw.

## Verified facts (2007 Honda Accord, K24A8)

Everything below was confirmed via web search on 2026-10-06. Anything
that could not be confirmed is listed separately as UNVERIFIED rather
than guessed.

- **OBD-II protocol is ISO 9141-2 K-Line** (pin 7, 10.4 kbps, 5-baud
  init), not CAN. CAN was only mandated for US-market vehicles from
  model year 2008; protocol tables list Honda/Acura as ISO 9141 through
  the pre-2008 years. ([SparkFun/Digi-Key OBD-II guide](https://www.digikey.tw/htmldatasheets/production/1844671/0/0/1/obd-ii-getting-started.html),
  [OBD2 protocol table](https://offroad-bulgaria.com/filedata/fetch?id=5144780))
- **DLC location:** under the driver's side dash, next to the kick panel.
  ([answers.com](https://www.answers.com/asian-cars/Where_is_the_OBD_port_on_a_2000_Honda_Accord))
- **Engine:** K24A8 2.4L i-VTEC — 166 hp, 160 lb-ft.
  ([autofiles.com](https://autofiles.com/oil-capacity/honda/accord/))
- **VTEC engagement** on the economy i-VTEC K24A4/A8 is load- and
  rpm-dependent; owners observe the change around ~2,200–2,500 rpm (no
  hard "kick" like performance VTEC).
  ([driveaccord.net](https://www.driveaccord.net/threads/my-vtec-is-not-working.3801/page-2?post_id=492542),
  [JustAnswer mechanic](https://www.justanswer.com/honda/itvk3-p2467-2007-accord-2-4l-k24a8-170000-p2646.html))
- **P2646** = "A" Rocker Arm Actuator System Performance/Stuck Off (VTEC
  stuck off); **P2647** = VTEC system stuck ON. Honda service bulletin
  13-021 (covers 2003–2012 Accord L4) attributes intermittent
  P2646/P2647 to the rocker arm oil pressure switch; corrective action is
  replacing the switch (**37250-PNE-G01**) plus O-ring (**91319-PAA-A01**).
  ([CarBuzz](https://CarBuzz.com/p2646-honda-error-code/),
  [Honda SB 13-021](https://static.oemdtc.com/NHTSA-PDFs/SB-10098946-5233.pdf))
- **Spark plugs:** NGK **IZFR6K13** (NGK stock #6774), Laser Iridium —
  the OE plug for the 2003–2007 Accord 2.4L.
  ([1aauto](https://www.1aauto.com/honda-accord-fit-4-piece-laser-iridium-spark-plug-set-ngk-ngetk00079/i/ngetk00079),
  [PartSource Canada](https://partsource.ca/products/izfr6k13-ngk-laser-iridium-spark-plug-1-pk?bvstate=pg:3/ct:r))
- **Valve clearance (cold):** intake 0.008–0.010 in (0.21–0.25 mm),
  exhaust 0.011–0.013 in (0.28–0.32 mm). Honda recommends checking at
  ~110k-mile intervals.
  ([EricTheCarGuy K-series guide](https://www.youtube.com/watch?v=959I0wF5NH8),
  [Honda Element K24 valve guide](https://www.scribd.com/document/759101663/Honda-ELEMENT-Valve-Clearance-Adjustement))
- **Engine oil:** SAE 5W-20 (all temps), 4.4 qt / 4.2 L with filter.
  ([AMSOIL lookup](https://www.amsoil.ca/lookup/auto-and-light-truck/2007/honda/accord/2-4l-4-cyl-engine-code-k24a8-8/))
- **Automatic transmission fluid:** Honda **ATF DW-1** (supersedes the
  older ATF-Z1). Honda recommends drain-and-fill service (no machine
  flush); owners typically do ~3–3.75 qt per drain.
  ([BobIsTheOilGuy](https://bobistheoilguy.com/forums/threads/2007-honda-accord.221406/),
  [tpautorepair](https://tpautorepair.net/what-transmission-fluid-for-honda-accord/))

### UNVERIFIED (could not be confirmed; do not treat as fact)

- The exact factory VTEC crossover rpm for the K24A8 — only
  community-observed ranges (~2,200–2,500 rpm) were found; Honda
  publishes no single figure for the economy i-VTEC.
- The exact spark plug gap for a specific trim — parts catalogs list
  0.044 in (federal) vs 0.052 in (California/SULEV) variants. Check the
  under-hood emissions label.
- Whether a 2007 Accord ECU answers Honda mode `$22` at all (marked
  experimental in this tool; the probe log will tell).
- Exact ATF drain quantity per drain-and-fill (one source says ~3.75 qt;
  measure what comes out).

## License

MIT.
