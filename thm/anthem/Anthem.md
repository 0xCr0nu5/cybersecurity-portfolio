# Anthem CTF Walkthrough

**Target:** Anthem  
**Source:** [TryHackMe](https://tryhackme.com/room/anthem)  
**Difficulty:** Easy  
**Target IP:** 10.113.152.69

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Enumeration](#web-enumeration)
- [robots.txt & Leaked Password](#robotstxt--leaked-password)
- [OSINT: Identifying the Administrator](#osint-identifying-the-administrator)
- [Flag Hunting in Page Source](#flag-hunting-in-page-source)
- [Initial Access via RDP](#initial-access-via-rdp)
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

Anthem is an easy Windows box built around attention to detail rather than
exploitation — no login brute forcing is required, only a browser and Remote
Desktop. The objective is to grab the user and root flags. The chain is an
enumeration and OSINT exercise: `robots.txt` leaks a password, the site's
Umbraco CMS and a Solomon Grundy poem reveal the administrator's name and
(by email pattern) their username, multiple flags are hidden in page source,
and the leaked password grants RDP access as the low-privilege user `sg`.
Privilege escalation comes from a hidden backup file storing the administrator
password in plaintext, reachable after taking ownership/permissions on the file.

**Key Skills Required:**
- Network scanning and service enumeration
- Web enumeration and `robots.txt` inspection
- Identifying a CMS (Umbraco) and site structure
- OSINT / lateral thinking (poem → name → email/username pattern)
- Locating flags hidden in HTML source
- Remote Desktop access (`rdesktop`)
- Windows file permission/ownership manipulation for privilege escalation

---

## Reconnaissance

### Network Scanning

A `-Pn` scan (host blocks ping) shows only two services:

```bash
nmap -Pn -A 10.113.152.69
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 80/tcp | http | Microsoft HTTPAPI httpd 2.0 |
| 3389/tcp | ms-wbt-server | Microsoft Terminal Services (RDP) |

The RDP certificate and NTLM info identify the host as `WIN-LU09299160F`,
running Windows Server 2019 (build 10.0.17763).

> **Q — Web server port:** `80`
> **Q — Remote desktop port:** `3389`

With only a web server and RDP exposed, the plan is clear: enumerate the website
to recover credentials, then log in over RDP.

---

## Web Enumeration

The site is a corporate blog. Inspecting it reveals the CMS and domain:

> **Q — CMS in use:** `umbraco`
> **Q — Website domain:** `Anthem.com`

---

## robots.txt & Leaked Password

`robots.txt` exposes both the Umbraco directory structure and a stray string
that looks like a password:

```bash
curl http://10.113.152.69/robots.txt
```

```
UmbracoIsTheBest!

# Use for all search robots
User-agent: *

# Define the directories not to crawl
Disallow: /bin/
Disallow: /config/
Disallow: /umbraco/
Disallow: /umbraco_client/
```

> **Q — Possible password found by web crawlers:** `UmbracoIsTheBest!`

> **Recovered credential (password):** `UmbracoIsTheBest!`

---

## OSINT: Identifying the Administrator

A blog post at `/archive/a-cheers-to-our-it-department/` contains a poem:

```
Born on a Monday,
Christened on Tuesday,
Married on Wednesday,
Took ill on Thursday,
Grew worse on Friday,
Died on Saturday,
Buried on Sunday.
That was the end…
```

This is the nursery rhyme about **Solomon Grundy** — the administrator's name.

> **Q — Name of the Administrator:** `Solomon Grundy`

The site also lists a user, Jane Doe, whose email is `JD@anthem.com`. Applying
the same initials-based pattern to the admin gives their address:

> **Q — Administrator email:** `SG@anthem.com`

This also reveals the RDP username: `sg`.

---

## Flag Hunting in Page Source

Several flags are hidden in the HTML source of various pages.

**Flag 1 & Flag 2** — homepage / hiring page source:

```html
<meta content="THM{L0L_WH0_US3S_M3T4}" property="og:description" />
<input type="text" name="term" placeholder="Search... THM{G!T_G00D}" />
```

> **Q — Flag 1:** `THM{L0L_WH0_US3S_M3T4}`
> **Q — Flag 2:** `THM{G!T_G00D}`

**Flag 3** — the Jane Doe author page (`/authors/jane-doe/`):

> **Q — Flag 3:** `THM{L0L_WH0_D15}`

**Flag 4** — source of the IT-department post:

```html
<meta content="THM{AN0TH3R_M3TA}" property="og:description" />
```

> **Q — Flag 4:** `THM{AN0TH3R_M3TA}`

---

## Initial Access via RDP

The leaked password works for the `sg` account over Remote Desktop:

```bash
rdesktop -u sg 10.113.152.69
# password: UmbracoIsTheBest!
```

> **Recovered credentials:** `sg : UmbracoIsTheBest!`
> **Foothold:** `sg`

---

## User Flag

The user flag is on the `sg` desktop:

```
C:\Users\SG\Desktop\user.txt
```

> **Q — user.txt:** `THM{N00T_NO0T}`

---

## Privilege Escalation

A hidden backup file holds the administrator password. Enable hidden items
(View → Hidden Items) and browse to:

```
C:\backup\restore
```

The file's security tab shows it has no accessible permissions:

```
Group or user names:
No groups or users have permission to access this object. However, the owner
of this object can assign permissions.
```

Since the current user can take ownership, edit the file's permissions:
**Security → Edit → Add… → "Everyone" → OK → Apply**. The file is then readable:

> **Recovered credentials:** `administrator : ChangeMeBaby1MoreTime`

> **Q — Admin password:** `ChangeMeBaby1MoreTime`

Reconnect over RDP as the administrator:

```bash
rdesktop -u administrator 10.113.152.69
# password: ChangeMeBaby1MoreTime
```

> **Privilege escalation:** `sg` → `administrator`

---

## Root Flag

The root flag is on the administrator's desktop:

> **Q — root.txt:** `THM{Y0U_4R3_1337}`

---

## Flags

| Flag | Value | Location |
|------|-------|----------|
| Flag 1 | `THM{L0L_WH0_US3S_M3T4}` | Homepage source (og:description) |
| Flag 2 | `THM{G!T_G00D}` | Hiring page search placeholder |
| Flag 3 | `THM{L0L_WH0_D15}` | `/authors/jane-doe/` |
| Flag 4 | `THM{AN0TH3R_M3TA}` | IT-department post source |
| User flag | `THM{N00T_NO0T}` | `C:\Users\SG\Desktop\user.txt` |
| Root flag | `THM{Y0U_4R3_1337}` | Administrator desktop |

---

## Vulnerabilities

### 1. Password Disclosure in robots.txt (Critical)

**Description:** A live password (`UmbracoIsTheBest!`) was left in the public
`robots.txt` file, readable by anyone.

**Impact:** Directly provided the credential for RDP foothold as `sg`.

**Mitigation:**
- Never store secrets in `robots.txt` or any client-readable file.
- Treat `robots.txt` as fully public; use real access controls.

### 2. Sensitive Information Disclosure / OSINT Exposure (Medium)

**Description:** The admin's identity was derivable from a themed blog poem, and
their username/email followed a guessable initials pattern (`JD` → `SG`).

**Impact:** Enabled identification of the valid `sg` account for login.

**Mitigation:**
- Avoid predictable username/email schemes.
- Limit identifying content that maps directly to account names.

### 3. Internet-Exposed RDP (High)

**Description:** Remote Desktop (3389) was exposed and accepted password
authentication with a credential leaked elsewhere on the site.

**Impact:** Remote interactive access to the host as `sg`.

**Mitigation:**
- Restrict RDP behind a VPN / IP allowlist; enforce MFA and NLA.
- Use strong, unique credentials and monitor logins.

### 4. Plaintext Admin Credential in Backup File (Critical)

**Description:** The administrator password (`ChangeMeBaby1MoreTime`) was stored
in plaintext in a hidden file at `C:\backup\restore`.

**Impact:** Full privilege escalation to `administrator`.

**Mitigation:**
- Never store plaintext credentials on disk; use a secrets manager.
- Rotate the exposed password and audit backup contents.

### 5. Weak File Permission Model (High)

**Description:** A low-privilege user could take ownership of the backup file and
grant themselves (and "Everyone") read access.

**Impact:** Disclosure of the admin password to a non-privileged user.

**Mitigation:**
- Apply least-privilege ACLs and prevent ownership takeover of sensitive files.
- Encrypt sensitive files at rest.

---

## Attack Chain Summary

```
Nmap scan → 2 open ports (HTTP:80, RDP:3389)
    ↓
robots.txt → password leak: UmbracoIsTheBest! + Umbraco CMS
    ↓
IT-dept blog poem → Solomon Grundy (admin name)
    ↓
email pattern (JD@anthem.com) → SG@anthem.com → username: sg
    ↓
page source → Flags 1-4 (THM{...})
    ↓
rdesktop -u sg → foothold
    ↓
User flag: THM{N00T_NO0T}
    ↓
C:\backup\restore (hidden) → take ownership / add "Everyone"
    ↓
restore file → administrator : ChangeMeBaby1MoreTime
    ↓
rdesktop -u administrator → administrator
    ↓
Root flag: THM{Y0U_4R3_1337}
    ↓
Complete system compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/OS detection |
| cURL / browser | Web enumeration and reading robots.txt |
| Google / OSINT | Identifying the Solomon Grundy poem reference |
| View Source | Locating flags hidden in HTML |
| rdesktop | RDP foothold and administrator access |
| Windows Explorer (ACL editor) | Taking ownership to read the backup file |

---

## References

- [TryHackMe — Anthem](https://tryhackme.com/room/anthem)
- [Nmap](https://nmap.org/)
- [Umbraco CMS](https://umbraco.com/)
- [rdesktop](https://www.rdesktop.org/)
- [Solomon Grundy (nursery rhyme)](https://en.wikipedia.org/wiki/Solomon_Grundy_(nursery_rhyme))
- [robots.txt](https://developers.google.com/search/docs/crawling-indexing/robots/intro)

---
