# Konfiguration

Die Konfiguration steht in `/etc/klassenkasse.env` im Container (gehört root, lesbar für den
Dienst). Nach einer Änderung:

```bash
systemctl restart klassenkasse
```

| Variable | Standard | Bedeutung |
|---|---|---|
| `KK_KLASSE` | `Klassenkasse` | Titel in der Web-Oberfläche, in Anführungszeichen |
| `KK_DB` | `/var/lib/klassenkasse/klassenkasse.db` | SQLite-Datenbank |
| `KK_SECRET` | zufällig bei der Installation | Schlüssel für die Sitzungs-Cookies. Ändern meldet alle ab. |
| `KK_BIND` | `0.0.0.0:8000` | Adresse und Port. `127.0.0.1:8000`, wenn ein Reverse-Proxy im selben Container läuft. |
| `KK_BEHIND_PROXY` | `0` | `1`, wenn ein Reverse-Proxy davor steht (wertet `X-Forwarded-*` aus) |
| `KK_COOKIE_SECURE` | `0` | `1`, wenn nur noch per HTTPS zugegriffen wird |

Updates lassen diese Datei unverändert.

Wird der Port geändert, nutzen `update` und `install.sh --update` automatisch den neuen;
der Installer auf dem Host prüft allerdings Port 8000.

## Sicherungen

- **Täglich um 02:30** schreibt der Timer `klassenkasse-backup.timer` eine Kopie nach
  `/var/lib/klassenkasse/backup/klassenkasse_<datum>.db`. Kopien älter als 30 Tage werden
  gelöscht. Verpasste Läufe (Container aus) werden beim nächsten Start nachgeholt.
- **Vor jedem Update** eine Kopie `vor-update_<version>_<datum>.db` – bleibt, bis du sie
  löschst.
- **Manuell:** `klassenkasse-admin backup /var/lib/klassenkasse/backup/manuell.db`

Die Sicherungen liegen im Container. Für den Fall, dass der Container selbst verloren geht,
zusätzlich ein Proxmox-Backup (vzdump, PBS) des Containers einrichten.

Sicherung aus dem Container auf den Host holen:

```bash
pct pull <ID> /var/lib/klassenkasse/backup/klassenkasse_2026-10-15.db ./klassenkasse_2026-10-15.db
```

### Wiederherstellen

```bash
systemctl stop klassenkasse
cp /var/lib/klassenkasse/backup/klassenkasse_2026-10-15.db /var/lib/klassenkasse/klassenkasse.db
rm -f /var/lib/klassenkasse/klassenkasse.db-wal /var/lib/klassenkasse/klassenkasse.db-shm
chown klassenkasse:klassenkasse /var/lib/klassenkasse/klassenkasse.db
systemctl start klassenkasse
```
