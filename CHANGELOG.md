# Changelog

Alle wichtigen Änderungen an der Klassenkasse stehen hier. Das Format folgt
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/), die Versionsnummern folgen
[Semantic Versioning](https://semver.org/lang/de/). Solange die Version mit 0 beginnt, ist
die Klassenkasse in aktiver Entwicklung: zwischen Versionen kann sich noch alles ändern.
Die Versionen bleiben unter 1.0, bis zum ersten finalen Release, das 1.0.0 wird.

Eine Installation aktualisierst du mit `update` im Container oder auf dem Proxmox-Host mit
`bash <(curl -fsSL https://raw.githubusercontent.com/StofflHD/klassenkasse/main/install.sh) --update`

## [0.1.0] – 2026-10-15

Erste veröffentlichte Version.

### Hinzugefügt
- Installer für den Proxmox-Host (`install.sh`): legt einen Debian-LXC an, installiert die
  App, legt den ersten Administrator an; `--update`, `--uninstall`, `-y` und Vorgaben per
  Umgebungsvariablen (`KK_*`)
- Befehl `update` im Container: holt die neueste Version von GitHub, sichert vorher die
  Datenbank; `update --check` zeigt nur, ob eine neue Version da ist
- Versionsnummer in der Fußzeile der Web-Oberfläche und per `klassenkasse-admin version`
- `klassenkasse-admin create-user … --password-stdin` für Skripte
- Dokumentation in `docs/`

### Geändert
- Der Programmcode liegt jetzt in `/opt/klassenkasse/app`. Installationen nach der alten
  Zip-Anleitung übernimmt `install.sh --update` auf dem Host (Container-ID angeben);
  Datenbank und `/etc/klassenkasse.env` bleiben unverändert.
