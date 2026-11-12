CREATE TABLE IF NOT EXISTS lists (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id     INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
    name        TEXT    NOT NULL,
    -- нормализованное название (strip + casefold), считается в Python:
    -- встроенный lower() в SQLite не понимает кириллицу
    name_key    TEXT    NOT NULL,
    qty         INTEGER NOT NULL CHECK (qty > 0),
    -- цена за всю позицию в копейках; NULL = цена не указана
    price_cents INTEGER CHECK (price_cents IS NULL OR price_cents >= 0),
    bought      INTEGER NOT NULL DEFAULT 0 CHECK (bought IN (0, 1)),
    UNIQUE (list_id, name_key)
);
