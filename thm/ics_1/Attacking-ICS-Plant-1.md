# Attacking ICS Plant #1 CTF Walkthrough

**Target:** Attacking ICS Plant #1
**Source:** [TryHackMe](https://tryhackme.com/room/attackingics1)
**Difficulty:** Easy
**Target IP:** 10.82.173.122

## Table of Contents
- [Overview](#overview)
- [OT/ICS & SCADA Fundamentals](#otics--scada-fundamentals)
- [Modbus Protocol Fundamentals](#modbus-protocol-fundamentals)
- [Discovery — Mapping the Plant's Registers](#discovery--mapping-the-plants-registers)
- [Play to Learn — Identifying the Nozzle Register](#play-to-learn--identifying-the-nozzle-register)
- [Attack — Abusing the Registers](#attack--abusing-the-registers)
- [Room Answers](#room-answers)
- [Vulnerabilities](#vulnerabilities)
- [Attack Chain Summary](#attack-chain-summary)
- [Tools Used](#tools-used)
- [References](#references)

---

## Overview

Attacking ICS Plant #1 is an easy-difficulty introduction to attacking
Operational Technology (OT) using the Modbus TCP protocol against
VirtuaPlant, a simulated bottle-filling plant. Rather than a traditional
foothold-to-root chain, the room walks through black-box Modbus register
discovery, mapping each register to a sensor or actuator by observing
state changes during normal plant operation, and then abusing the
`write_register` function to directly manipulate plant behavior — bypassing
the sensors and logic the plant was designed to respect entirely.

**Key Skills Required:**
- Understanding of OT/ICS and SCADA architecture (HMI, PLC/RTU, SCADA)
- Modbus TCP protocol fundamentals (function codes, register types)
- Python Modbus client scripting (`pymodbus`)
- Black-box register mapping through observation
- Direct register manipulation to override plant behavior

---

## OT/ICS & SCADA Fundamentals

Operational Technology (OT) and Industrial Control Systems (ICS) prioritize
**availability** over confidentiality — unlike traditional IT, where OT
operators have historically had far less security maturity, and ICS
software is built to be fast and reliable first, often at the expense of
being secure.

A SCADA (Supervisory Control and Data Acquisition) deployment is made up
of several components:

- **Supervisory computers / HMI:** gather process data and let operators
  issue commands via mouse, keyboard, or touchscreen.
- **PLCs (Programmable Logic Controllers):** digital computers that
  continuously monitor sensors and control actuators for local automation.
- **RTUs (Remote Terminal Units):** functionally overlap with PLCs, but
  preferred for wider geographic telemetry.
- **Communication network:** links all SCADA components (Ethernet, serial,
  radio, cellular); PLCs/RTUs are designed to operate autonomously on
  their last known instruction if the network fails.

Because an HMI can override plant behavior through simple input devices,
any malicious software that can reach the same control surface can do the
same thing — this is the core premise the room builds toward.

---

## Modbus Protocol Fundamentals

Modbus, originally developed by Modicon (now Schneider Electric), is a
royalty-free, widely-deployed industrial master/slave protocol. Modbus TCP
encapsulates Modbus RTU request/response packets over standard Ethernet,
listening on **TCP port 502**.

Modbus register types:

| Register | Size | Access |
|----------|------|--------|
| Discrete Input (Status Input) | 1 bit | Read-only |
| Coil (Discrete Output) | 1 bit | Read/Write |
| Input Register | 16 bit | Read-only |
| Holding Register | 16 bit | Read/Write |

Common Modbus function codes:

| Function Code | Register Type |
|---|---|
| 1 | Read Coil |
| 2 | Read Discrete Input |
| 3 | Read Holding Registers |
| 4 | Read Input Registers |
| 5 | Write Single Coil |
| 6 | Write Single Holding Register |
| 15 | Write Multiple Coils |
| 16 | Write Multiple Holding Registers |

```bash
pip3 install pymodbus==1.5.2
```

> **Q1 — function to read holding registers in pymodbus:** `read_holding_registers` (see `discover.py`)
> **Q2 — function to write holding registers in pymodbus:** `write_register` (see `set_register.py`)

---

## Discovery — Mapping the Plant's Registers

Connecting to the plant's web interface (`http://10.82.173.122`) reveals a
bottle-filling process with three repeating phases:

1. **Initialization:** the roller moves the first bottle under the nozzle.
2. **Filling:** once a bottle is in place, the nozzle opens and fills it.
3. **Moving:** once filled, the roller advances the next empty bottle,
   then the cycle returns to phase 2.

Two sensors and three actuators are observed:

- **Sensors:** water level (red), bottle presence (green).
- **Actuators:** start/stop control, roller motor, nozzle valve.

> **Q3 — phases observed:** `3` (initialization, filling, moving)
> **Q4 — sensors observed:** `2` (red level sensor, green presence sensor)
> **Q5 — actuators observed:** `3` (start/stop control, roller motor, nozzle valve)

### Running discover.py

```bash
python3 discovery.py 10.82.173.122
```

```
[1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1]
[1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1]
[0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1]
[0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1]
```

> **Q6 — register count:** `16` (all arrays returned 16 values)
> **Q7 — registers continuously changing after start:** `4` (registers 1, 2, 3, 4)
> **Q8 — minimum observed value:** `0`
> **Q9 — maximum observed value:** `1`
> **Q10 — register that holds its value constant:** `16` — this corresponds to the plant's start/stop control; it only changes when an operator (or attacker) manually toggles the plant.
> **Q11 — registers set to 1 while filling:** `2` and `4`
> **Q12 — registers set to 1 while the roller is moving bottles:** `1` and `3`
> **Q13 — color of the water level sensor:** `red`
> **Q14 — color of the bottle sensor:** `green`
> **Q15 — register associated with the roller at plant start:** `3` (activates immediately as the roller motor engages)
> **Q16 — register associated with the water level sensor:** `1`

From these observations a working model emerges:

- 16 registers are exposed, but only 5 are meaningfully used.
- Register 16: start/stop button (`1` = on, `0` = off).
- Registers 1 and 3 usually match, except during initialization.
- Registers 2 and 4 always match each other.

---

## Play to Learn — Identifying the Nozzle Register

With registers 2 and 4 still ambiguous as nozzle vs. bottle-position, the
`set_registry.py` script is used to force each candidate register directly
and observe the plant's reaction on the web page:

```bash
python3 set_registry.py 10.82.173.122 4 1
```

Forcing register 4 to `1` immediately opens the nozzle regardless of
whether a bottle is actually in position — confirming it controls the
nozzle actuator.

> **Q17 — register associated with the nozzle:** `4`

This resolves the full register map:

| Register | Meaning | Value 1 means |
|---|---|---|
| 1 | Bottle sensor | Bottle is under the nozzle |
| 2 | Water level sensor | Bottle is filled |
| 3 | Roller actuator | Roller is on |
| 4 | Nozzle actuator | Nozzle is open |
| 16 | Plant control | Plant is started |

---

## Attack — Abusing the Registers

With the full register map in hand, the plant's logic can be bypassed
entirely by writing arbitrary values directly to the exposed Modbus
registers — something the plant's physical sensors were never designed to
defend against. The room provides several ready-made attack scripts to
demonstrate different abuse scenarios against the running plant:

```
attack_move_fill2.py
attack_move_fill.py
attack_shutdown2.py
attack_shutdown.py
attack_stop_fill2.py
attack_stop_fill.py
```

Running each against the target and observing the web page shows the
plant manager will shut the process down if it detects an abnormal
condition (for example, the nozzle open with no bottle present, or the
roller and nozzle both active simultaneously), but a carefully-timed write
can still desynchronize sensors from actuators — overflowing bottles,
running the roller into a filling station, or forcing an unexpected
shutdown — all without ever touching the plant's physical controls.

---

## Room Answers

| # | Question | Answer |
|---|----------|--------|
| Q1 | pymodbus function to read holding registers | `read_holding_registers` |
| Q2 | pymodbus function to write holding registers | `write_register` |
| Q3 | Phases observed | `3` |
| Q4 | Sensors observed | `2` |
| Q5 | Actuators observed | `3` |
| Q6 | Register count (discovery.py) | `16` |
| Q7 | Registers continuously changing | `4` |
| Q8 | Minimum observed value | `0` |
| Q9 | Maximum observed value | `1` |
| Q10 | Register holding a constant value | `16` |
| Q11 | Registers set to 1 while filling | `2`, `4` |
| Q12 | Registers set to 1 while roller moves bottles | `1`, `3` |
| Q13 | Color of the water level sensor | `red` |
| Q14 | Color of the bottle sensor | `green` |
| Q15 | Register associated with the roller | `3` |
| Q16 | Register associated with the water level sensor | `1` |
| Q17 | Register associated with the nozzle | `4` |

---

## Vulnerabilities

### 1. Unauthenticated Modbus TCP Access (Critical)

**Description:** The Modbus TCP service (port 502) accepts reads and
writes from any client with network access, with no authentication,
encryption, or integrity checking — a design characteristic of the Modbus
protocol itself rather than a specific misconfiguration.

**Impact:** Any network-adjacent attacker can read the complete process
state and write arbitrary values to any coil or holding register,
bypassing all physical sensor logic.

**Mitigation:**
- Never expose Modbus TCP directly to untrusted or IT-side networks;
  isolate OT networks with dedicated firewalls/data diodes.
- Where Modbus must traverse untrusted segments, wrap it in an
  authenticated, encrypted tunnel (e.g., a VPN) and use network-level
  allow-listing for authorized master devices only.

### 2. No Sanity Checking on Actuator State Combinations (Medium)

**Description:** Individual registers (e.g., the nozzle) can be forced
into physically inconsistent states (open with no bottle present)
directly via Modbus writes, with only a reactive shutdown if the "plant
manager" logic detects an anomaly after the fact.

**Impact:** Process disruption, potential physical damage or product loss
(overflow, misaligned filling) before any safety shutdown engages.

**Mitigation:**
- Implement interlocks at the PLC level that reject physically impossible
  actuator combinations regardless of the write source.
- Treat anomaly detection as a secondary control, not a substitute for
  access control on the primary read/write channel.

---

## Attack Chain Summary

```
Browser recon → http://10.82.173.122 → observe 3-phase bottle-filling process
    ↓
pip install pymodbus → discovery.py → 16 registers enumerated
    ↓
Observe register deltas across phases → map registers 1–4 to sensors/actuators
    ↓
set_registry.py → force register 4 → confirms nozzle actuator
    ↓
Full register map resolved (1: bottle, 2: water level, 3: roller, 4: nozzle, 16: plant control)
    ↓
attack_*.py scripts → direct register writes → plant logic bypassed
    ↓
Room complete (Q1–Q17 answered)
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| pymodbus (Python library) | Modbus TCP client for reading/writing registers |
| discovery.py | Register enumeration and state observation |
| set_registry.py | Forcing individual register values to confirm their function |
| attack_*.py scripts | Demonstrating process-disruption attacks via register writes |
| Web browser | Observing plant state via the VirtuaPlant HMI |

---

## References

- [TryHackMe — Attacking ICS Plant #1](https://tryhackme.com/room/attackingics1)
- [NIST SP 800-82 — Guide to Industrial Control Systems (ICS) Security](https://csrc.nist.gov/publications/detail/sp/800-82/rev-2/final)
- [VirtuaPlant (GitHub)](https://github.com/ayusopo/virtuaplant)
- [Modbus 101 — Introduction to Modbus](https://www.csimn.com/CSI_pages/Modbus101.html)

---
