#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 StofflHD
# Klassenkasse – Installation/Update im Debian- oder Ubuntu-LXC.
# Aufruf im Container als root aus dem Projektordner:  bash deploy/install.sh [--quiet]
# Erneut ausführen = Update: Datenbank und Konfiguration bleiben erhalten.
# Der Installer auf dem Proxmox-Host (install.sh) ruft das mit --quiet auf:
# dann wird nichts gefragt, den ersten Administrator legt der Host-Installer an.
# Klassenname vorgeben (nur bei Neuinstallation): KK_KLASSE="Klassenkasse 7b" bash deploy/install.sh
set -euo pipefail

APP_DIR=/opt/klassenkasse
DATA_DIR=/var/lib/klassenkasse
ENV_FILE=/etc/klassenkasse.env
SVC_USER=klassenkasse
SRC="$(cd "$(dirname "$0")/.." && pwd)"
QUIET=0
[[ "${1:-}" == "--quiet" ]] && QUIET=1

say() { [[ $QUIET == 1 ]] || echo "==> $*"; }

[ "$(id -u)" -eq 0 ] || { echo "Bitte als root ausführen."; exit 1; }
[ -f "$SRC/app/app.py" ] || { echo "Projektdateien fehlen in $SRC"; exit 1; }

say "Pakete installieren"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
# curl: für den Befehl "update"; im Debian-Template fehlt es
apt-get install -y -qq python3 python3-venv sqlite3 curl >/dev/null

say "Systembenutzer und Verzeichnisse"
id -u "$SVC_USER" &>/dev/null || useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin "$SVC_USER"
install -d -o "$SVC_USER" -g "$SVC_USER" -m 750 "$DATA_DIR" "$DATA_DIR/backup"
install -d -m 755 "$APP_DIR"

say "Programmdateien kopieren"
# Code ersetzen – Daten liegen in $DATA_DIR, die Konfiguration in $ENV_FILE
rm -rf "$APP_DIR/app"
# Installationen aus dem alten Zip hatten den Code direkt in $APP_DIR
rm -rf "$APP_DIR/app.py" "$APP_DIR/schema.sql" "$APP_DIR/templates" "$APP_DIR/static" "$APP_DIR/__pycache__"
cp -r "$SRC/app" "$SRC/requirements.txt" "$SRC/VERSION" "$APP_DIR/"
find "$APP_DIR/app" -name __pycache__ -prune -exec rm -rf {} +

say "Python-Umgebung"
[ -x "$APP_DIR/venv/bin/pip" ] || python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install -q --upgrade pip
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

if [ ! -f "$ENV_FILE" ]; then
  say "Konfiguration anlegen ($ENV_FILE)"
  KLASSE="${KK_KLASSE:-}"
  if [[ -z $KLASSE && $QUIET == 0 ]]; then
    read -rp "Name der Klasse (z. B. 'Klassenkasse 7b'): " KLASSE || true
  fi
  KLASSE="${KLASSE:-Klassenkasse}"
  # landet in Anführungszeichen in der env-Datei
  [[ $KLASSE != *[\"\\\$\`]* ]] || { echo "Klassenname darf kein \" \\ \$ oder \` enthalten."; exit 1; }
  cat > "$ENV_FILE" <<EOF
# Klassenkasse – Konfiguration. Nach Änderungen: systemctl restart klassenkasse
KK_KLASSE="$KLASSE"
KK_DB=$DATA_DIR/klassenkasse.db
KK_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
KK_BIND=0.0.0.0:8000
# Auf 1 setzen, wenn ein Reverse-Proxy mit HTTPS davor steht (z. B. Nginx Proxy Manager, Caddy)
KK_BEHIND_PROXY=0
KK_COOKIE_SECURE=0
EOF
fi
chown root:"$SVC_USER" "$ENV_FILE"
chmod 640 "$ENV_FILE"

say "Verwaltungsbefehl klassenkasse-admin"
cat > /usr/local/bin/klassenkasse-admin <<EOF
#!/bin/sh
# Beispiele: klassenkasse-admin create-user anna --role kasse
#            klassenkasse-admin backup /var/lib/klassenkasse/backup/manuell.db
#            klassenkasse-admin version
cd $APP_DIR/app
exec runuser -u $SVC_USER -- sh -c 'set -a; . $ENV_FILE; set +a; exec $APP_DIR/venv/bin/flask --app app "\$@"' sh "\$@"
EOF
chmod 755 /usr/local/bin/klassenkasse-admin

# Befehl "update" für die Klassenkasse selbst. Temp-Datei + mv: update.sh kann
# gerade selbst laufen, und bash liest ein überschriebenes Skript an der alten Stelle weiter.
install -m 0755 "$SRC/deploy/update.sh" /usr/bin/update.kk-new
mv -f /usr/bin/update.kk-new /usr/bin/update

say "systemd-Dienste"
cp "$SRC/deploy/klassenkasse.service" "$SRC/deploy/klassenkasse-backup.service" \
   "$SRC/deploy/klassenkasse-backup.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable -q --now klassenkasse-backup.timer
systemctl enable -q klassenkasse
systemctl restart klassenkasse

[[ $QUIET == 1 ]] && exit 0

if [ "$(/usr/local/bin/klassenkasse-admin count-users | tail -n1)" = "0" ]; then
  echo "==> Ersten Administrator anlegen"
  read -rp "Benutzername [admin]: " ADMIN || true
  /usr/local/bin/klassenkasse-admin create-user "${ADMIN:-admin}" --role admin
fi

sleep 1
IP=$(hostname -I | awk '{print $1}')
PORT=$(grep -oP '^KK_BIND=.*:\K[0-9]+' "$ENV_FILE" || echo 8000)
if systemctl is-active --quiet klassenkasse; then
  echo
  echo "Fertig. Klassenkasse $(cat "$APP_DIR/VERSION") läuft unter:  http://$IP:$PORT"
  echo "Logs:   journalctl -u klassenkasse -f"
  echo "Backup: täglich 02:30 nach $DATA_DIR/backup (30 Tage)"
  echo "Update: update"
else
  echo "Dienst startet nicht – siehe: journalctl -u klassenkasse -n 50"; exit 1
fi
