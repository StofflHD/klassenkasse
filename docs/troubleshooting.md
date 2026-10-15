# Fehlersuche

## Der Installer bricht ab

Er zeigt die letzten 25 Zeilen; das ganze Log steht in `/var/log/klassenkasse-install.log`
auf dem Host.

- **„Kein Debian-Template gefunden“** – `pveam update` schlägt fehl, meist kein Internet/DNS
  auf dem Host. `pveam available --section system` prüfen.
- **„hat nach 2 Minuten kein Netz/DNS“** – DHCP im Netz? Bei fester IP: Gateway richtig?
  Im Container nachsehen: `pct enter <ID>`, dann `ip a` und `cat /etc/resolv.conf`.
- **„CT … gibt es schon“** – andere ID wählen oder `--update` nutzen.
- **Abbruch nach „App installieren“** – der Container ist schon da. `install.sh --update`
  mit seiner ID ausführen: das schließt die Installation ab und legt den ersten
  Administrator an, falls es noch keinen gibt.

## Die Web-Oberfläche antwortet nicht

Im Container:

```bash
systemctl status klassenkasse
journalctl -u klassenkasse -n 50
```

Häufige Ursachen:

- Tippfehler in `/etc/klassenkasse.env` (z. B. fehlendes Anführungszeichen bei `KK_KLASSE`)
- Datenbank gehört nicht dem Benutzer `klassenkasse` (nach einer Wiederherstellung):
  `chown -R klassenkasse:klassenkasse /var/lib/klassenkasse`
- Port belegt: `ss -tlnp | grep 8000`

## „Ungültige Anfrage (evtl. Seite neu laden)“

Das Formular war zu alt (Schutz gegen gefälschte Anfragen). Seite neu laden und noch einmal
absenden. Passiert das ständig hinter einem Reverse-Proxy: `KK_BEHIND_PROXY=1` gesetzt? Mit
`KK_COOKIE_SECURE=1` geht die Anmeldung nur über HTTPS.

## Passwort vergessen

Im Container (bzw. vom Host mit `pct exec <ID> --`):

```bash
klassenkasse-admin create-user admin --role admin
```

Setzt Passwort und Rolle neu, wenn es den Benutzer schon gibt, sonst wird er angelegt.

## `update` findet GitHub nicht

`curl -I https://raw.githubusercontent.com` im Container testen. Ohne Internet: neue Version
auf den Host kopieren und dort `bash install.sh --update` aus der lokalen Kopie ausführen.

## Ein Update ist schiefgegangen

Die Datenbank von vor dem Update liegt in `/var/lib/klassenkasse/backup/vor-update_*.db`;
Wiederherstellen wie in [Konfiguration](configuration.md#wiederherstellen). Eine ältere
Version installieren: `KK_REF=v0.1.0 update --force` (Tag aus GitHub).
