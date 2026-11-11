# Attacking ICS Plant #2 CTF Walkthrough

**Target:** Attacking ICS Plant #2
**Source:** [TryHackMe](https://tryhackme.com/room/attackingics2)
**Difficulty:** Medium
**Target IP:** 10.82.147.186

> **Prerequisite:** [Attacking ICS Plant #1](https://tryhackme.com/room/attackingics1) — this room reuses the same `pymodbus`-based discovery/attack scripts (`discovery.py`, `attack_*.py`) introduced there.

## Table of Contents
- [Overview](#overview)
- [Register Targets](#register-targets)
- [Flag #1 — Overflowing the Tank](#flag-1--overflowing-the-tank)
- [Flag #2 — Diverting Oil Through the Waste Water Valve](#flag-2--diverting-oil-through-the-waste-water-valve)
- [Room Answers](#room-answers)
- [Vulnerabilities](#vulnerabilities)
- [Attack Chain Summary](#attack-chain-summary)
- [Tools Used](#tools-used)
- [References](#references)

---

## Overview

Attacking ICS Plant #2 builds directly on Plant #1, moving from a simple
bottle-filling simulation to an oil/water separator process modeled over
the same Modbus TCP interface. Instead of mapping registers from scratch,
the room names each register's PLC tag up front and asks the attacker to
force two distinct unsafe process states purely through direct Modbus
writes: an uncontrolled tank overflow, and a process bypass that routes
oil through the waste water line instead of the separator. Both flags are
retrieved from the plant's web server once the corresponding physical
condition has been sustained long enough to trigger it.

**Key Skills Required:**
- Modbus TCP register discovery (`pymodbus`, reused from Plant #1)
- Mapping named PLC tags to observed register indices
- Timing-based attack execution (sustaining an unsafe state for a set
  duration)
- Retrieving flags served conditionally by the plant's web application

---

## Register Targets

Before attacking the plant, the room identifies the following PLC tags to
be mapped onto registers:

| PLC Tag | Function |
|---|---|
| `PLC_FEED_PUMP` | Open/close the feed pump |
| `PLC_TANK_LEVEL` | Tank level sensor |
| `PLC_OUTLET_VALVE` | Open/close the outlet valve |
| `PLC_SEP_VALVE` | Open/close the separator vessel valve |
| `PLC_OIL_SPILL` | Wasted oil counter |
| `PLC_OIL_PROCESSED` | Processed oil counter |
| `PLC_WASTE_VALVE` | Open/close the waste water valve |

Running the Plant #1 discovery script against the new target confirms 16
registers are again exposed, with the first two immediately identifiable
from how they move during normal operation:

```bash
python3 discovery.py 10.82.147.186
```

```
[1, 0, 0, 0, 0, 15, 1197, 0, 0, 0, 0, 0, 0, 0, 0, 1]
[0, 1, 0, 0, 0, 15, 1197, 0, 0, 0, 0, 0, 0, 0, 0, 1]
[0, 1, 1, 0, 0, 16, 1207, 0, 0, 0, 0, 0, 0, 0, 0, 1]
[0, 0, 0, 0, 0, 16, 1217, 1, 0, 0, 0, 0, 0, 0, 0, 1]
[0, 0, 0, 1, 0, 20, 1516, 1, 0, 0, 0, 0, 0, 0, 0, 1]
```

- **Register 1:** `PLC_FEED_PUMP` — toggles high while the pump is feeding
  oil into the tank.
- **Register 2:** `PLC_TANK_LEVEL` sensor flag — toggles as the tank
  reaches its normal fill threshold.
- **Register 6:** a steadily-climbing counter — tracks tank level/volume
  in finer detail (seen rising from `15` to `20`).
- **Register 7:** a continuously-incrementing counter — matches
  `PLC_OIL_PROCESSED`, climbing in lockstep with register 6.

---

## Flag #1 — Overflowing the Tank

**Objective:** let oil overflow the tank for at least 60 seconds, then
retrieve `flag1.txt`.

The attack opens the feed pump while forcing the outlet valve closed,
guaranteeing oil keeps flowing in with nowhere to drain:

- Set register 1 (`PLC_FEED_PUMP`) to `1`
- Set register 2 (`PLC_OUTLET_VALVE`) to `0`

> Before attacking, reset the simulation with **ESC**. If the flag can't be
> retrieved on the first attempt, reset the room and repeat the attack.

```bash
python3 attack_oil_flow.py 10.82.147.186
```

Running `discovery.py` alongside the attack confirms the sustained unsafe
state — the feed pump stays on, the outlet stays closed, and the tank
counter (register 6/7) climbs continuously without ever draining:

```
[0, 1, 1, 0, 0, 16, 1207, 0, 0, 0, 0, 0, 0, 0, 0, 1]
...
[0, 0, 0, 1, 0, 20, 1516, 1, 0, 0, 0, 0, 0, 0, 0, 1]
```

After maintaining the overflow condition for the required duration, the
flag becomes available:

```bash
curl http://10.82.147.186/flag1.txt
```

```
0df2936b4cfbd5ce3ae91ef7021d925a
```

> **Flag #1:** `0df2936b4cfbd5ce3ae91ef7021d925a`

---

## Flag #2 — Diverting Oil Through the Waste Water Valve

**Objective:** let oil flow through the waste water valve only, until its
counter reaches 2000, then retrieve `flag2.txt`.

This attack forces a different unsafe routing: the feed pump, outlet
valve, and separator vessel valve are all forced open, while the waste
water valve is forced **closed** — misrouting process flow so that oil
ends up counted through the waste path instead of being properly
separated:

- Set registers 1, 3, and 7 to `1` (`PLC_FEED_PUMP`, `PLC_SEP_VALVE`, and
  the waste-routing register)
- Set register 2 to `0` (`PLC_OUTLET_VALVE` held closed)

> As with Flag #1, reset the simulation with **ESC** before starting, and
> reset again if the flag doesn't appear on the first pass.

```bash
python3 attack_water.py 10.82.147.186
```

Once the waste-water counter reaches the 2000 threshold, the flag is
retrievable:

```bash
curl http://10.82.147.186/flag2.txt
```

```
fdee450ac6627276d115dd905a256d49
```

> **Flag #2:** `fdee450ac6627276d115dd905a256d49`

---

## Room Answers

| # | Flag | Value |
|---|------|-------|
| 1 | flag1.txt — sustained tank overflow | `0df2936b4cfbd5ce3ae91ef7021d925a` |
| 2 | flag2.txt — waste-water-only routing | `fdee450ac6627276d115dd905a256d49` |

---

## Vulnerabilities

### 1. Unauthenticated Modbus TCP Access (Critical)

**Description:** As with Plant #1, the Modbus TCP service exposed by this
oil/water separator simulation accepts register reads and writes from any
network-reachable client, with no authentication or integrity checking.

**Impact:** An attacker can force the feed pump, outlet valve, and
separator valve into physically unsafe combinations directly, without
ever touching the plant's HMI or respecting its process safety logic.

**Mitigation:**
- Segregate OT networks running Modbus TCP from any IT-reachable segment
  with dedicated firewalling or a data diode.
- Require authenticated, encrypted transport for any Modbus traffic that
  must cross a trust boundary.

### 2. No Physical Safety Interlocks Enforced Independently of Modbus (High)

**Description:** The simulated process allows the feed pump to remain open
indefinitely with the outlet closed, and allows oil to be routed entirely
through the waste water path, with no independent safety controller
rejecting these states.

**Impact:** Sustained unsafe states lead to tank overflow (environmental/
safety hazard in a real deployment) and product loss through an
unintended waste path — both demonstrated as directly achievable via
Modbus writes alone.

**Mitigation:**
- Implement hard interlocks at the PLC or safety-instrumented-system (SIS)
  level that are independent of the same Modbus channel used for normal
  supervisory control, so a compromised master cannot create physically
  unsafe states.
- Add overflow/high-level alarms and automatic feed-pump cutoffs that
  trigger regardless of the commanded register values.

---

## Attack Chain Summary

```
Prerequisite: Attacking ICS Plant #1 scripts (discovery.py, attack_*.py)
    ↓
python3 discovery.py → confirm 16 registers, map PLC tags to indices
    ↓
Flag #1: force PLC_FEED_PUMP=1, PLC_OUTLET_VALVE=0 (attack_oil_flow.py)
    ↓
Sustain overflow 60+ seconds → curl flag1.txt
    ↓
Reset simulation (ESC)
    ↓
Flag #2: force PLC_FEED_PUMP/PLC_SEP_VALVE/waste-route=1, PLC_OUTLET_VALVE=0 (attack_water.py)
    ↓
Sustain until waste counter reaches 2000 → curl flag2.txt
    ↓
Room complete (Flags 1–2 retrieved)
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| pymodbus (Python library) | Modbus TCP client for reading/writing registers |
| discovery.py | Register enumeration and state observation (from Plant #1) |
| attack_oil_flow.py | Forcing a sustained tank-overflow condition |
| attack_water.py | Forcing an oil/waste-water misrouting condition |
| cURL | Retrieving flags served by the plant's web application |

---

## References

- [TryHackMe — Attacking ICS Plant #2](https://tryhackme.com/room/attackingics2)
- [TryHackMe — Attacking ICS Plant #1 (prerequisite)](https://tryhackme.com/room/attackingics1)
- [NIST SP 800-82 — Guide to Industrial Control Systems (ICS) Security](https://csrc.nist.gov/publications/detail/sp/800-82/rev-2/final)

---
