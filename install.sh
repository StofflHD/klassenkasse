#!/usr/bin/env bash
# Klassenkasse – einfacher Installer, läuft auf dem Proxmox-Host.
#
# Direkt von GitHub:
#   bash <(curl -fsSL https://raw.githubusercontent.com/StofflHD/klassenkasse/main/install.sh)
# oder aus einer lokalen Kopie des Projekts: bash install.sh
#
#   bash install.sh              Installation: legt den LXC an und richtet alles ein
#   bash install.sh --update     App aktualisieren, Daten und Konfiguration bleiben
#   bash install.sh --uninstall  Container (nach Rückfrage) löschen
#   -y / --yes                   nichts fragen, Standardwerte / vorgegebene Variablen nehmen
#
# Jede Frage kann vorgegeben werden, z. B. unbeaufsichtigt:
#   KK_CTID=150 KK_KLASSE="Klassenkasse 7b" KK_NET=192.168.1.60/24 bash install.sh -y
# GitHub:    KK_REPO (Standard StofflHD/klassenkasse) KK_REF (Branch/Tag, Standard main)
# Variablen: KK_CTID KK_HOSTNAME KK_ROOTFS_STORAGE KK_TEMPLATE_STORAGE KK_BRIDGE
#            KK_NET (dhcp | 192.168.1.60/24) KK_GW KK_KLASSE
#            KK_USER KK_PASSWORD (Login des ersten Administrators; mit -y ohne Passwort wird eins erzeugt)
#            KK_ROOT_PASSWORD (root-Passwort des Containers; mit -y und leer hat er keins)
set -euo pipefail

APP_DIR=/opt/klassenkasse
MARK=klassenkasse
PORT=8000
# pct exec hat einen knappen PATH ohne /usr/local/bin – daher immer mit vollem Pfad
ADMIN_CMD=/usr/local/bin/klassenkasse-admin
LOG=/var/log/klassenkasse-install.log

REPO="${KK_REPO:-StofflHD/klassenkasse}"
REF="${KK_REF:-main}"
ONELINER="bash <(curl -fsSL https://raw.githubusercontent.com/$REPO/$REF/install.sh)"

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORIG_ARGS=("$@")

RD=$'\e[31m' GN=$'\e[32m' YW=$'\e[33m' BL=$'\e[36m' BD=$'\e[1m' CL=$'\e[0m'
info() { echo -e "${BL}➜${CL} $*"; }
ok()   { echo -e "${GN}✔${CL} $*"; }
warn() { echo -e "${YW}⚠${CL} $*"; }
die()  { echo -e "${RD}✘ $*${CL}" >&2; exit 1; }

YES=0
ACTION=install
for a in "$@"; do
  case "$a" in
    -y | --yes) YES=1 ;;
    --update) ACTION=update ;;
    --uninstall) ACTION=uninstall ;;
    -h | --help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "Unbekannte Option: $a (siehe --help)" ;;
  esac
done

# ask VAR "Frage" Standard – behält ein vorgegebenes $VAR, fragt sonst (Enter = Standard)
ask() {
  local var=$1 question=$2 def=$3 answer
  [[ -n "${!var:-}" ]] && return 0
  if [[ $YES == 1 ]]; then
    printf -v "$var" '%s' "$def"
    return 0
  fi
  read -r -p "${YW}?${CL} $question [${BD}${def}${CL}]: " answer </dev/tty
  printf -v "$var" '%s' "${answer:-$def}"
}

confirm() {
  [[ $YES == 1 ]] && return 0
  local a
  read -r -p "${YW}?${CL} $1 [j/N]: " a </dev/tty
  [[ "$a" =~ ^[jJyY]$ ]]
}

# einen Schritt ausführen, Ausgabe geht nach $LOG; bei Fehler das Ende davon zeigen
step() {
  local msg=$1
  shift
  info "$msg …"
  if ! "$@" >>"$LOG" 2>&1; then
    echo
    tail -n 25 "$LOG" >&2
    die "$msg fehlgeschlagen (vollständiges Log: $LOG)"
  fi
  ok "$msg"
}

# C.UTF-8: der Host reicht sein LANG weiter (z. B. de_DE.UTF-8), das im
# Debian-Template fehlt – sonst warnt jeder apt-/perl-Aufruf
ct_exec() { pct exec "$CTID" -- env LANG=C.UTF-8 LC_ALL=C.UTF-8 bash -c "$1"; }

# Passwort zweimal abfragen (min. 8 Zeichen); leere Eingabe = $3 (generate|none)
GENERATED_PW=0
ask_secret() {
  local var=$1 prompt=$2 empty=$3 p1 p2
  while true; do
    read -r -s -p "${YW}?${CL} $prompt: " p1 </dev/tty
    echo
    if [[ -z $p1 ]]; then
      if [[ $empty == generate ]]; then
        printf -v "$var" '%s' "$(openssl rand -hex 8)"
        GENERATED_PW=1
      fi
      return 0
    fi
    if ((${#p1} < 8)); then
      warn "Mindestens 8 Zeichen"
      continue
    fi
    read -r -s -p "${YW}?${CL} Wiederholen: " p2 </dev/tty
    echo
    if [[ $p1 == "$p2" ]]; then
      printf -v "$var" '%s' "$p1"
      return 0
    fi
    warn "Die Passwörter stimmen nicht überein"
  done
}

# Login des ersten Administrators: vorgegeben, zweimal eingetippt oder zufällig
ask_password() {
  if [[ -n ${KK_PASSWORD:-} ]]; then
    ((${#KK_PASSWORD} >= 8)) || die "KK_PASSWORD braucht mindestens 8 Zeichen"
    return 0
  fi
  if [[ $YES == 1 ]]; then
    KK_PASSWORD=$(openssl rand -hex 8)
    GENERATED_PW=1
    return 0
  fi
  ask_secret KK_PASSWORD "Passwort für die Web-Oberfläche (leer = zufälliges erzeugen)" generate
}

# root-Passwort des Containers: vorgegeben, zweimal eingetippt oder keins
ROOT_PW_SET=0
ask_root_password() {
  if [[ -n ${KK_ROOT_PASSWORD:-} ]]; then
    ((${#KK_ROOT_PASSWORD} >= 8)) || die "KK_ROOT_PASSWORD braucht mindestens 8 Zeichen"
    ROOT_PW_SET=1
    return 0
  fi
  [[ $YES == 1 ]] && return 0
  ask_secret KK_ROOT_PASSWORD "root-Passwort für den Container (leer = keins, Zugang per 'pct enter')" none
  [[ -n ${KK_ROOT_PASSWORD:-} ]] && ROOT_PW_SET=1
  return 0
}

# über stdin an chpasswd, nicht pct create --password (wäre in ps sichtbar)
set_root_password() {
  printf 'root:%s\n' "$KK_ROOT_PASSWORD" | pct exec "$CTID" -- chpasswd
}

# Passwort über stdin, nie als Argument (wäre in ps / im Log sichtbar)
set_login() {
  printf '%s\n' "$KK_PASSWORD" |
    pct exec "$CTID" -- env LANG=C.UTF-8 LC_ALL=C.UTF-8 \
      "$ADMIN_CMD" create-user "$KK_USER" --role admin --password-stdin
}

print_login() {
  if [[ $GENERATED_PW == 1 ]]; then
    echo -e "  Login:          ${BD}$KK_USER${CL} / ${BD}$KK_PASSWORD${CL}  ${YW}(jetzt notieren, es wird nicht gespeichert)${CL}"
  else
    echo -e "  Login:          ${BD}$KK_USER${CL} mit deinem Passwort"
  fi
  echo "  Neues Passwort: in der Web-Oberfläche (Klick auf den Benutzernamen) oder"
  echo "                  pct exec $CTID -- $ADMIN_CMD create-user $KK_USER --role admin"
}

storages() { pvesm status --content "$1" 2>/dev/null | awk 'NR>1 && $3=="active" {print $1, $2}'; }

# erster Storage mit Inhaltstyp $1, bevorzugt Name $2 / Typ $3
pick_storage() {
  local list
  list=$(storages "$1")
  { echo "$list" | awk -v n="${2:-}" '$1==n {print $1}'
    echo "$list" | awk -v t="${3:-}" '$2==t {print $1}'
    echo "$list" | awk '{print $1}'
  } | grep -m1 . || true
}

require_storage() {
  pvesm status --storage "$1" >/dev/null 2>&1 || die "Storage '$1' gibt es nicht"
}

# Container mit dem Tag "klassenkasse" auf diesem Node
installed_ctids() {
  local id
  for id in $(pct list 2>/dev/null | awk 'NR>1 {print $1}'); do
    pct config "$id" 2>/dev/null | grep -qE "^tags:.*(^|[ ;,])$MARK([ ;,]|\$)" && echo "$id"
  done
  return 0
}

# --- Bausteine --------------------------------------------------------------

pick_template() {
  pveam update >>"$LOG" 2>&1 || warn "pveam update fehlgeschlagen, nehme die vorhandene Template-Liste"
  local v t
  for v in 13 12; do
    t=$(pveam available --section system | awk '{print $2}' | grep -E "^debian-$v-standard_.*_amd64" | sort -V | tail -n1)
    if [[ -n $t ]]; then
      echo "$t"
      return 0
    fi
  done
  die "Kein Debian-Template gefunden (pveam available --section system)"
}

create_ct() {
  local net="name=eth0,bridge=$KK_BRIDGE,ip=$KK_NET"
  [[ $KK_NET != dhcp && -n ${KK_GW:-} ]] && net+=",gw=$KK_GW"
  pct create "$CTID" "$KK_TEMPLATE_STORAGE:vztmpl/$TEMPLATE" \
    --hostname "$KK_HOSTNAME" --cores 1 --memory 512 --swap 512 \
    --rootfs "$KK_ROOTFS_STORAGE:2" --net0 "$net" \
    --unprivileged 1 --features nesting=1 --onboot 1 \
    --tags "$MARK" --description "Klassenkasse (Web-Oberfläche Port $PORT)"
  pct start "$CTID"
}

wait_for_network() {
  local i
  for i in $(seq 1 60); do
    ct_exec "getent hosts deb.debian.org" >/dev/null 2>&1 && return 0
    sleep 2
  done
  echo "Container $CTID hat nach 2 Minuten kein Netz/DNS" >&2
  return 1
}

# Projekt in den CT kopieren und dort den Installer ausführen
push_app() {
  local tgz klasse=""
  [[ -n ${KK_KLASSE:-} ]] && klasse="KK_KLASSE=$(printf '%q' "$KK_KLASSE")"
  tgz=$(mktemp --suffix=.tar.gz)
  tar -czf "$tgz" -C "$SRC" --exclude=./venv --exclude=./.venv --exclude=./.git \
    --exclude=__pycache__ --exclude='*.db' --exclude='*.zip' --exclude=./_src .
  pct push "$CTID" "$tgz" /tmp/kk-src.tar.gz
  rm -f "$tgz"
  ct_exec "rm -rf /tmp/kk-src && mkdir -p /tmp/kk-src && tar -xzf /tmp/kk-src.tar.gz -C /tmp/kk-src \
    && $klasse bash /tmp/kk-src/deploy/install.sh --quiet; rc=\$?; rm -rf /tmp/kk-src /tmp/kk-src.tar.gz; exit \$rc"
}

# /login ist ohne Anmeldung erreichbar
wait_for_web() {
  local i
  for i in $(seq 1 30); do
    ct_exec "curl -fs --max-time 2 http://127.0.0.1:$PORT/login" >/dev/null 2>&1 && return 0
    sleep 2
  done
  ct_exec "journalctl -u klassenkasse -n 30 --no-pager" >&2 || true
  return 1
}

ct_ip() { pct exec "$CTID" -- hostname -I 2>/dev/null | awk '{print $1}'; }

banner() {
  echo -e "\n${BD}Klassenkasse${CL} – $1\n"
  echo "Log: $LOG" >"$LOG"
}

# --- Aktionen ---------------------------------------------------------------

do_install() {
  banner "Installation"

  ask KK_CTID "Container-ID" "$(pvesh get /cluster/nextid)"
  CTID=$KK_CTID
  [[ $CTID =~ ^[0-9]+$ ]] || die "Ungültige Container-ID"
  pct status "$CTID" >/dev/null 2>&1 && die "CT $CTID gibt es schon. Zum Aktualisieren: $ONELINER --update"

  ask KK_HOSTNAME "Hostname" "klassenkasse"
  ask KK_ROOTFS_STORAGE "Storage für den Container" "$(pick_storage rootdir local-lvm lvmthin)"
  require_storage "$KK_ROOTFS_STORAGE"
  ask KK_TEMPLATE_STORAGE "Storage für das Debian-Template" "$(pick_storage vztmpl local)"
  require_storage "$KK_TEMPLATE_STORAGE"
  ask KK_BRIDGE "Netzwerk-Bridge" "vmbr0"
  ip link show "$KK_BRIDGE" >/dev/null 2>&1 || die "Bridge '$KK_BRIDGE' gibt es nicht"
  ask KK_NET "IP-Adresse (dhcp oder z. B. 192.168.1.60/24)" "dhcp"
  [[ $KK_NET == dhcp ]] || ask KK_GW "Gateway" "$(ip -4 route show default | awk '{print $3; exit}')"

  echo
  ask KK_KLASSE "Name der Klasse (Titel in der Web-Oberfläche)" "Klassenkasse"
  [[ $KK_KLASSE != *[\"\\\$\`]* ]] || die "Klassenname darf kein \" \\ \$ oder \` enthalten"
  ask KK_USER "Benutzername des ersten Administrators" "admin"
  [[ $KK_USER =~ ^[A-Za-z0-9._-]{1,50}$ ]] || die "Benutzername: nur Buchstaben, Ziffern, . _ -"
  ask_password
  ask_root_password

  echo -e "\n${BD}Zusammenfassung${CL}
  Container   $CTID ($KK_HOSTNAME), 1 CPU, 512 MB RAM, 2 GB auf $KK_ROOTFS_STORAGE
  Netzwerk    $KK_BRIDGE, $KK_NET${KK_GW:+, Gateway $KK_GW}
  Klasse      $KK_KLASSE
  Login       $KK_USER (Administrator)
  root-Login  $([[ $ROOT_PW_SET == 1 ]] && echo "Passwort gesetzt" || echo "kein Passwort (pct enter $CTID)")\n"
  confirm "Installation starten?" || die "Abgebrochen"
  echo

  TEMPLATE=$(pick_template)
  if ! pveam list "$KK_TEMPLATE_STORAGE" | grep -q "$TEMPLATE"; then
    step "Template $TEMPLATE herunterladen" pveam download "$KK_TEMPLATE_STORAGE" "$TEMPLATE"
  fi
  step "Container $CTID anlegen und starten" create_ct
  [[ $ROOT_PW_SET == 1 ]] && step "root-Passwort setzen" set_root_password
  step "Auf Netzwerk warten" wait_for_network
  step "App installieren (dauert 1–3 Minuten)" push_app
  step "Administrator anlegen" set_login
  step "Dienst starten" ct_exec "systemctl restart klassenkasse"
  step "Web-Oberfläche prüfen" wait_for_web

  echo -e "\n${GN}${BD}Fertig!${CL} Klassenkasse: ${BD}http://$(ct_ip):$PORT${CL}"
  print_login
  if [[ $ROOT_PW_SET == 1 ]]; then
    echo "  root-Shell:     Konsole oder pct enter $CTID (root mit deinem Passwort)"
  else
    echo "  root-Shell:     pct enter $CTID (kein root-Passwort; später: pct exec $CTID -- passwd)"
  fi
  echo "  Einstellungen:  pct exec $CTID -- nano /etc/klassenkasse.env  (danach: pct exec $CTID -- systemctl restart klassenkasse)"
  echo "  Sicherung:      täglich 02:30 nach /var/lib/klassenkasse/backup (30 Tage)"
  echo "  Update:         update  (im Container: pct enter $CTID) oder hier auf dem Host:"
  echo "                  $ONELINER --update"
  echo -e "  ${YW}Die Verbindung ist unverschlüsselt (HTTP) – nur im Heimnetz oder hinter einem HTTPS-Reverse-Proxy nutzen.${CL}"
}

do_update() {
  banner "Update"
  local found
  found=$(installed_ctids | head -n1)
  ask KK_CTID "Container-ID der Installation" "${found:-}"
  CTID=$KK_CTID
  [[ $CTID =~ ^[0-9]+$ ]] || die "Ungültige Container-ID"
  pct config "$CTID" >/dev/null 2>&1 || die "CT $CTID gibt es nicht"
  pct status "$CTID" | grep -q running || step "Container $CTID starten" pct start "$CTID"
  pct exec "$CTID" -- sh -c "test -f $APP_DIR/app/app.py || test -f $APP_DIR/app.py" ||
    die "In CT $CTID ist keine Klassenkasse installiert"
  # ältere Installationen (aus dem Zip) haben noch keinen Tag
  local tags
  tags=$(pct config "$CTID" | sed -n 's/^tags: //p')
  [[ $tags == *$MARK* ]] || pct set "$CTID" --tags "${tags:+$tags;}$MARK"

  local before
  before=$(pct exec "$CTID" -- cat "$APP_DIR/VERSION" 2>/dev/null || echo "alt")
  step "Auf Netzwerk warten" wait_for_network
  step "Datenbank sichern" ct_exec "[ ! -f /var/lib/klassenkasse/klassenkasse.db ] || \
    $ADMIN_CMD backup /var/lib/klassenkasse/backup/vor-update_${before}_\$(date +%F_%H%M).db"
  step "App aktualisieren (Daten und Konfiguration bleiben)" push_app
  # z. B. wenn eine Installation vor dem Anlegen des Administrators abgebrochen ist
  local need_login=0
  if [[ $(pct exec "$CTID" -- "$ADMIN_CMD" count-users 2>/dev/null | tail -n1) == 0 ]]; then
    need_login=1
    warn "Es gibt noch keinen Benutzer – bitte jetzt den ersten Administrator anlegen"
    ask KK_USER "Benutzername des ersten Administrators" "admin"
    [[ $KK_USER =~ ^[A-Za-z0-9._-]{1,50}$ ]] || die "Benutzername: nur Buchstaben, Ziffern, . _ -"
    ask_password
    step "Administrator anlegen" set_login
  fi
  step "Web-Oberfläche prüfen" wait_for_web
  echo -e "\n${GN}${BD}Update fertig:${CL} $before → $(pct exec "$CTID" -- cat "$APP_DIR/VERSION")  http://$(ct_ip):$PORT"
  [[ $need_login == 1 ]] && print_login
  return 0
}

do_uninstall() {
  banner "Deinstallation"
  local found a
  found=$(installed_ctids | head -n1)
  ask KK_CTID "Container-ID der Installation" "${found:-}"
  CTID=$KK_CTID
  [[ $CTID =~ ^[0-9]+$ ]] || die "Ungültige Container-ID"
  pct config "$CTID" >/dev/null 2>&1 || die "CT $CTID gibt es nicht"
  pct config "$CTID" | grep -qE "^tags:.*$MARK" || warn "CT $CTID hat nicht den Tag '$MARK' – ist das wirklich die Klassenkasse?"

  # nie vorausgewählt, auch nicht mit -y
  warn "Damit werden alle Buchungen, Schüler/innen und Sicherungen im Container gelöscht."
  read -r -p "${YW}?${CL} Container $CTID samt Daten endgültig löschen? Zur Bestätigung die ID eintippen: " a </dev/tty || a=
  if [[ $a == "$CTID" ]]; then
    pct status "$CTID" | grep -q running && step "Container stoppen" pct stop "$CTID"
    step "Container $CTID löschen" pct destroy "$CTID" --purge
  else
    info "Container $CTID bleibt erhalten"
  fi
}

# Per curl gestartet, liegen die Projektdateien nicht neben dem Skript:
# Repo herunterladen und den Installer von dort erneut starten.
fetch_source() {
  local dir
  info "Lade $REPO ($REF) von GitHub …"
  dir=$(mktemp -d /tmp/kk-src.XXXXXX)
  if ! curl -fsSL "https://codeload.github.com/$REPO/tar.gz/$REF" | tar -xz -C "$dir" --strip-components=1; then
    rm -rf "$dir"
    die "Download fehlgeschlagen – Internetverbindung, KK_REPO und KK_REF prüfen"
  fi
  [[ -f $dir/install.sh && -f $dir/app/app.py ]] || die "Heruntergeladenes Archiv ist unvollständig"
  ok "Quellcode geladen"
  KK_FETCHED_SRC="$dir" exec bash "$dir/install.sh" "${ORIG_ARGS[@]}"
}

# --- Start ------------------------------------------------------------------

[[ $EUID -eq 0 ]] || die "Bitte als root ausführen"
command -v pveversion >/dev/null 2>&1 || die "Dieses Skript läuft auf dem Proxmox-Host, nicht im Container"
if [[ $ACTION != uninstall ]]; then
  if [[ ! -f $SRC/app/app.py || ! -f $SRC/deploy/install.sh ]]; then
    [[ -z ${KK_FETCHED_SRC:-} ]] || die "Im heruntergeladenen Archiv fehlen Projektdateien"
    fetch_source
  fi
fi
# heruntergeladene Kopie: danach wieder entfernen
if [[ -n ${KK_FETCHED_SRC:-} && $SRC == "$KK_FETCHED_SRC" ]]; then
  trap 'rm -rf "$KK_FETCHED_SRC"' EXIT
fi

# Von Windows kopiert? CRLF-Zeilenenden würden jedes Skript im Container
# kaputt machen. Das Normalisieren schadet nie, also immer.
if [[ $ACTION != uninstall ]]; then
  find "$SRC/app" "$SRC/deploy" "$SRC/requirements.txt" "$SRC/VERSION" -type f \
    \( -name '*.sh' -o -name '*.py' -o -name '*.service' -o -name '*.timer' -o -name '*.txt' \
    -o -name '*.sql' -o -name '*.css' -o -name '*.html' -o -name VERSION \) -exec sed -i 's/\r$//' {} +
fi

case $ACTION in
  install) do_install ;;
  update) do_update ;;
  uninstall) do_uninstall ;;
esac
