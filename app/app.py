# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 StofflHD
"""Klassenkasse – Web-App zur Verwaltung einer Klassenkasse (Flask + SQLite)."""
import os
import re
import ipaddress
import json
import secrets
import sqlite3
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import wraps

import click
from flask import (Flask, Response, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from markupsafe import Markup
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

import tableio
from proxy import TrustedProxyFix, parse_trusted
from tableio import euro_plain

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def read_version():
    try:
        with open(os.path.join(BASE_DIR, "..", "VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "dev"


VERSION = read_version()

app = Flask(__name__)
app.config.update(
    DATABASE=os.environ.get("KK_DB", os.path.join(BASE_DIR, "klassenkasse.db")),
    SECRET_KEY=os.environ.get("KK_SECRET") or secrets.token_hex(32),
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("KK_COOKIE_SECURE") == "1",
    KLASSE=os.environ.get("KK_KLASSE", "Klassenkasse"),
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,     # Uploads (Import)
    MAX_FORM_MEMORY_SIZE=5 * 1024 * 1024,   # Bestätigung eines großen Imports
)
# Reverse-Proxy: KK_TRUSTED_PROXIES nennt die Proxys, deren X-Forwarded-* geglaubt wird.
# KK_BEHIND_PROXY=1 allein (bis 0.6.0) glaubt den Headern von jedem – nur noch als Notlösung.
TRUSTED_PROXIES = parse_trusted(os.environ.get("KK_TRUSTED_PROXIES"))
if TRUSTED_PROXIES:
    PROXY_MODE = "trusted"
    app.wsgi_app = TrustedProxyFix(app.wsgi_app, TRUSTED_PROXIES)
elif os.environ.get("KK_BEHIND_PROXY") == "1":
    PROXY_MODE = "any"
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.logger.warning("KK_BEHIND_PROXY=1 ohne KK_TRUSTED_PROXIES: X-Forwarded-For wird von "
                       "jedem geglaubt, die IP-Sperre lässt sich am Proxy vorbei umgehen.")
else:
    PROXY_MODE = "off"

# Brute-Force-Schutz: nach so vielen Fehlversuchen (innerhalb von 24 h, seit der letzten
# erfolgreichen Anmeldung) wird die IP-Adresse gesperrt, bis ein Administrator sie freigibt
try:
    MAX_LOGIN_FAILURES = max(1, int(os.environ.get("KK_MAX_LOGIN_FAILURES", "3")))
except ValueError:
    MAX_LOGIN_FAILURES = 3

ROLES = {"lesen": 0, "kasse": 1, "admin": 2}
ROLE_LABELS = {"lesen": "Nur lesen", "kasse": "Kassenwart", "admin": "Administrator"}
MAX_CENTS = 100_000_000  # 1 Mio. € als Plausibilitätsgrenze

BOOKING_SELECT = """
    SELECT b.*, s.name AS student_name, c.title AS collection_title
    FROM bookings b
    LEFT JOIN students s ON s.id = b.student_id
    LEFT JOIN collections c ON c.id = b.collection_id
"""


# ---------------------------------------------------------------- Datenbank
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"], timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    os.makedirs(os.path.dirname(os.path.abspath(app.config["DATABASE"])), exist_ok=True)
    db = sqlite3.connect(app.config["DATABASE"])
    with open(os.path.join(BASE_DIR, "schema.sql"), encoding="utf-8") as f:
        db.executescript(f.read())
    migrate(db)
    db.close()


# Erziehungsberechtigte: je zwei Personen mit eigenen Daten, Spalten g1_*, g2_*
GUARDIAN_FIELDS = [
    ("name", "Name", 100),
    ("phone", "Telefon", 80),
    ("email", "E-Mail", 120),
    ("address", "Anschrift, falls abweichend", 200),
]
GUARDIAN_COLUMNS = [f"g{n}_{k}" for n in (1, 2) for k, _l, _m in GUARDIAN_FIELDS]


def columns(db, table):
    return {r[1] for r in db.execute(f"PRAGMA table_info({table})")}


def join_phones(a, b):
    """SQL-Ausdruck: zwei Nummernspalten zu einer, getrennt mit " / "."""
    return f"CASE WHEN {b} = '' THEN {a} WHEN {a} = '' THEN {b} ELSE {a} || ' / ' || {b} END"


def migrate(db):
    """Ältere Datenbanken auf den Stand von schema.sql bringen.

    Läuft in einer Schreibtransaktion: starten Dienst und klassenkasse-admin
    gleichzeitig, wartet der zweite und findet alles schon erledigt.
    """
    db.isolation_level = None
    db.execute("BEGIN IMMEDIATE")
    try:
        cols = columns(db, "students")
        if "g1_name" not in cols:
            # 0.1.x: noch keine Kontaktfelder; 0.2.0: eine Spalte für alle Eltern
            for col in ("street", "zip", "city", "notes", "guardians", "phone", "phone2", "email"):
                if col not in cols:
                    db.execute(f"ALTER TABLE students ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
            for col in GUARDIAN_COLUMNS:
                db.execute(f"ALTER TABLE students ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
            # Daten aus 0.2.0 verlustfrei nach Erziehungsberechtigte/r 1 übernehmen
            db.execute(f"""UPDATE students SET g1_name = guardians, g1_email = email,
                                               g1_phone = {join_phones('phone', 'phone2')}""")
        if "g1_mobile" in cols:
            # 0.3.0 hatte Telefon und Mobil getrennt: in Telefon zusammenführen. Die
            # Spalte g*_mobile bleibt ungenutzt stehen und wird geleert, damit ein
            # erneuter Lauf nichts doppelt anhängt.
            for n in (1, 2):
                db.execute(f"""UPDATE students SET g{n}_phone = {join_phones(f'g{n}_phone', f'g{n}_mobile')},
                                                   g{n}_mobile = '' WHERE g{n}_mobile != ''""")
        if "birthday" in cols:
            # Geburtstage werden seit 0.7.0 nicht mehr erfasst – gespeicherte Werte löschen
            # (Datensparsamkeit). Die Sicherung vor dem Update enthält sie noch.
            db.execute("UPDATE students SET birthday = NULL WHERE birthday IS NOT NULL")
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise


init_db()


# ---------------------------------------------------------------- Hilfsfunktionen
def parse_euro(text):
    """'12,50' / '12.50' / '1.234,56 €' -> Cent als int."""
    s = (text or "").strip().replace("€", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        value = Decimal(s)
    except InvalidOperation:
        raise ValueError("Ungültiger Betrag.")
    if not value.is_finite() or value <= 0 or value.as_tuple().exponent < -2:
        raise ValueError("Betrag muss positiv sein und darf höchstens 2 Nachkommastellen haben.")
    cents = int(value * 100)
    if cents > MAX_CENTS:
        raise ValueError("Betrag ist unplausibel hoch.")
    return cents


def parse_date(text, default_today=True):
    text = (text or "").strip()
    if not text:
        return date.today().isoformat() if default_today else None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise ValueError("Ungültiges Datum.")


def opt_int(text):
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        raise ValueError("Ungültige Auswahl.")


def euro(cents):
    return euro_plain(cents) + " €"


def date_de(iso):
    if not iso:
        return ""
    try:
        return date.fromisoformat(iso[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return iso


app.jinja_env.filters["euro"] = euro
app.jinja_env.filters["euro_plain"] = euro_plain
app.jinja_env.filters["date_de"] = date_de


def safe_next(target, fallback):
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return fallback


def export_response(fmt, basename, columns, rows, title):
    """Tabelle als CSV oder Excel ausliefern; columns = [(Überschrift, Art), …]."""
    if fmt == "xlsx":
        data, mime = tableio.to_xlsx(columns, rows, title), tableio.XLSX_MIME
    elif fmt == "csv":
        data, mime = tableio.to_csv(columns, rows), "text/csv; charset=utf-8"
    else:
        abort(404)
    return Response(data, mimetype=mime,
                    headers={"Content-Disposition": f"attachment; filename={basename}.{fmt}"})


# ---------------------------------------------------------------- Login, Rollen, CSRF
def can(role):
    user = g.get("user")
    return bool(user) and ROLES[user["role"]] >= ROLES[role]


# ---------------------------------------------------------------- Brute-Force-Schutz
def client_ip():
    """IP-Adresse des Aufrufers (hinter einem Reverse-Proxy nur mit KK_TRUSTED_PROXIES richtig)."""
    return request.remote_addr or ""


def parse_network(text):
    """'192.168.1.20', '2001:db8::1' oder '10.0.0.0/24' -> normalisierte Schreibweise."""
    text = (text or "").strip()
    try:
        if "/" in text:
            net = ipaddress.ip_network(text, strict=False)
            return str(net.network_address) if net.num_addresses == 1 else str(net)
        return str(ipaddress.ip_address(text))
    except ValueError:
        raise ValueError(f"Keine gültige IP-Adresse oder kein gültiges Netz: {text}")


def blocking_entry(db, ip):
    """Der Sperreintrag, der diese IP-Adresse erfasst – oder None."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    for row in db.execute("SELECT * FROM ip_blocks").fetchall():
        try:
            if addr in ipaddress.ip_network(row["ip"], strict=False):
                return row
        except ValueError:
            continue
    return None


def record_failure(db, ip, username):
    """Fehlversuch speichern; gibt die Zahl der Fehlversuche zurück und sperrt bei Bedarf."""
    db.execute("DELETE FROM login_failures WHERE at < datetime('now', 'localtime', '-30 days')")
    db.execute("INSERT INTO login_failures (ip, username) VALUES (?, ?)", (ip, username[:50]))
    count = db.execute("""SELECT COUNT(*) FROM login_failures WHERE ip = ?
                          AND at >= datetime('now', 'localtime', '-1 day')""", (ip,)).fetchone()[0]
    if count >= MAX_LOGIN_FAILURES and blocking_entry(db, ip) is None:
        db.execute("""INSERT OR IGNORE INTO ip_blocks (ip, reason, created_by) VALUES (?, ?, ?)""",
                   (ip, f"{count} fehlgeschlagene Anmeldungen, zuletzt als „{username[:50]}“",
                    "automatisch"))
    db.commit()
    return count


@app.before_request
def before():
    g.user = None
    if request.endpoint != "static":
        block = blocking_entry(get_db(), client_ip())
        if block is not None:
            return render_template("blocked.html", ip=client_ip(), block=block), 403
    uid = session.get("uid")
    if uid:
        g.user = get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if g.user is None:
            session.clear()
    if request.method == "POST":
        token = session.get("csrf")
        if not token or not secrets.compare_digest(token, request.form.get("csrf", "")):
            abort(400)


@app.context_processor
def inject():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return {
        "user": g.get("user"),
        "klasse": app.config["KLASSE"],
        "can": can,
        "ROLE_LABELS": ROLE_LABELS,
        "csrf_field": Markup(f'<input type="hidden" name="csrf" value="{session["csrf"]}">'),
        "today": date.today().isoformat(),
        "version": VERSION,
    }


def role_required(min_role):
    def deco(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if g.user is None:
                return redirect(url_for("login", next=request.path))
            if not can(min_role):
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return deco


login_required = role_required("lesen")


@app.route("/login", methods=["GET", "POST"])
def login():
    db = get_db()
    no_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        u = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if u and check_password_hash(u["pw_hash"], request.form.get("password", "")):
            db.execute("DELETE FROM login_failures WHERE ip = ?", (client_ip(),))
            db.commit()
            session.clear()
            session["uid"] = u["id"]
            return redirect(safe_next(request.args.get("next"), url_for("index")))
        count = record_failure(db, client_ip(), username)
        left = MAX_LOGIN_FAILURES - count
        if left <= 0:
            app.logger.warning("IP %s nach %d Fehlversuchen gesperrt", client_ip(), count)
            return redirect(url_for("login"))  # zeigt jetzt die Sperrseite
        flash("Benutzername oder Passwort falsch. "
              + (f"Noch {left} Versuche, dann wird diese IP-Adresse gesperrt." if left > 1
                 else "Noch 1 Versuch, dann wird diese IP-Adresse gesperrt."), "error")
    return render_template("login.html", no_users=no_users)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/passwort", methods=["GET", "POST"])
@login_required
def password():
    if request.method == "POST":
        old, new = request.form.get("old", ""), request.form.get("new", "")
        if not check_password_hash(g.user["pw_hash"], old):
            flash("Das bisherige Passwort stimmt nicht.", "error")
        elif len(new) < 8:
            flash("Das neue Passwort muss mindestens 8 Zeichen haben.", "error")
        elif new != request.form.get("new2", ""):
            flash("Die neuen Passwörter stimmen nicht überein.", "error")
        else:
            db = get_db()
            db.execute("UPDATE users SET pw_hash = ? WHERE id = ?",
                       (generate_password_hash(new), g.user["id"]))
            db.commit()
            flash("Passwort geändert.", "ok")
            return redirect(url_for("index"))
    return render_template("password.html")


# ---------------------------------------------------------------- Auswertungen
def totals(db):
    r = db.execute("""
        SELECT COALESCE(SUM(CASE WHEN kind = 'in'  THEN amount_cents END), 0) AS ein,
               COALESCE(SUM(CASE WHEN kind = 'out' THEN amount_cents END), 0) AS aus
        FROM bookings WHERE cancelled_at IS NULL""").fetchone()
    return r["ein"], r["aus"], r["ein"] - r["aus"]


def collection_status(db, col):
    """Für jede Schülerin/jeden Schüler: bezahlt / offen bei dieser Sammlung."""
    rows = db.execute("""
        SELECT s.id, s.name, s.active, COALESCE(SUM(b.amount_cents), 0) AS paid
        FROM students s
        LEFT JOIN bookings b ON b.student_id = s.id AND b.collection_id = ?
             AND b.kind = 'in' AND b.cancelled_at IS NULL
        GROUP BY s.id ORDER BY s.name COLLATE NOCASE""", (col["id"],)).fetchall()
    items = []
    for r in rows:
        if not r["active"] and r["paid"] == 0:
            continue
        open_ = max(col["amount_cents"] - r["paid"], 0) if r["active"] else 0
        items.append({"id": r["id"], "name": r["name"], "active": r["active"],
                      "paid": r["paid"], "open": open_})
    return items


def collection_summary(db, col):
    items = collection_status(db, col)
    open_items = [i for i in items if i["open"] > 0]
    return {"c": col, "rows": items, "total": len(items),
            "open_count": len(open_items),
            "open_sum": sum(i["open"] for i in open_items),
            "paid_sum": sum(i["paid"] for i in items)}


def form_lists(db):
    return {
        "all_students": db.execute(
            "SELECT id, name FROM students WHERE active = 1 ORDER BY name COLLATE NOCASE").fetchall(),
        "open_collections": db.execute(
            "SELECT id, title, amount_cents FROM collections WHERE closed = 0 ORDER BY id DESC").fetchall(),
    }


def get_or_404(db, table, id_):
    row = db.execute(f"SELECT * FROM {table} WHERE id = ?", (id_,)).fetchone()
    if row is None:
        abort(404)
    return row


# ---------------------------------------------------------------- Übersicht
@app.route("/")
@login_required
def index():
    db = get_db()
    ein, aus, stand = totals(db)
    cols = db.execute("""SELECT * FROM collections WHERE closed = 0
                         ORDER BY due_date IS NULL, due_date, id""").fetchall()
    summaries = [collection_summary(db, c) for c in cols]
    recent = db.execute(BOOKING_SELECT + " ORDER BY b.booking_date DESC, b.id DESC LIMIT 10").fetchall()
    return render_template("index.html", ein=ein, aus=aus, stand=stand,
                           summaries=summaries, recent=recent, **form_lists(db))


# ---------------------------------------------------------------- Buchungen
def read_booking_form(db, f):
    kind = f.get("kind")
    if kind not in ("in", "out"):
        raise ValueError("Ungültige Buchungsart.")
    amount = parse_euro(f.get("amount"))
    bdate = parse_date(f.get("date"))
    sid, cid = opt_int(f.get("student_id")), opt_int(f.get("collection_id"))
    if sid is not None:
        get_or_404(db, "students", sid)
    col = get_or_404(db, "collections", cid) if cid is not None else None
    purpose = (f.get("purpose") or "").strip()[:200]
    if not purpose and col:
        purpose = col["title"]
    if not purpose:
        raise ValueError("Bitte einen Zweck angeben.")
    return {"kind": kind, "amount": amount, "bdate": bdate, "sid": sid, "cid": cid, "purpose": purpose}


def insert_booking(db, kind, amount, bdate, sid, cid, purpose):
    db.execute("""INSERT INTO bookings (booking_date, kind, amount_cents, purpose,
                                        student_id, collection_id, created_by)
                  VALUES (?, ?, ?, ?, ?, ?, ?)""",
               (bdate, kind, amount, purpose, sid, cid, g.user["username"]))
    db.commit()


@app.route("/buchungen", methods=["GET", "POST"])
@login_required
def bookings():
    db = get_db()
    if request.method == "POST":
        if not can("kasse"):
            abort(403)
        try:
            insert_booking(db, **read_booking_form(db, request.form))
            flash("Buchung gespeichert.", "ok")
        except ValueError as e:
            flash(str(e), "error")
        return redirect(safe_next(request.form.get("back"), url_for("bookings")))

    show_cancelled = request.args.get("storniert") == "1"
    where = "" if show_cancelled else " WHERE b.cancelled_at IS NULL"
    rows = db.execute(BOOKING_SELECT + where + " ORDER BY b.booking_date DESC, b.id DESC").fetchall()
    ein, aus, stand = totals(db)
    return render_template("bookings.html", rows=rows, show_cancelled=show_cancelled,
                           ein=ein, aus=aus, stand=stand, **form_lists(db))


@app.route("/buchungen/<int:bid>/storno", methods=["POST"])
@role_required("kasse")
def cancel_booking(bid):
    db = get_db()
    get_or_404(db, "bookings", bid)
    reason = request.form.get("reason", "").strip()[:200]
    if not reason:
        flash("Bitte einen Grund für das Storno angeben.", "error")
    else:
        cur = db.execute("""UPDATE bookings SET cancelled_at = ?, cancelled_by = ?, cancel_reason = ?
                            WHERE id = ? AND cancelled_at IS NULL""",
                         (datetime.now().strftime("%Y-%m-%d %H:%M"), g.user["username"], reason, bid))
        db.commit()
        flash("Buchung storniert." if cur.rowcount else "Buchung war bereits storniert.", "ok")
    return redirect(safe_next(request.form.get("back"), url_for("bookings")))


@app.route("/export/buchungen.<fmt>")
@login_required
def export_bookings(fmt):
    rows = get_db().execute(BOOKING_SELECT + " ORDER BY b.booking_date, b.id").fetchall()
    return export_response(
        fmt, f"buchungen_{date.today().isoformat()}",
        [("Nr", "int"), ("Datum", "date"), ("Art", "text"), ("Betrag", "euro"), ("Zweck", "text"),
         ("Schüler/in", "text"), ("Sammlung", "text"), ("Erfasst von", "text"),
         ("Erfasst am", "datetime"), ("Storniert am", "datetime"), ("Storniert von", "text"),
         ("Storno-Grund", "text")],
        [[r["id"], r["booking_date"], "Einnahme" if r["kind"] == "in" else "Ausgabe",
          r["amount_cents"] if r["kind"] == "in" else -r["amount_cents"],
          r["purpose"], r["student_name"], r["collection_title"], r["created_by"], r["created_at"],
          r["cancelled_at"], r["cancelled_by"], r["cancel_reason"]] for r in rows],
        "Buchungen")


# ---------------------------------------------------------------- Sammlungen
@app.route("/sammlungen", methods=["GET", "POST"])
@login_required
def collections():
    db = get_db()
    if request.method == "POST":
        if not can("kasse"):
            abort(403)
        try:
            title = request.form.get("title", "").strip()[:120]
            if not title:
                raise ValueError("Bitte einen Titel angeben.")
            amount = parse_euro(request.form.get("amount"))
            due = parse_date(request.form.get("due_date"), default_today=False)
            db.execute("INSERT INTO collections (title, amount_cents, due_date) VALUES (?, ?, ?)",
                       (title, amount, due))
            db.commit()
            flash(f"Sammlung „{title}“ angelegt.", "ok")
        except ValueError as e:
            flash(str(e), "error")
        return redirect(url_for("collections"))
    cols = db.execute("SELECT * FROM collections ORDER BY closed, id DESC").fetchall()
    return render_template("collections.html", summaries=[collection_summary(db, c) for c in cols])


@app.route("/sammlungen/<int:cid>")
@login_required
def collection(cid):
    db = get_db()
    s = collection_summary(db, get_or_404(db, "collections", cid))
    return render_template("collection.html", s=s)


@app.route("/sammlungen/<int:cid>/zahlung", methods=["POST"])
@role_required("kasse")
def collection_payment(cid):
    db = get_db()
    col = get_or_404(db, "collections", cid)
    try:
        if col["closed"]:
            raise ValueError("Die Sammlung ist abgeschlossen.")
        sid = opt_int(request.form.get("student_id"))
        if sid is None:
            raise ValueError("Keine Schülerin / kein Schüler gewählt.")
        student = get_or_404(db, "students", sid)
        insert_booking(db, "in", parse_euro(request.form.get("amount")),
                       parse_date(request.form.get("date")), sid, cid, col["title"])
        flash(f"Zahlung von {student['name']} gebucht.", "ok")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("collection", cid=cid))


@app.route("/sammlungen/<int:cid>/status", methods=["POST"])
@role_required("kasse")
def collection_toggle(cid):
    db = get_db()
    col = get_or_404(db, "collections", cid)
    db.execute("UPDATE collections SET closed = ? WHERE id = ?", (0 if col["closed"] else 1, cid))
    db.commit()
    flash("Sammlung wieder geöffnet." if col["closed"] else "Sammlung abgeschlossen.", "ok")
    return redirect(url_for("collection", cid=cid))


@app.route("/export/sammlung/<int:cid>.<fmt>")
@login_required
def export_collection(cid, fmt):
    db = get_db()
    s = collection_summary(db, get_or_404(db, "collections", cid))
    return export_response(
        fmt, f"sammlung_{cid}",
        [("Schüler/in", "text"), ("Soll", "euro"), ("Bezahlt", "euro"), ("Offen", "euro")],
        [[i["name"], s["c"]["amount_cents"] if i["active"] else 0, i["paid"], i["open"]]
         for i in s["rows"]],
        s["c"]["title"])


# ---------------------------------------------------------------- Schüler/innen
def open_per_student(db):
    result = {}
    for col in db.execute("SELECT * FROM collections WHERE closed = 0").fetchall():
        for i in collection_status(db, col):
            result[i["id"]] = result.get(i["id"], 0) + i["open"]
    return result


# Felder der Klassenliste außer dem Namen: (Spalte, Bezeichnung, max. Länge)
ADDRESS_FIELDS = [
    ("street", "Straße", 120),
    ("zip", "PLZ", 10),
    ("city", "Ort", 80),
    ("notes", "Notiz", 500),
]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def email_list(text):
    return [a.strip() for a in (text or "").replace(";", ",").split(",") if a.strip()]


def phone_list(text):
    """'089 123 / 0171 456' -> ['089 123', '0171 456'] (jede Nummer einzeln anrufbar)"""
    return [p.strip() for p in re.split(r"[/,;]", text or "") if p.strip()]


app.jinja_env.filters["phones"] = phone_list
app.jinja_env.filters["tel"] = lambda p: re.sub(r"[^0-9+]", "", p)


def read_student_form(f):
    data = {"name": (f.get("name") or "").strip()[:100]}
    if not data["name"]:
        raise ValueError("Bitte einen Namen angeben.")
    for key, _label, maxlen in ADDRESS_FIELDS:
        data[key] = (f.get(key) or "").strip()[:maxlen]
    for n in (1, 2):
        for key, _label, maxlen in GUARDIAN_FIELDS:
            data[f"g{n}_{key}"] = (f.get(f"g{n}_{key}") or "").strip()[:maxlen]
        emails = email_list(data[f"g{n}_email"])
        for addr in emails:
            if not EMAIL_RE.match(addr):
                raise ValueError(f"Ungültige E-Mail-Adresse: {addr}")
        data[f"g{n}_email"] = ", ".join(emails)
    return data


def guardians(st):
    """Die eingetragenen Erziehungsberechtigten einer Schülerin/eines Schülers."""
    result = []
    for n in (1, 2):
        g = {k: st[f"g{n}_{k}"] for k, _l, _m in GUARDIAN_FIELDS}
        if any(g.values()):
            g["n"], g["emails"], g["phones"] = n, email_list(g["email"]), phone_list(g["phone"])
            result.append(g)
    return result


app.jinja_env.globals["guardians"] = guardians
STUDENT_COLUMNS = ["name"] + [k for k, _l, _m in ADDRESS_FIELDS] + GUARDIAN_COLUMNS


@app.route("/schueler", methods=["GET", "POST"])
@login_required
def students():
    db = get_db()
    if request.method == "POST":
        if not can("kasse"):
            abort(403)
        if request.form.get("action") == "single":
            try:
                data = read_student_form(request.form)
                db.execute(f"INSERT INTO students ({', '.join(STUDENT_COLUMNS)}) "
                           f"VALUES ({', '.join('?' * len(STUDENT_COLUMNS))})",
                           [data[c] for c in STUDENT_COLUMNS])
                db.commit()
                flash(f"{data['name']} angelegt.", "ok")
            except ValueError as e:
                flash(str(e), "error")
            return redirect(url_for("students"))
        names = [n.strip()[:100] for n in request.form.get("names", "").splitlines() if n.strip()]
        for n in names:
            db.execute("INSERT INTO students (name) VALUES (?)", (n,))
        db.commit()
        flash(f"{len(names)} Schüler/innen angelegt." if names else "Keine Namen eingegeben.",
              "ok" if names else "error")
        return redirect(url_for("students"))
    rows = db.execute("SELECT * FROM students ORDER BY active DESC, name COLLATE NOCASE").fetchall()
    return render_template("students.html", rows=rows, open_map=open_per_student(db))


def student_export_columns():
    return ([("Name", "text"), ("Straße", "text"), ("PLZ", "text"),
             ("Ort", "text")]
            + [(guardian_header(n, label), "text") for n in (1, 2) for _k, label, _m in GUARDIAN_FIELDS]
            + [("Notiz", "text"), ("Status", "text")])


def guardian_header(n, label):
    return f"Erziehungsb. {n}: {label.split(',')[0]}"


@app.route("/export/klassenliste.<fmt>")
@login_required
def export_students(fmt):
    rows = get_db().execute("SELECT * FROM students ORDER BY active DESC, name COLLATE NOCASE").fetchall()
    return export_response(
        fmt, f"klassenliste_{date.today().isoformat()}", student_export_columns(),
        [[r["name"], r["street"], r["zip"], r["city"]]
         + [r[c] for c in GUARDIAN_COLUMNS]
         + [r["notes"], "aktiv" if r["active"] else "inaktiv"] for r in rows],
        "Klassenliste")


# ---------------------------------------------------------------- Import der Klassenliste
def norm_header(text):
    text = (text or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(a, b)
    return re.sub(r"[^a-z0-9]", "", text)


# normalisierte Überschrift -> Feld; die Überschriften des eigenen Exports sind immer dabei
HEADER_ALIASES = {
    "name": "name", "schueler": "name", "schuelerin": "name", "schuelerinnen": "name", "kind": "name",
    "vorname": "first", "nachname": "last", "familienname": "last",
    "strasse": "street", "str": "street", "strassehausnummer": "street", "anschrift": "street",
    "adresse": "street",
    "plz": "zip", "postleitzahl": "zip",
    "ort": "city", "wohnort": "city", "stadt": "city",
    "notiz": "notes", "notizen": "notes", "bemerkung": "notes", "bemerkungen": "notes", "hinweis": "notes",
    "status": "status",
    "telefon": "g1_phone", "tel": "g1_phone", "telefonnummer": "g1_phone", "handy": "g1_phone",
    "mobil": "g1_phone", "email": "g1_email", "mail": "g1_email",
    "erziehungsberechtigte": "g1_name", "eltern": "g1_name",
}
GUARDIAN_HEADER_RE = re.compile(
    r"^(?:erziehungsb\w*?|eltern(?:teil)?|eb)([12])"
    r"(name|telefon|tel|mobil|handy|email|mail|anschrift|adresse)$")
GUARDIAN_HEADER_KEYS = {"name": "name", "telefon": "phone", "tel": "phone", "mobil": "phone",
                        "handy": "phone", "email": "email", "mail": "email",
                        "anschrift": "address", "adresse": "address"}
STATUS_VALUES = {"aktiv": 1, "ja": 1, "1": 1, "x": 1, "inaktiv": 0, "nein": 0, "0": 0}


def map_headers(header):
    """Spalten der Datei -> {Index: Feld}, dazu die Liste der unbekannten Überschriften."""
    mapping, ignored, used = {}, [], set()
    for i, h in enumerate(header):
        key = norm_header(h)
        m = GUARDIAN_HEADER_RE.match(key)
        field = f"g{m.group(1)}_{GUARDIAN_HEADER_KEYS[m.group(2)]}" if m else HEADER_ALIASES.get(key)
        if field and field not in used:
            mapping[i] = field
            used.add(field)
        elif h:
            ignored.append(h)
    fields = set(mapping.values())
    if "name" not in fields and not {"first", "last"} & fields:
        raise ValueError("Keine Spalte „Name“ (oder „Vorname“/„Nachname“) gefunden.")
    return mapping, ignored


def import_records(header, body, lines):
    """Zeilen der Datei -> Liste von {Feld: Text}, nur Felder, deren Spalte es gibt.

    "line" ist die Zeilennummer in der Datei, für die Vorschau.
    """
    mapping, ignored = map_headers(header)
    records = []
    for row, line in zip(body, lines):
        rec = {field: row[i].strip() for i, field in mapping.items()}
        rec["line"] = str(line)
        first, last = rec.pop("first", ""), rec.pop("last", "")
        if not rec.get("name") and (first or last):
            rec["name"] = f"{first} {last}".strip()
        if any(v for k, v in rec.items() if k != "line"):
            records.append(rec)
    return records, ignored


def plan_import(db, records):
    """Was der Import tun würde: je Zeile Aktion, Daten, Änderungen und Fehler.

    Vorhandene Schüler/innen werden am Namen erkannt. Überschrieben werden nur
    gefüllte Zellen; leere lassen vorhandene Daten stehen (Löschen geht im Formular).
    """
    existing = {}
    for r in db.execute("SELECT * FROM students").fetchall():
        existing.setdefault(r["name"].strip().lower(), r)
    seen, plan = set(), []
    for rec in records:
        item = {"rec": rec, "name": rec.get("name", ""), "line": rec.get("line", ""),
                "changes": [], "error": None}
        try:
            key = item["name"].strip().lower()
            if not key:
                raise ValueError("Name fehlt.")
            if key in seen:
                raise ValueError("Steht mehrfach in der Datei.")
            seen.add(key)
            old = existing.get(key)
            form = {c: (old[c] or "") if old else "" for c in STUDENT_COLUMNS}
            form.update({k: v for k, v in rec.items() if k in STUDENT_COLUMNS and v})
            data = read_student_form(form)
            active = old["active"] if old else 1
            if rec.get("status"):
                if rec["status"].lower() not in STATUS_VALUES:
                    raise ValueError(f"Unbekannter Status: {rec['status']} (aktiv oder inaktiv)")
                active = STATUS_VALUES[rec["status"].lower()]
            data["active"] = active
            item["data"] = data
            if old is None:
                item["action"] = "neu"
            else:
                item["sid"] = old["id"]
                item["changes"] = [c for c in STUDENT_COLUMNS + ["active"]
                                   if (old[c] or "") != (data[c] or "")]
                item["action"] = "ändern" if item["changes"] else "gleich"
        except ValueError as e:
            item["action"], item["error"] = "fehler", str(e)
        plan.append(item)
    return plan


FIELD_LABELS = dict(
    [("name", "Name"), ("active", "Status")]
    + [(k, label) for k, label, _m in ADDRESS_FIELDS]
    + [(f"g{n}_{k}", f"Erziehungsb. {n}: {label.split(',')[0]}") for n in (1, 2)
       for k, label, _m in GUARDIAN_FIELDS])


@app.route("/schueler/import", methods=["POST"])
@role_required("kasse")
def students_import():
    db = get_db()
    try:
        if "records" in request.form:  # Bestätigung nach der Vorschau
            records = json.loads(request.form["records"])
            if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
                raise ValueError("Ungültige Importdaten.")
            records = [{str(k): str(v)[:600] for k, v in r.items()} for r in records]
            plan = plan_import(db, records)
            cols = STUDENT_COLUMNS + ["active"]
            new = changed = 0
            for item in plan:
                if item["action"] == "neu":
                    db.execute(f"INSERT INTO students ({', '.join(cols)}) "
                               f"VALUES ({', '.join('?' * len(cols))})",
                               [item["data"][c] for c in cols])
                    new += 1
                elif item["action"] == "ändern":
                    db.execute(f"UPDATE students SET {', '.join(c + ' = ?' for c in cols)} WHERE id = ?",
                               [item["data"][c] for c in cols] + [item["sid"]])
                    changed += 1
            db.commit()
            skipped = sum(1 for i in plan if i["action"] == "fehler")
            flash(f"Import fertig: {new} neu, {changed} geändert"
                  + (f", {skipped} Zeilen mit Fehlern übersprungen." if skipped else "."), "ok")
            return redirect(url_for("students"))

        upload = request.files.get("file")
        if not upload or not upload.filename:
            raise ValueError("Bitte eine Datei wählen.")
        header, body, lines = tableio.read_table(upload.filename, upload.read())
        records, ignored = import_records(header, body, lines)
        if not records:
            raise ValueError("Die Datei enthält keine Zeilen.")
        plan = plan_import(db, records)
        counts = {a: sum(1 for i in plan if i["action"] == a) for a in ("neu", "ändern", "gleich", "fehler")}
        return render_template("students_import.html", plan=plan, counts=counts, ignored=ignored,
                               filename=upload.filename, labels=FIELD_LABELS,
                               records_json=json.dumps(records, ensure_ascii=False))
    except (ValueError, json.JSONDecodeError) as e:
        flash(f"Import nicht möglich: {e}", "error")
        return redirect(url_for("students"))


@app.route("/schueler/<int:sid>")
@login_required
def student(sid):
    db = get_db()
    st = get_or_404(db, "students", sid)
    status = []
    for col in db.execute("SELECT * FROM collections ORDER BY closed, id DESC").fetchall():
        for i in collection_status(db, col):
            if i["id"] == sid:
                status.append({"c": col, **i})
    rows = db.execute(BOOKING_SELECT + " WHERE b.student_id = ? ORDER BY b.booking_date DESC, b.id DESC",
                      (sid,)).fetchall()
    return render_template("student.html", st=st, status=status, rows=rows)


@app.route("/schueler/<int:sid>/bearbeiten", methods=["POST"])
@role_required("kasse")
def student_edit(sid):
    db = get_db()
    st = get_or_404(db, "students", sid)
    if request.form.get("action") == "toggle":
        db.execute("UPDATE students SET active = ? WHERE id = ?", (0 if st["active"] else 1, sid))
        flash("Status geändert.", "ok")
    else:
        try:
            data = read_student_form(request.form)
            db.execute(f"UPDATE students SET {', '.join(c + ' = ?' for c in STUDENT_COLUMNS)} WHERE id = ?",
                       [data[c] for c in STUDENT_COLUMNS] + [sid])
            flash("Gespeichert.", "ok")
        except ValueError as e:
            flash(str(e), "error")
    db.commit()
    return redirect(url_for("student", sid=sid))


# ---------------------------------------------------------------- Benutzer (Admin)
@app.route("/benutzer", methods=["GET", "POST"])
@role_required("admin")
def users():
    db = get_db()
    if request.method == "POST":
        username = request.form.get("username", "").strip()[:50]
        pw, role = request.form.get("password", ""), request.form.get("role")
        if not username or role not in ROLES:
            flash("Bitte Benutzername und Rolle angeben.", "error")
        elif len(pw) < 8:
            flash("Das Passwort muss mindestens 8 Zeichen haben.", "error")
        else:
            try:
                db.execute("INSERT INTO users (username, pw_hash, role) VALUES (?, ?, ?)",
                           (username, generate_password_hash(pw), role))
                db.commit()
                flash(f"Benutzer {username} angelegt.", "ok")
            except sqlite3.IntegrityError:
                flash("Diesen Benutzernamen gibt es schon.", "error")
        return redirect(url_for("users"))
    rows = db.execute("SELECT * FROM users ORDER BY username COLLATE NOCASE").fetchall()
    blocks = db.execute("SELECT * FROM ip_blocks ORDER BY blocked_at DESC").fetchall()
    failures = db.execute("""SELECT ip, COUNT(*) AS n, MAX(at) AS last, GROUP_CONCAT(DISTINCT username) AS names
                             FROM login_failures GROUP BY ip ORDER BY last DESC LIMIT 20""").fetchall()
    return render_template("users.html", rows=rows, blocks=blocks, failures=failures,
                           my_ip=client_ip(), max_failures=MAX_LOGIN_FAILURES,
                           proxy_mode=PROXY_MODE, proxy_addr=request.environ.get("kk.proxy_addr"),
                           trusted=", ".join(str(n.network_address) if n.num_addresses == 1 else str(n)
                                             for n in TRUSTED_PROXIES))


@app.route("/benutzer/sperrliste", methods=["POST"])
@role_required("admin")
def blocklist_edit():
    db = get_db()
    action = request.form.get("action")
    try:
        ip = parse_network(request.form.get("ip"))
        if action == "add":
            net = ipaddress.ip_network(ip, strict=False)
            if ipaddress.ip_address(client_ip()) in net:
                raise ValueError("Damit würdest du dich selbst aussperren (deine IP-Adresse: "
                                 f"{client_ip()}).")
            reason = request.form.get("reason", "").strip()[:200] or "von Hand gesperrt"
            cur = db.execute("INSERT OR IGNORE INTO ip_blocks (ip, reason, created_by) VALUES (?, ?, ?)",
                             (ip, reason, g.user["username"]))
            flash(f"{ip} gesperrt." if cur.rowcount else f"{ip} ist schon gesperrt.", "ok")
        elif action == "remove":
            db.execute("DELETE FROM ip_blocks WHERE ip = ?", (ip,))
            db.execute("DELETE FROM login_failures WHERE ip = ?", (ip,))
            flash(f"{ip} entsperrt.", "ok")
        elif action == "forget":
            db.execute("DELETE FROM login_failures WHERE ip = ?", (ip,))
            flash(f"Fehlversuche von {ip} zurückgesetzt.", "ok")
        db.commit()
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("users") + "#sperrliste")


@app.route("/benutzer/<int:uid>", methods=["POST"])
@role_required("admin")
def user_edit(uid):
    db = get_db()
    u = get_or_404(db, "users", uid)
    action = request.form.get("action")
    if uid == g.user["id"] and action in ("delete", "role"):
        flash("Das eigene Konto kann hier nicht gelöscht oder herabgestuft werden.", "error")
    elif action == "delete":
        db.execute("DELETE FROM users WHERE id = ?", (uid,))
        flash(f"Benutzer {u['username']} gelöscht.", "ok")
    elif action == "role" and request.form.get("role") in ROLES:
        db.execute("UPDATE users SET role = ? WHERE id = ?", (request.form["role"], uid))
        flash("Rolle geändert.", "ok")
    elif action == "password":
        pw = request.form.get("password", "")
        if len(pw) < 8:
            flash("Das Passwort muss mindestens 8 Zeichen haben.", "error")
        else:
            db.execute("UPDATE users SET pw_hash = ? WHERE id = ?", (generate_password_hash(pw), uid))
            flash(f"Passwort für {u['username']} neu gesetzt.", "ok")
    db.commit()
    return redirect(url_for("users"))


# ---------------------------------------------------------------- Fehlerseiten
@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(413)
def error_page(e):
    texts = {400: "Ungültige Anfrage (evtl. Seite neu laden).",
             403: "Dafür fehlen dir die Rechte.", 404: "Nicht gefunden.",
             413: "Die Datei ist zu groß (höchstens 5 MB)."}
    return render_template("error.html", code=e.code, text=texts.get(e.code, "Fehler")), e.code


# ---------------------------------------------------------------- Kommandozeile
@app.cli.command("create-user")
@click.argument("username")
@click.option("--role", type=click.Choice(list(ROLES)), default="admin", show_default=True)
@click.option("--password-stdin", is_flag=True,
              help="Passwort aus der ersten Zeile von stdin lesen (für Skripte).")
def create_user(username, role, password_stdin):
    """Benutzer anlegen oder Passwort/Rolle eines bestehenden setzen."""
    if password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = click.prompt("Passwort", hide_input=True,
                                confirmation_prompt="Passwort wiederholen")
    if len(password) < 8:
        raise click.ClickException("Das Passwort muss mindestens 8 Zeichen haben.")
    db = sqlite3.connect(app.config["DATABASE"])
    db.execute("""INSERT INTO users (username, pw_hash, role) VALUES (?, ?, ?)
                  ON CONFLICT(username) DO UPDATE SET pw_hash = excluded.pw_hash, role = excluded.role""",
               (username, generate_password_hash(password), role))
    db.commit()
    db.close()
    click.echo(f"Benutzer '{username}' ({role}) gespeichert.")


@app.cli.command("version")
def version():
    """Installierte Version anzeigen."""
    click.echo(VERSION)


@app.cli.command("blocklist")
def blocklist_cmd():
    """Gesperrte IP-Adressen anzeigen."""
    db = sqlite3.connect(app.config["DATABASE"])
    rows = db.execute("SELECT ip, blocked_at, created_by, reason FROM ip_blocks ORDER BY blocked_at").fetchall()
    db.close()
    if not rows:
        click.echo("Keine IP-Adresse gesperrt.")
    for ip, at, by, reason in rows:
        click.echo(f"{ip:<40} {at}  {by}: {reason}")


@app.cli.command("unblock")
@click.argument("ip", required=False)
@click.option("--all", "all_", is_flag=True, help="Alle Sperren und Fehlversuche löschen.")
def unblock_cmd(ip, all_):
    """IP-Adresse entsperren (z. B. wenn sich ein Administrator ausgesperrt hat)."""
    db = sqlite3.connect(app.config["DATABASE"])
    if all_:
        n = db.execute("DELETE FROM ip_blocks").rowcount
        db.execute("DELETE FROM login_failures")
    elif ip:
        try:
            ip = parse_network(ip)
        except ValueError as e:
            raise click.ClickException(str(e))
        n = db.execute("DELETE FROM ip_blocks WHERE ip = ?", (ip,)).rowcount
        db.execute("DELETE FROM login_failures WHERE ip = ?", (ip,))
    else:
        raise click.UsageError("IP-Adresse oder --all angeben.")
    db.commit()
    db.close()
    click.echo(f"{n} Sperre(n) aufgehoben.")


@app.cli.command("count-users")
def count_users():
    db = sqlite3.connect(app.config["DATABASE"])
    click.echo(db.execute("SELECT COUNT(*) FROM users").fetchone()[0])
    db.close()


@app.cli.command("backup")
@click.argument("target")
def backup(target):
    """Konsistente Sicherung der Datenbank (auch im laufenden Betrieb)."""
    src = sqlite3.connect(app.config["DATABASE"])
    dst = sqlite3.connect(target)
    src.backup(dst)
    dst.close()
    src.close()
    click.echo(f"Sicherung geschrieben: {target}")


if __name__ == "__main__":
    app.run(debug=True)
