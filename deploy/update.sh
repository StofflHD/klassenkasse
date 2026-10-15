#!/usr/bin/env bash
# KK_SELF_UPDATE – wird als /usr/bin/update im Klassenkasse-Container installiert.
#
#   update            Klassenkasse auf die neueste Version von GitHub bringen
#   update --check    nur anzeigen, ob ein Update da ist
#   update --force    neu installieren, auch wenn die Version gleich ist
#
# Datenbank, Benutzer und Konfiguration bleiben erhalten. Vor dem Update wird
# die Datenbank nach /var/lib/klassenkasse/backup/ gesichert.
set -euo pipefail

REPO="${KK_REPO:-StofflHD/klassenkasse}"
REF="${KK_REF:-main}"
APP_DIR=/opt/klassenkasse
DATA_DIR=/var/lib/klassenkasse
ENV_FILE=/etc/klassenkasse.env

RD=$'\e[31m' GN=$'\e[32m' BL=$'\e[36m' BD=$'\e[1m' CL=$'\e[0m'
info() { echo -e "${BL}➜${CL} $*"; }
ok()   { echo -e "${GN}✔${CL} $*"; }
die()  { echo -e "${RD}✘ $*${CL}" >&2; exit 1; }

CHECK=0
FORCE=0
for a in "$@"; do
  case "$a" in
    --check) CHECK=1 ;;
    --force) FORCE=1 ;;
    -h | --help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "Unbekannte Option: $a (siehe --help)" ;;
  esac
done

[[ $EUID -eq 0 ]] || die "Bitte als root ausführen"
[[ -d $APP_DIR/app ]] || die "Klassenkasse ist nicht in $APP_DIR installiert"

port() { grep -oP '^KK_BIND=.*:\K[0-9]+' "$ENV_FILE" 2>/dev/null || echo 8000; }

installed=$(tr -d '[:space:]' <"$APP_DIR/VERSION" 2>/dev/null || true)
installed=${installed:-unbekannt}
latest=$(curl -fsSL --max-time 20 "https://raw.githubusercontent.com/$REPO/$REF/VERSION" | tr -d '[:space:]') ||
  die "GitHub nicht erreichbar ($REPO)"
[[ $latest =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "Unerwartete Version von GitHub: '$latest'"
info "Installiert: ${BD}$installed${CL}, neueste: ${BD}$latest${CL}"

if [[ $installed == "$latest" && $FORCE == 0 ]]; then
  ok "Klassenkasse ist aktuell"
  exit 0
fi
if [[ $CHECK == 1 ]]; then
  info "Update verfügbar: $installed → $latest (ausführen: update)"
  exit 0
fi

tmp=$(mktemp -d /tmp/kk-update.XXXXXX)
trap 'rm -rf "$tmp"' EXIT

info "Lade $REPO ($REF) …"
curl -fsSL --max-time 120 "https://codeload.github.com/$REPO/tar.gz/$REF" | tar -xz -C "$tmp" --strip-components=1 ||
  die "Download fehlgeschlagen"
[[ -f $tmp/deploy/install.sh && -f $tmp/app/app.py ]] || die "Heruntergeladenes Archiv ist unvollständig"

if [[ -f $DATA_DIR/klassenkasse.db ]]; then
  backup="$DATA_DIR/backup/vor-update_${installed}_$(date +%F_%H%M).db"
  klassenkasse-admin backup "$backup" >/dev/null || die "Sicherung der Datenbank fehlgeschlagen"
  ok "Datenbank gesichert: $backup"
fi

info "Installiere (dauert bis zu einer Minute) …"
log=$(mktemp)
if ! bash "$tmp/deploy/install.sh" --quiet >"$log" 2>&1; then
  tail -n 25 "$log" >&2
  die "Installation fehlgeschlagen (Log: $log)"
fi
rm -f "$log"

for _ in $(seq 1 30); do
  if curl -fs --max-time 2 "http://127.0.0.1:$(port)/login" >/dev/null; then
    ok "Klassenkasse auf ${BD}$(tr -d '[:space:]' <"$APP_DIR/VERSION")${CL} aktualisiert und läuft"
    exit 0
  fi
  sleep 2
done
journalctl -u klassenkasse -n 30 --no-pager >&2 || true
die "Klassenkasse antwortet nach dem Update nicht (siehe Log oben)"
