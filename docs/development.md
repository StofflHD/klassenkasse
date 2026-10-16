# Entwicklung

## Lokal starten

```bash
python3 -m venv venv && . venv/bin/activate
pip install -r requirements.txt
cd app
flask --app app create-user admin
flask --app app run --debug
```

Die Datenbank landet dann als `app/klassenkasse.db` (mit `KK_DB` änderbar) und ist per
`.gitignore` ausgeschlossen.

## Aufbau

```
install.sh                 Installer für den Proxmox-Host (legt den LXC an)
deploy/install.sh          Installation/Update im Container
deploy/update.sh           wird zu /usr/bin/update im Container
deploy/*.service, *.timer  systemd: App (Gunicorn) und tägliche Sicherung
app/app.py                 Flask-App: Routen, Rechte, Import-Logik, CLI (create-user, backup, version)
app/tableio.py             Tabellen lesen/schreiben: CSV und Excel (openpyxl)
app/schema.sql             Tabellen und Trigger (wird bei jedem Start angewendet)
app/templates/, static/    Oberfläche
VERSION                    aktuelle Version, von update.sh mit GitHub verglichen
```

Im Container: Code in `/opt/klassenkasse/app`, venv in `/opt/klassenkasse/venv`, Daten in
`/var/lib/klassenkasse`, Konfiguration in `/etc/klassenkasse.env`. Der Dienst läuft als
Systembenutzer `klassenkasse` mit systemd-Härtung (`ProtectSystem=strict`, nur
`/var/lib/klassenkasse` beschreibbar).

## Datenmodell

```
students     (id, name, active, street, zip, city, notes,
              g1_name, g1_phone, g1_email, g1_address,
              g2_name, g2_phone, g2_email, g2_address)
collections  (id, title, amount_cents, due_date, closed)
bookings     (id, booking_date, kind in/out, amount_cents, purpose,
              student_id?, collection_id?, created_by, created_at,
              cancelled_at?, cancelled_by?, cancel_reason?)
users        (id, username, pw_hash, role)
login_failures (id, ip, username, at)              Fehlversuche, 30 Tage
ip_blocks    (ip, blocked_at, created_by, reason)  Sperrliste (Adresse oder Netz)
```

Der Kassenstand wird nie gespeichert, sondern immer aus den nicht stornierten Buchungen
berechnet. Trigger verhindern Löschen und Ändern von Buchungen sowie das Aufheben eines
Stornos.

`schema.sql` beschreibt den aktuellen Stand und nutzt nur `CREATE … IF NOT EXISTS`. Bestehende
Datenbanken bringt `migrate()` in `app.py` beim Start auf diesen Stand – in einer
Schreibtransaktion (`BEGIN IMMEDIATE`), damit Dienst und `klassenkasse-admin` sich nicht in
die Quere kommen. Neue Spalten also in beiden Stellen ergänzen. In älteren Datenbanken
bleiben nicht mehr genutzte Spalten stehen: `guardians`, `phone`, `phone2`, `email` (0.2.0)
`g1_mobile`, `g2_mobile` (0.3.0, nach der Übernahme geleert) und `birthday` (bis 0.6.0).

## Release

1. `VERSION` erhöhen (bis zum finalen Release 0.x, siehe CHANGELOG)
2. Eintrag in `CHANGELOG.md`
3. Commit, Tag `vX.Y.Z`, nach `main` pushen – ab dann meldet `update` die neue Version
