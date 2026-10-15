<p align="center"><img src="app/static/logo.svg" width="96" alt="Klassenkasse-Logo"></p>

# Klassenkasse

Web-App zur Verwaltung einer Klassenkasse: Einnahmen und Ausgaben buchen, Sammelaktionen
(„Ausflug Zoo, 12 € pro Kopf“) mit Übersicht, wer noch offen ist, CSV-Export für die
Kassenprüfung. Läuft als eigener LXC-Container auf einem Proxmox-Host und wird mit einem
einzigen Befehl installiert.

**Technik:** Python 3, Flask, SQLite, Gunicorn, systemd

## Funktionen

- **Kassenstand, Einnahmen, Ausgaben** auf einen Blick
- **Buchungen** mit Zweck, optional einer Schülerin/einem Schüler und einer Sammlung zugeordnet
- **Sammlungen** mit Soll pro Kopf: Liste „bezahlt / offen“, Zahlung mit einem Klick erfassen
  (Teilzahlungen möglich)
- **Klassenliste** als Tabelle: Geburtstag, Anschrift, Notiz und zwei Erziehungsberechtigte
  in eigenen Spalten (Name, Telefon, E-Mail, abweichende Anschrift), mit Suche
- **Import der Klassenliste** aus Excel (.xlsx) oder CSV, mit Vorschau vor dem Übernehmen
- **Pro Schüler/in:** Kontaktdaten, alle Zahlungen und offene Beträge
- **Revisionssicher:** Buchungen können nicht gelöscht oder geändert werden – nur storniert
  (mit Grund, Zeit und Benutzer). Das erzwingt die Datenbank selbst per Trigger.
- **Keine Rundungsfehler:** Beträge werden intern in Cent gespeichert
- **Benutzer mit Rollen:** *Nur lesen* (Elternvertretung, Kassenprüfung), *Kassenwart*, *Administrator*
- **Export als Excel (.xlsx) oder CSV** für Buchungen, Sammlungen und Klassenliste
- **Tägliche Sicherung** der Datenbank, 30 Tage aufbewahrt, und eine zusätzliche vor jedem Update
- **Update mit einem Befehl:** `update` im Container
- Mobiltauglich, heller und dunkler Modus

## Installation

Auf dem **Proxmox-Host** als root:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/StofflHD/klassenkasse/main/install.sh)
```

Der Installer fragt nach Container-ID, Storage, Netzwerk, dem Namen der Klasse und dem
Login des ersten Administrators, legt einen Debian-LXC an (unprivilegiert, 1 CPU, 512 MB
RAM, 2 GB Disk) und richtet alles ein. Danach läuft die Klassenkasse unter
`http://<IP-des-Containers>:8000`.

Unbeaufsichtigt, mit fertigen Antworten:

```bash
KK_CTID=150 KK_KLASSE="Klassenkasse 7b" KK_NET=192.168.1.60/24 KK_GW=192.168.1.1 \
  bash <(curl -fsSL https://raw.githubusercontent.com/StofflHD/klassenkasse/main/install.sh) -y
```

Alle Varianten, auch die Installation in einen vorhandenen Container:
[docs/installation.md](docs/installation.md)

## Update

Im Container (`pct enter <ID>`):

```bash
update
```

oder auf dem Proxmox-Host:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/StofflHD/klassenkasse/main/install.sh) --update
```

Datenbank, Benutzer und Konfiguration bleiben erhalten; die Datenbank wird vorher gesichert.
`update --check` zeigt nur, ob es eine neue Version gibt. Was sich geändert hat, steht im
[CHANGELOG](CHANGELOG.md).

## Verwaltung

| Aufgabe | Befehl (im Container) |
|---|---|
| Benutzer anlegen / Passwort zurücksetzen | `klassenkasse-admin create-user NAME --role admin\|kasse\|lesen` |
| Manuelle Sicherung | `klassenkasse-admin backup /var/lib/klassenkasse/backup/manuell.db` |
| Version | `klassenkasse-admin version` |
| Status / Neustart | `systemctl status klassenkasse` / `systemctl restart klassenkasse` |
| Logs | `journalctl -u klassenkasse -f` |
| Konfiguration | `/etc/klassenkasse.env` ([Optionen](docs/configuration.md)) |

**Dateien:** Programm in `/opt/klassenkasse`, Daten in `/var/lib/klassenkasse`
(`klassenkasse.db` + `backup/`). Zusätzlich empfiehlt sich ein Proxmox-Backup (vzdump) des
Containers.

## Dokumentation

- [Installation](docs/installation.md) – Host-Installer, Variablen, manuelle Installation, Deinstallation
- [Bedienung](docs/usage.md) – Buchungen, Sammlungen, Storno, Rollen, Export
- [Konfiguration](docs/configuration.md) – `/etc/klassenkasse.env`, Sicherungen
- [Reverse-Proxy / HTTPS](docs/reverse-proxy.md) – Zugriff von außen
- [Fehlersuche](docs/troubleshooting.md)
- [Entwicklung](docs/development.md) – lokal starten, Datenmodell, Release

## Datenschutz

Die App enthält Namen, Anschriften und Kontaktdaten von Kindern und Eltern sowie
Zahlungsdaten. Alle Konten – auch *Nur lesen* – sehen die Klassenliste. Bitte nicht ohne HTTPS ins Internet
stellen ([Reverse-Proxy](docs/reverse-proxy.md) oder VPN), starke Passwörter verwenden und
nur so viele Konten wie nötig anlegen.

## Lizenz

[GPL-3.0](LICENSE)
