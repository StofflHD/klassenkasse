PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY,
    username    TEXT NOT NULL UNIQUE COLLATE NOCASE,
    pw_hash     TEXT NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('lesen', 'kasse', 'admin')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS students (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    -- Klassenliste (ab 0.2.0; ältere Datenbanken ergänzt init_db() in app.py)
    birthday    TEXT,
    guardians   TEXT NOT NULL DEFAULT '',
    street      TEXT NOT NULL DEFAULT '',
    zip         TEXT NOT NULL DEFAULT '',
    city        TEXT NOT NULL DEFAULT '',
    phone       TEXT NOT NULL DEFAULT '',
    phone2      TEXT NOT NULL DEFAULT '',
    email       TEXT NOT NULL DEFAULT '',
    notes       TEXT NOT NULL DEFAULT ''
);

-- Sammelaktion, z. B. "Ausflug Zoo, 12 € pro Kopf"
CREATE TABLE IF NOT EXISTS collections (
    id            INTEGER PRIMARY KEY,
    title         TEXT NOT NULL,
    amount_cents  INTEGER NOT NULL CHECK (amount_cents > 0),
    due_date      TEXT,
    closed        INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Beträge immer in Cent (Ganzzahl), immer positiv; die Richtung steckt in "kind".
CREATE TABLE IF NOT EXISTS bookings (
    id             INTEGER PRIMARY KEY,
    booking_date   TEXT NOT NULL,
    kind           TEXT NOT NULL CHECK (kind IN ('in', 'out')),
    amount_cents   INTEGER NOT NULL CHECK (amount_cents > 0),
    purpose        TEXT NOT NULL,
    student_id     INTEGER REFERENCES students(id),
    collection_id  INTEGER REFERENCES collections(id),
    created_by     TEXT NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    cancelled_at   TEXT,
    cancelled_by   TEXT,
    cancel_reason  TEXT
);

CREATE INDEX IF NOT EXISTS idx_bookings_student    ON bookings(student_id);
CREATE INDEX IF NOT EXISTS idx_bookings_collection ON bookings(collection_id);

-- Buchungen sind revisionssicher: kein Löschen, keine Änderung der Inhalte.
-- Korrekturen laufen ausschließlich über Storno + neue Buchung.
CREATE TRIGGER IF NOT EXISTS bookings_no_delete
BEFORE DELETE ON bookings
BEGIN
    SELECT RAISE(ABORT, 'Buchungen werden storniert, nicht gelöscht');
END;

CREATE TRIGGER IF NOT EXISTS bookings_no_update
BEFORE UPDATE OF booking_date, kind, amount_cents, purpose, student_id, collection_id, created_by, created_at
ON bookings
BEGIN
    SELECT RAISE(ABORT, 'Buchungen sind unveränderlich');
END;

CREATE TRIGGER IF NOT EXISTS bookings_no_uncancel
BEFORE UPDATE OF cancelled_at ON bookings
WHEN OLD.cancelled_at IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Storno kann nicht rückgängig gemacht werden');
END;
