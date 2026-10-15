"""Klassenkasse – Web-App zur Verwaltung einer Klassenkasse (Flask + SQLite)."""
import csv
import io
import os
import re
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
)
if os.environ.get("KK_BEHIND_PROXY") == "1":
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

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
            for col in ("birthday", "street", "zip", "city", "notes",
                        "guardians", "phone", "phone2", "email"):
                if col not in cols:
                    db.execute(f"ALTER TABLE students ADD COLUMN {col} "
                               + ("TEXT" if col == "birthday" else "TEXT NOT NULL DEFAULT ''"))
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


def euro_plain(cents):
    sign = "-" if cents < 0 else ""
    e, c = divmod(abs(int(cents)), 100)
    return f"{sign}{e:,}".replace(",", ".") + f",{c:02d}"


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


def csv_text(value):
    """Schutz vor CSV-/Formel-Injection in Tabellenkalkulationen."""
    value = "" if value is None else str(value)
    if value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def csv_response(filename, header, rows):
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(header)
    w.writerows(rows)
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


# ---------------------------------------------------------------- Login, Rollen, CSRF
def can(role):
    user = g.get("user")
    return bool(user) and ROLES[user["role"]] >= ROLES[role]


@app.before_request
def before():
    g.user = None
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
        u = db.execute("SELECT * FROM users WHERE username = ?",
                       (request.form.get("username", "").strip(),)).fetchone()
        if u and check_password_hash(u["pw_hash"], request.form.get("password", "")):
            session.clear()
            session["uid"] = u["id"]
            return redirect(safe_next(request.args.get("next"), url_for("index")))
        flash("Benutzername oder Passwort falsch.", "error")
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


@app.route("/export/buchungen.csv")
@login_required
def export_bookings():
    rows = get_db().execute(BOOKING_SELECT + " ORDER BY b.booking_date, b.id").fetchall()
    return csv_response(
        f"buchungen_{date.today().isoformat()}.csv",
        ["Nr", "Datum", "Art", "Betrag", "Zweck", "Schüler/in", "Sammlung",
         "Erfasst von", "Erfasst am", "Storniert am", "Storniert von", "Storno-Grund"],
        [[r["id"], date_de(r["booking_date"]), "Einnahme" if r["kind"] == "in" else "Ausgabe",
          euro_plain(r["amount_cents"] if r["kind"] == "in" else -r["amount_cents"]),
          csv_text(r["purpose"]), csv_text(r["student_name"]), csv_text(r["collection_title"]),
          csv_text(r["created_by"]), r["created_at"], r["cancelled_at"] or "",
          csv_text(r["cancelled_by"]), csv_text(r["cancel_reason"])] for r in rows])


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


@app.route("/export/sammlung/<int:cid>.csv")
@login_required
def export_collection(cid):
    db = get_db()
    s = collection_summary(db, get_or_404(db, "collections", cid))
    return csv_response(
        f"sammlung_{cid}.csv",
        ["Schüler/in", "Soll", "Bezahlt", "Offen"],
        [[csv_text(i["name"]), euro_plain(s["c"]["amount_cents"] if i["active"] else 0),
          euro_plain(i["paid"]), euro_plain(i["open"])] for i in s["rows"]])


# ---------------------------------------------------------------- Schüler/innen
def open_per_student(db):
    result = {}
    for col in db.execute("SELECT * FROM collections WHERE closed = 0").fetchall():
        for i in collection_status(db, col):
            result[i["id"]] = result.get(i["id"], 0) + i["open"]
    return result


# Felder der Klassenliste außer Name und Geburtstag: (Spalte, Bezeichnung, max. Länge)
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
    data["birthday"] = parse_date(f.get("birthday"), default_today=False)
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
STUDENT_COLUMNS = ["name", "birthday"] + [k for k, _l, _m in ADDRESS_FIELDS] + GUARDIAN_COLUMNS


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


@app.route("/export/klassenliste.csv")
@login_required
def export_students():
    rows = get_db().execute("SELECT * FROM students ORDER BY active DESC, name COLLATE NOCASE").fetchall()
    return csv_response(
        f"klassenliste_{date.today().isoformat()}.csv",
        ["Name", "Geburtstag", "Straße", "PLZ", "Ort"]
        + [f"Erziehungsb. {n}: {label.split(',')[0]}" for n in (1, 2) for _k, label, _m in GUARDIAN_FIELDS]
        + ["Notiz", "Status"],
        [[csv_text(r["name"]), date_de(r["birthday"]), csv_text(r["street"]), csv_text(r["zip"]),
          csv_text(r["city"])]
         + [csv_text(r[c]) for c in GUARDIAN_COLUMNS]
         + [csv_text(r["notes"]), "aktiv" if r["active"] else "inaktiv"] for r in rows])


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
    return render_template("users.html", rows=rows)


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
def error_page(e):
    texts = {400: "Ungültige Anfrage (evtl. Seite neu laden).",
             403: "Dafür fehlen dir die Rechte.", 404: "Nicht gefunden."}
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
