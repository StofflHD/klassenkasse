# Changelog

Alle wichtigen Änderungen an der Klassenkasse stehen hier. Das Format folgt
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/), die Versionsnummern folgen
[Semantic Versioning](https://semver.org/lang/de/). Solange die Version mit 0 beginnt, ist
die Klassenkasse in aktiver Entwicklung: zwischen Versionen kann sich noch alles ändern.
Die Versionen bleiben unter 1.0, bis zum ersten finalen Release, das 1.0.0 wird.

Eine Installation aktualisierst du mit `update` im Container oder auf dem Proxmox-Host mit
`bash <(curl -fsSL https://raw.githubusercontent.com/StofflHD/klassenkasse/main/install.sh) --update`

## [0.6.0] – 2026-10-15

### Hinzugefügt
- **Export als Excel (.xlsx)** zusätzlich zu CSV – für Buchungen, Sammlungen und die
  Klassenliste. Beträge sind echte Zahlen, Datumsangaben echte Daten, die Kopfzeile ist
  fixiert und hat einen Filter.
- **Import der Klassenliste** aus Excel oder CSV: erkennt die Spalten des Exports und gängige
  Überschriften (Vorname/Nachname, Geburtsdatum, PLZ, Telefon …), zeigt vor dem Übernehmen
  eine Vorschau (neu / ändern / gleich / Fehler) und erkennt vorhandene Schüler/innen am
  Namen. Leere Zellen überschreiben nichts.

### Geändert
- Neue Abhängigkeiten `openpyxl` und `defusedxml`; `update` installiert sie automatisch.
- Die Export-Adressen enden auf `.xlsx` oder `.csv` (z. B. `/export/klassenliste.xlsx`).

## [0.5.0] – 2026-10-15

### Hinzugefügt
- **Logo und Favicon:** Euro-Münze über einer Kasse im Grün der App. Das Logo steht in der
  Kopfzeile und auf der Anmeldeseite; Favicon als SVG mit PNG-Ersatz (32 px) und ein
  Symbol für den iOS-Homescreen (180 px).

## [0.4.0] – 2026-10-15

### Geändert
- **Ein Telefonfeld je Erziehungsberechtigte/m:** *Telefon* und *Mobil* sind
  zusammengelegt – eine Nummer reicht, Festnetz oder mobil. Wer doch zwei braucht, trennt
  sie mit `/`; jede Nummer ist einzeln anklickbar.
- Beim ersten Start werden vorhandene Mobilnummern ins Telefonfeld übernommen. Stand bei
  einer Person beides drin, stehen danach beide Nummern im Telefonfeld
  („089 123456 / 0171 2345678“) – bei Bedarf über *Bearbeiten* auf eine kürzen.

## [0.3.0] – 2026-10-15

### Geändert
- **Erziehungsberechtigte in eigenen Spalten:** Statt einer gemeinsamen Spalte gibt es jetzt
  Erziehungsberechtigte/r 1 und 2, jeweils mit Name, Telefon, Mobil, E-Mail und einer
  Anschrift, falls sie von der des Kindes abweicht. Telefon und E-Mail gehören jetzt zur
  jeweiligen Person, nicht mehr zum Kind.
- Die Seite einer Schülerin/eines Schülers zeigt die Kontaktdaten als Karten: Kind,
  Erziehungsberechtigte/r 1 und 2.
- CSV-Export der Klassenliste mit eigenen Spalten je Erziehungsberechtigte/m.

### Übernahme bestehender Daten
- Einträge aus 0.2.0 werden beim ersten Start automatisch zu Erziehungsberechtigte/r 1
  verschoben: *Erziehungsberechtigte* → Name, *Telefon* → Telefon, *Telefon 2 / mobil* →
  Mobil, *E-Mail* → E-Mail. Stehen dort zwei Personen (z. B. „Maria und Peter Beispiel“),
  bitte die zweite über *Bearbeiten* nach Erziehungsberechtigte/r 2 verschieben.

## [0.2.0] – 2026-10-15

### Hinzugefügt
- **Klassenliste:** Der Reiter *Schüler* heißt jetzt *Klassenliste* und zeigt eine Tabelle mit
  Geburtstag, Erziehungsberechtigten, Anschrift, Telefon (zwei Nummern), E-Mail und Notiz.
  Telefon und E-Mail sind anklickbar, ein Suchfeld filtert die Tabelle.
- Schüler/innen einzeln mit allen Kontaktdaten anlegen; das Anlegen mehrerer Namen auf
  einmal bleibt.
- Kontaktdaten auf der Seite der Schülerin/des Schülers anzeigen und bearbeiten
- CSV-Export der Klassenliste

### Geändert
- Bestehende Datenbanken bekommen die neuen Spalten beim ersten Start automatisch;
  vorhandene Daten bleiben unverändert.

## [0.1.1] – 2026-10-15

### Behoben
- Die Installation brach beim Schritt *Administrator anlegen* ab
  (`env: 'klassenkasse-admin': No such file or directory`): `pct exec` sucht nicht in
  `/usr/local/bin`. Die Skripte rufen den Befehl jetzt mit vollem Pfad auf.
- `install.sh --update` legt den ersten Administrator an, wenn es noch keinen Benutzer gibt.
  So lässt sich eine abgebrochene Installation fertigstellen, ohne den Container neu
  anzulegen.

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
