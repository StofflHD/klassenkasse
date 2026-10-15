# Installation

## Mit dem Installer auf dem Proxmox-Host (empfohlen)

Auf dem Proxmox-Host als root:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/StofflHD/klassenkasse/main/install.sh)
```

Der Installer

1. fragt Container-ID, Hostname, Storage, Bridge, IP (DHCP oder fest), den Namen der Klasse,
   den Login des ersten Administrators und optional ein root-Passwort für den Container,
2. lädt bei Bedarf das neueste Debian-Template (13, sonst 12),
3. legt einen unprivilegierten LXC an (1 CPU, 512 MB RAM, 512 MB Swap, 2 GB Disk, Start beim
   Booten, Tag `klassenkasse`),
4. installiert darin die App mit `deploy/install.sh`, legt den Administrator an und prüft,
   ob die Web-Oberfläche antwortet.

Am Ende zeigt er die Adresse (`http://<IP>:8000`) und den Login. Wird das Passwort leer
gelassen, erzeugt er ein zufälliges und zeigt es **einmal** an – gleich notieren.

Das Log liegt in `/var/log/klassenkasse-install.log`.

### Optionen

| Option | Wirkung |
|---|---|
| *(keine)* | Neuinstallation |
| `--update` | App in einem vorhandenen Container aktualisieren |
| `--uninstall` | Container nach Rückfrage löschen |
| `-y`, `--yes` | Nichts fragen, Standardwerte bzw. Variablen nehmen |
| `-h`, `--help` | Hilfe |

### Variablen

Jede Frage lässt sich vorgeben; mit `-y` werden für alles andere die Standardwerte genommen.

| Variable | Standard | Bedeutung |
|---|---|---|
| `KK_CTID` | nächste freie ID | Container-ID |
| `KK_HOSTNAME` | `klassenkasse` | Hostname |
| `KK_ROOTFS_STORAGE` | `local-lvm` bzw. erster passender | Storage für den Container |
| `KK_TEMPLATE_STORAGE` | `local` | Storage für das Template |
| `KK_BRIDGE` | `vmbr0` | Netzwerk-Bridge |
| `KK_NET` | `dhcp` | `dhcp` oder z. B. `192.168.1.60/24` |
| `KK_GW` | Default-Gateway des Hosts | Gateway bei fester IP |
| `KK_KLASSE` | `Klassenkasse` | Titel in der Web-Oberfläche |
| `KK_USER` | `admin` | erster Administrator |
| `KK_PASSWORD` | zufällig | sein Passwort (mind. 8 Zeichen) |
| `KK_ROOT_PASSWORD` | keins | root-Passwort des Containers |
| `KK_REPO` | `StofflHD/klassenkasse` | GitHub-Repository |
| `KK_REF` | `main` | Branch oder Tag |

Beispiel:

```bash
KK_CTID=150 KK_KLASSE="Klassenkasse 7b" KK_NET=192.168.1.60/24 KK_GW=192.168.1.1 \
  bash <(curl -fsSL https://raw.githubusercontent.com/StofflHD/klassenkasse/main/install.sh) -y
```

Passwörter werden nie als Argument übergeben (sie stünden sonst in `ps` und im Log), sondern
über stdin.

### Aus einer lokalen Kopie

Repository auf den Host kopieren (z. B. per `git clone` oder `scp`) und dort
`bash install.sh` ausführen. Kommen die Dateien von Windows, wandelt der Installer
CRLF-Zeilenenden automatisch um.

## In einen vorhandenen Container

Für einen selbst angelegten Debian-12/13- oder Ubuntu-24.04-Container:

```bash
apt-get update && apt-get install -y curl
curl -fsSL https://codeload.github.com/StofflHD/klassenkasse/tar.gz/main | tar -xz
cd klassenkasse-main
bash deploy/install.sh
```

Das Skript fragt nach dem Klassennamen und legt den ersten Administrator an.

## Update

Im Container: `update` (Details siehe [README](../README.md#update)). Auf dem Host:
`install.sh --update` – findet den Container über den Tag `klassenkasse`, sonst nach der ID
fragen lassen.

Installationen nach der alten Zip-Anleitung (Code direkt in `/opt/klassenkasse`) lassen sich
ebenfalls mit `install.sh --update` übernehmen: die Container-ID angeben, Datenbank und
Konfiguration bleiben, der Container bekommt den Tag `klassenkasse`.

Vor jedem Update wird die Datenbank als
`/var/lib/klassenkasse/backup/vor-update_<alte-version>_<datum>.db` gesichert. Diese Dateien
werden nicht automatisch gelöscht.

## Deinstallation

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/StofflHD/klassenkasse/main/install.sh) --uninstall
```

Der Container wird nur gelöscht, wenn du zur Bestätigung seine ID eintippst – auch mit `-y`.
Vorher bei Bedarf die Datenbank sichern, siehe [Konfiguration](configuration.md#sicherungen).
