"""Работа с SQLite: подключение, создание таблиц и запросы."""
import sqlite3
from pathlib import Path

from flask import current_app, g

BASE_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = BASE_DIR / "schema.sql"
DEFAULT_DB_PATH = BASE_DIR / "shopping.db"


def name_key(name):
    """Ключ для сравнения названий без учёта регистра (работает и с кириллицей)."""
    return " ".join(name.split()).casefold()


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db(path=DEFAULT_DB_PATH):
    conn = connect(path)
    with conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.close()


# ---------- списки ----------

def all_lists():
    rows = get_db().execute("SELECT id, name FROM lists ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def get_list(list_id):
    row = get_db().execute("SELECT id, name FROM lists WHERE id = ?", (list_id,)).fetchone()
    return dict(row) if row else None


def create_list(name):
    conn = get_db()
    with conn:
        cur = conn.execute("INSERT INTO lists (name) VALUES (?)", (name,))
    return get_list(cur.lastrowid)


def rename_list(list_id, name):
    conn = get_db()
    with conn:
        cur = conn.execute("UPDATE lists SET name = ? WHERE id = ?", (name, list_id))
    return cur.rowcount > 0


def delete_list(list_id):
    conn = get_db()
    with conn:
        cur = conn.execute("DELETE FROM lists WHERE id = ?", (list_id,))
    return cur.rowcount > 0


# ---------- товары ----------

def _item_dict(row):
    return {
        "id": row["id"],
        "list_id": row["list_id"],
        "name": row["name"],
        "qty": row["qty"],
        "price_cents": row["price_cents"],
        "bought": bool(row["bought"]),
    }


def get_item(item_id):
    row = get_db().execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return _item_dict(row) if row else None


def list_items(list_id):
    rows = get_db().execute(
        "SELECT * FROM items WHERE list_id = ? ORDER BY bought, id", (list_id,)
    ).fetchall()
    return [_item_dict(r) for r in rows]


def add_item(list_id, name, qty, price_cents):
    """Добавляет товар или объединяет с уже существующим (то же название без учёта регистра).

    При объединении количество и цена складываются; пустая цена считается нулём,
    но если цены нет у обоих — остаётся пустой. Объединённый товар снова «не куплен».
    Возвращает (item, merged).
    """
    conn = get_db()
    key = name_key(name)
    with conn:
        existing = conn.execute(
            "SELECT * FROM items WHERE list_id = ? AND name_key = ?", (list_id, key)
        ).fetchone()
        if existing:
            old_price = existing["price_cents"]
            if old_price is None and price_cents is None:
                new_price = None
            else:
                new_price = (old_price or 0) + (price_cents or 0)
            conn.execute(
                "UPDATE items SET qty = qty + ?, price_cents = ?, bought = 0 WHERE id = ?",
                (qty, new_price, existing["id"]),
            )
            item_id, merged = existing["id"], True
        else:
            cur = conn.execute(
                "INSERT INTO items (list_id, name, name_key, qty, price_cents) VALUES (?, ?, ?, ?, ?)",
                (list_id, name, key, qty, price_cents),
            )
            item_id, merged = cur.lastrowid, False
    return get_item(item_id), merged


def set_bought(item_id, bought):
    conn = get_db()
    with conn:
        cur = conn.execute("UPDATE items SET bought = ? WHERE id = ?", (1 if bought else 0, item_id))
    return cur.rowcount > 0


def delete_item(item_id):
    conn = get_db()
    with conn:
        cur = conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    return cur.rowcount > 0
