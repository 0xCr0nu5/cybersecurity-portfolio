# Momentum-1 CTF - Complete Walkthrough

## Overview

**VM Name:** Momentum: 1  
**Source:** [VulnHub](https://www.vulnhub.com/entry/momentum-1,685/)  
**Difficulty:** Easy-Medium  
**Objective:** Capture two flags (user and root)

This CTF challenges participants to discover encrypted credentials through web enumeration, exploit an insecure Redis configuration, and perform privilege escalation to achieve root access.

---

## Table of Contents

1. [Reconnaissance](#1-reconnaissance)
2. [Web Application Analysis](#2-web-application-analysis)
3. [Credential Discovery](#3-credential-discovery)
4. [Initial Access](#4-initial-access)
5. [Service Enumeration](#5-service-enumeration)
6. [Privilege Escalation](#6-privilege-escalation)
7. [Flags](#7-flags)

---

## 1. Reconnaissance

### Network Scanning

Initial network discovery using Nmap to identify the target and enumerate services:

```bash
nmap -sS -sV -A -p- 10.0.2.239
```

**Key Findings:**

| Port | State | Service | Version |
|------|-------|---------|---------|
| 22   | Open  | SSH     | OpenSSH 7.9p1 Debian |
| 80   | Open  | HTTP    | Apache httpd 2.4.38 (Debian) |

**Target IP:** `10.0.2.239`

**Notable Observations:**
- Standard SSH and HTTP services exposed
- Both services running on Debian-based system
- Web server will be the primary attack surface

### Web Vulnerability Scan

```bash
nikto -h http://10.0.2.239
```

**Significant Discoveries:**
- Apache 2.4.38 (outdated version)
- Directory indexing enabled on `/css/` and `/img/`
- Missing security headers:
  - X-Frame-Options
  - X-Content-Type-Options
- `/manual/` directory accessible
- No robots.txt file found

---

## 2. Web Application Analysis

### Directory Enumeration

Using Gobuster to discover hidden directories and files:

```bash
gobuster dir -u http://10.0.2.239/ \
  -w /usr/share/wordlists/dirbuster/directory-list-2.3-medium.txt \
  -x .php,.html,.js,.bak,.txt
```

**Discovered Resources:**

| Path | Status | Type |
|------|--------|------|
| index.html | 200 | Static page |
| /img/ | 301 | Directory |
| /css/ | 301 | Directory |
| /js/ | 301 | Directory |
| /manual/ | 301 | Directory |

### Source Code Analysis

Examining the main page for hidden information:

```bash
curl http://10.0.2.239/
# Alternative: view-source:http://10.0.2.239/
```

**HTML Structure:**
```html
<head>
    <link rel="stylesheet" type="text/css" href="css/style.css">
    <script type="text/javascript" src="js/main.js"></script>
    <title>Momentum | Index </title>
</head>
```

The HTML source references a JavaScript file that may contain interesting logic.

### JavaScript File Analysis

Retrieving and analyzing the JavaScript file:

```bash
curl http://10.0.2.239/js/main.js
```

**Critical Findings in main.js:**

```javascript
function viewDetails(str) {
    window.location.href = "opus-details.php?id="+str;
}

/*
var CryptoJS = require("crypto-js");
var decrypted = CryptoJS.AES.decrypt(encrypted, "SecretPassphraseMomentum");
console.log(decrypted.toString(CryptoJS.enc.Utf8));
*/
```

**Key Discoveries:**
1. **PHP Endpoint:** `opus-details.php` (potential SQL injection or LFI target)
2. **Commented Code:** Reveals AES decryption implementation
3. **Encryption Passphrase:** `SecretPassphraseMomentum`
4. **Encryption Library:** CryptoJS (AES algorithm)

This is a major information disclosure vulnerability - the decryption key is exposed in client-side code!

---

## 3. Credential Discovery

### Browser Cookie Inspection

Opening browser developer tools to examine stored cookies:

**Steps:**
1. Open Developer Tools (F12)
2. Navigate to Console tab
3. Execute: `document.cookie`

**Output:**
```
cookie=U2FsdGVkX193yTOKOucUbHeDp1Wxd5r7YkoM8daRtj0rjABqGuQ6Mx28N1VbBSZt
```

The cookie value appears to be Base64-encoded encrypted data.

### AES Decryption

Using the passphrase discovered in the JavaScript file to decrypt the cookie:

**Decryption Options:**

1. **Online Tool:** https://www.browserling.com/tools/aes-decrypt
2. **CryptoJS Library (Browser Console)**
3. **Node.js Script**

**Decryption Parameters:**
- **Encrypted Text:** `U2FsdGVkX193yTOKOucUbHeDp1Wxd5r7YkoM8daRtj0rjABqGuQ6Mx28N1VbBSZt`
- **Passphrase:** `SecretPassphraseMomentum`
- **Algorithm:** AES

**Decrypted Output:**
```
auxerre-alienum##
```

### Credential Interpretation

Based on common CTF patterns and web enumeration context:

**Credentials Obtained:**
- **Username:** `auxerre`
- **Password:** `auxerre-alienum##`

The username "auxerre" likely corresponds to a system user account, and the password follows a pattern that suggests it's meant for SSH authentication.

---

## 4. Initial Access

### SSH Connection

Attempting SSH authentication with the discovered credentials:

```bash
ssh auxerre@10.0.2.239
```

**Login Prompt:**
```
auxerre@10.0.2.239's password: auxerre-alienum##
```

**Successful Connection:**
```bash
auxerre@Momentum:~$ whoami
auxerre

auxerre@Momentum:~$ pwd
/home/auxerre
```

### User Flag Capture

Listing files in the home directory:

```bash
auxerre@Momentum:~$ ls -l
total 4
-rwx------ 1 auxerre auxerre 146 Apr 22  2021 user.txt
```

Reading the user flag:

```bash
auxerre@Momentum:~$ cat user.txt
```

**Flag 1 Content:**
```
[ Momentum - User Owned ]
---------------------------------------
flag : 84157165c30ad34d18945b647ec7f647
---------------------------------------
```

**FLAG 1:** `84157165c30ad34d18945b647ec7f647` 

---

## 5. Service Enumeration

### Identifying Listening Services

Checking for services running on localhost that aren't exposed externally:

```bash
auxerre@Momentum:~$ ss -tlnp
```

**Output:**
```
State    Recv-Q   Send-Q   Local Address:Port    Peer Address:Port
LISTEN   0        128            0.0.0.0:22           0.0.0.0:*
LISTEN   0        128          127.0.0.1:6379         0.0.0.0:*
LISTEN   0        128                  *:80                 *:*
LISTEN   0        128               [::]:22              [::]:*
LISTEN   0        128              [::1]:6379            [::]:*
```

**Critical Discovery:**
- **Port 6379** - Redis database running on localhost
- Service bound to 127.0.0.1 (local-only access)
- Redis is an in-memory key-value database often used for caching and session storage

**Security Implication:**
Redis running without authentication on localhost represents "security through obscurity" - once an attacker gains local access, the database becomes accessible.

---

## 6. Privilege Escalation

### Redis Database Exploitation

#### Connecting to Redis

```bash
auxerre@Momentum:~$ redis-cli
127.0.0.1:6379>
```

No authentication required - the Redis server is completely open!

#### Database Enumeration

Listing all keys stored in the database:

```bash
127.0.0.1:6379> KEYS *
1) "rootpass"
```

**Critical Finding:**
A key named `rootpass` exists in the database - this is a strong indicator that it contains the root account password.

#### Credential Extraction

Retrieving the value of the `rootpass` key:

```bash
127.0.0.1:6379> GET "rootpass"
"m0mentum-al1enum##"
```

**Root Password Obtained:** `m0mentum-al1enum##`

The password is stored in **plain text** with no encryption or hashing - a severe security vulnerability.

#### Exiting Redis

```bash
127.0.0.1:6379> exit
```

### Switching to Root User

Using the extracted password to escalate privileges:

```bash
auxerre@Momentum:~$ su -l
Password: m0mentum-al1enum##
```

**Verifying Root Access:**

```bash
root@Momentum:~# whoami
root

root@Momentum:~# id
uid=0(root) gid=0(root) groups=0(root)

root@Momentum:~# pwd
/root
```

Complete system compromise achieved! 

### Root Directory Enumeration

```bash
root@Momentum:~# ls -la
total 28
drwx------  3 root root 4096 Apr 22  2021 .
drwxr-xr-x 18 root root 4096 Jun 28  2020 ..
-rw-------  1 root root    0 Apr 22  2021 .bash_history
-rw-r--r--  1 root root  570 Jan 31  2010 .bashrc
drwxr-xr-x  3 root root 4096 Jun 28  2020 .local
-rw-r--r--  1 root root  148 Aug 17  2015 .profile
-rwx------  1 root root  150 Apr 22  2021 root.txt
```

### Root Flag Capture

```bash
root@Momentum:~# cat root.txt
```

**Flag 2 Content:**
```
[ Momentum - Rooted ]
---------------------------------------
Flag : 658ff660fdac0b079ea78238e5996e40
---------------------------------------
by alienum with <3
```

**FLAG 2:** `658ff660fdac0b079ea78238e5996e40` 

---

## 7. Flags

| Flag | Location | Value |
|------|----------|-------|
| User Flag | `/home/auxerre/user.txt` | `84157165c30ad34d18945b647ec7f647` |
| Root Flag | `/root/root.txt` | `658ff660fdac0b079ea78238e5996e40` |

---

## Key Takeaways

### Vulnerabilities Exploited

#### 1. Information Disclosure via Client-Side Code
**Issue:**
- Encryption algorithm and passphrase exposed in JavaScript comments
- Source code revealed sensitive implementation details
- No obfuscation or protection of client-side secrets

**Lesson:**
Never include sensitive information (passwords, encryption keys, API tokens) in client-side code. Attackers can easily view and extract this data.

#### 2. Insecure Credential Storage in Cookies
**Issue:**
- User credentials stored in browser cookies
- Weak encryption with hardcoded passphrase
- Passphrase discoverable through source code analysis

**Lesson:**
- Cookies should never store passwords or sensitive authentication data
- Use secure session tokens with HttpOnly and Secure flags
- Implement server-side session management

#### 3. Insecure Redis Configuration
**Issue:**
- Redis accessible without authentication
- Sensitive credentials stored in plain text
- No access controls or password protection
- "Security through obscurity" (localhost binding only)

**Lesson:**
- Always enable Redis authentication (`requirepass` directive)
- Encrypt sensitive data before storage
- Use Redis ACLs for fine-grained access control
- Never rely solely on network restrictions for security

#### 4. Credential Reuse & Weak Password Management
**Issue:**
- Root password stored in accessible database
- No password hashing or salting
- Direct root access via `su` command enabled

**Lesson:**
- Never store passwords in plain text
- Use strong hashing algorithms (bcrypt, Argon2, scrypt)
- Implement principle of least privilege
- Use `sudo` instead of direct root login

#### 5. Missing Security Headers
**Issue:**
- X-Frame-Options not set (clickjacking vulnerability)
- X-Content-Type-Options missing
- No Content Security Policy (CSP)

**Lesson:**
Implement comprehensive security headers to protect against common web attacks.

---

## Attack Chain Summary

```
Initial Reconnaissance (Nmap)
    ↓
Web Service Discovery (Port 80)
    ↓
Directory Enumeration (Gobuster)
    ↓
JavaScript Source Analysis (main.js)
    ↓
AES Passphrase Discovery (SecretPassphraseMomentum)
    ↓
Browser Cookie Extraction (document.cookie)
    ↓
Cookie Decryption (AES-256)
    ↓
SSH Credentials Obtained (auxerre:auxerre-alienum##)
    ↓
Initial Access via SSH
    ↓
User Flag Captured (/home/auxerre/user.txt)
    ↓
Service Enumeration (ss -tlnp)
    ↓
Redis Discovery (Port 6379)
    ↓
Redis Connection (redis-cli)
    ↓
Database Key Enumeration (KEYS *)
    ↓
Root Password Extraction (GET rootpass)
    ↓
Privilege Escalation (su -l)
    ↓
Root Flag Captured (/root/root.txt)
    ↓
Complete System Compromise
```

---

## Security Recommendations

### 1. Client-Side Security
- Never include sensitive information in client-side code
- Remove all commented code from production JavaScript
- Implement proper encryption with server-side key management
- Use secure session management instead of cookie-based credentials
- Employ code obfuscation for production deployments (defense in depth)

### 2. Cookie Security
- Set `HttpOnly` flag to prevent JavaScript access
- Use `Secure` flag for HTTPS-only transmission
- Implement `SameSite` attribute to prevent CSRF attacks
- Never store passwords or sensitive authentication data in cookies
- Use short-lived session tokens with server-side validation

### 3. Redis Security
- Enable authentication with `requirepass` directive
- Use strong, randomly generated passwords
- Bind Redis to 127.0.0.1 only if remote access isn't required
- Implement Redis ACL for fine-grained access control
- Encrypt sensitive data before storage
- Regular security audits of stored keys
- Use TLS for Redis connections when remote access is needed
- Keep Redis updated to latest stable version

### 4. Credential Management
- Never store passwords in plain text
- Use strong hashing algorithms (bcrypt, Argon2, scrypt)
- Implement proper password policies (length, complexity, rotation)
- Use environment variables for sensitive configuration
- Avoid credential reuse across services
- Implement multi-factor authentication where possible

### 5. Web Application Security
- Implement all recommended security headers:
  - `X-Frame-Options: DENY`
  - `X-Content-Type-Options: nosniff`
  - `Content-Security-Policy`
  - `Strict-Transport-Security`
- Use HTTPS/TLS for all traffic
- Regular security assessments and code reviews
- Follow OWASP secure coding practices
- Disable directory indexing (`Options -Indexes`)

### 6. System Hardening
- Keep all software and packages updated
- Implement principle of least privilege
- Use `sudo` instead of direct root login
- Disable `su` command for non-administrative users
- Enable and configure firewall rules (iptables, ufw)
- Monitor and log all authentication attempts
- Implement intrusion detection systems (fail2ban, OSSEC)
- Regular security audits and penetration testing

---

## Tools Used

| Tool | Version | Purpose |
|------|---------|---------|
| Nmap | 7.98 | Network scanning and service enumeration |
| Nikto | 2.5.0 | Web server vulnerability scanning |
| Gobuster | 3.8.2 | Directory and file enumeration |
| curl | - | HTTP requests and file retrieval |
| Browser DevTools | - | Cookie inspection and JavaScript analysis |
| Online AES Decrypt | - | Cookie decryption (browserling.com) |
| OpenSSH | - | Remote access client |
| redis-cli | - | Redis database client |
| ss | - | Network service enumeration |

---

## Additional Redis Commands Reference

For those new to Redis exploitation, here are some useful commands:

```bash
# Connect to Redis
redis-cli

# List all databases
INFO keyspace

# Select a database (default is 0)
SELECT 0

# List all keys
KEYS *

# Get value of a key
GET keyname

# Get type of a key
TYPE keyname

# Get all keys matching pattern
KEYS *pass*

# Get server info
INFO

# List all configuration
CONFIG GET *

# Exit
exit
```

---

## References

- **VulnHub Momentum-1:** https://www.vulnhub.com/entry/momentum-1,685/
- **Redis Security:** https://redis.io/docs/management/security/
- **OWASP Top 10:** https://owasp.org/www-project-top-ten/
- **Redis Quick Start:** https://redis.io/docs/getting-started/
- **AES Encryption:** https://en.wikipedia.org/wiki/Advanced_Encryption_Standard
- **Cookie Security:** https://owasp.org/www-community/controls/SecureCookieAttribute
- **CryptoJS Documentation:** https://cryptojs.gitbook.io/docs/

---

## Author

**0xCr0nu5**  
Connect with me: [GitHub](https://github.com/0xCr0nu5)

---

## Disclaimer

This writeup is for **educational purposes only**. All techniques demonstrated should only be used on systems you own or have **explicit written permission** to test. Unauthorized access to computer systems is illegal and punishable by law.

**Remember:** With great power comes great responsibility. Use your skills ethically.

---
