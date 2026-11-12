"""MCP-сервер для базы Shopping List (SQLite), только чтение.

Даёт Claude Code инструменты, чтобы смотреть списки, товары, итоги и схему
и проверять целостность данных. Изменять данные нельзя: база открывается
в режиме read-only, а все изменения идут только через веб-приложение,
где работают проверка ввода и объединение товаров.

Запуск (обычно его запускает Claude Code по .mcp.json):
    .venv/Scripts/python.exe mcp_server/server.py

Путь к базе: переменная окружения SHOPPING_DB, иначе shopping.db в корне проекта.
"""
import os
import re
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from db import name_key  # noqa: E402  — то же правило сравнения названий, что в приложении

DB_PATH = Path(os.environ.get("SHOPPING_DB") or PROJECT_DIR / "shopping.db")
MAX_ROWS = 500

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)

server = MCPServer(
    name="shopping-db",
    instructions=(
        "База веб-приложения Shopping List (Flask + SQLite), только чтение. "
        "Цены хранятся в копейках (price_cents) за всю позицию; null — цена не указана. "
        "bought: 1 — куплено. name_key — название без регистра и лишних пробелов. "
        "Для обзора используй list_lists и get_list, для произвольных запросов — run_select."
    ),
)


class DbError(ToolError):
    """Ожидаемая ошибка: текст уходит клиенту как результат с is_error, без трейсбека в логах."""


@contextmanager
def connect():
    """Соединение только для чтения; закрывается после каждого вызова инструмента."""
    if not DB_PATH.exists():
        raise DbError(f"База не найдена: {DB_PATH}. Запустите веб-приложение один раз, чтобы она создалась.")
    conn = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")
        yield conn
    finally:
        conn.close()


def rubles(cents):
    if cents is None:
        return None
    return f"{cents // 100}.{cents % 100:02d}"


TOTALS_SQL = """
SELECT
    COUNT(*)                                                    AS total_count,
    COALESCE(SUM(bought), 0)                                    AS bought_count,
    COALESCE(SUM(price_cents), 0)                               AS total_cents,
    COALESCE(SUM(CASE WHEN bought = 1 THEN price_cents END), 0) AS bought_cents
FROM items WHERE list_id = ?
"""


def totals_for(conn, list_id):
    r = conn.execute(TOTALS_SQL, (list_id,)).fetchone()
    left_count = r["total_count"] - r["bought_count"]
    left_cents = r["total_cents"] - r["bought_cents"]
    return {
        "total": {"count": r["total_count"], "price_cents": r["total_cents"], "rub": rubles(r["total_cents"])},
        "bought": {"count": r["bought_count"], "price_cents": r["bought_cents"], "rub": rubles(r["bought_cents"])},
        "left": {"count": left_count, "price_cents": left_cents, "rub": rubles(left_cents)},
    }


def item_dict(row):
    return {
        "id": row["id"],
        "list_id": row["list_id"],
        "name": row["name"],
        "qty": row["qty"],
        "price_cents": row["price_cents"],
        "price_rub": rubles(row["price_cents"]),
        "bought": bool(row["bought"]),
    }


@server.tool(annotations=READ_ONLY)
def list_lists() -> list[dict]:
    """Все списки покупок с итогами: число позиций и суммы (всего / куплено / осталось)."""
    with connect() as conn:
        rows = conn.execute("SELECT id, name FROM lists ORDER BY id").fetchall()
        return [{"id": r["id"], "name": r["name"], "totals": totals_for(conn, r["id"])} for r in rows]


@server.tool(annotations=READ_ONLY)
def get_list(list_id: int) -> dict:
    """Один список: товары (некупленные сначала) и итоги, как их показывает страница."""
    with connect() as conn:
        lst = conn.execute("SELECT id, name FROM lists WHERE id = ?", (list_id,)).fetchone()
        if lst is None:
            raise DbError(f"Список {list_id} не найден")
        items = conn.execute(
            "SELECT * FROM items WHERE list_id = ? ORDER BY bought, id", (list_id,)
        ).fetchall()
        return {
            "list": dict(lst),
            "items": [item_dict(i) for i in items],
            "totals": totals_for(conn, list_id),
        }


@server.tool(annotations=READ_ONLY)
def find_items(query: str) -> list[dict]:
    """Ищет товары во всех списках по части названия без учёта регистра (работает с кириллицей)."""
    key = name_key(query)
    if not key:
        raise DbError("Пустой запрос")
    with connect() as conn:
        rows = conn.execute(
            "SELECT i.*, l.name AS list_name FROM items i JOIN lists l ON l.id = i.list_id ORDER BY i.list_id, i.id"
        ).fetchall()
    # фильтр в Python: instr/like в SQLite не понимают регистр кириллицы
    return [dict(item_dict(r), list_name=r["list_name"]) for r in rows if key in r["name_key"]][:MAX_ROWS]


@server.tool(annotations=READ_ONLY)
def describe_schema() -> dict:
    """Схема базы: таблицы, колонки, ограничения и исходный CREATE TABLE."""
    with connect() as conn:
        tables = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        result = {}
        for t in tables:
            cols = conn.execute(f'PRAGMA table_info("{t["name"]}")').fetchall()
            fks = conn.execute(f'PRAGMA foreign_key_list("{t["name"]}")').fetchall()
            count = conn.execute(f'SELECT COUNT(*) FROM "{t["name"]}"').fetchone()[0]
            result[t["name"]] = {
                "rows": count,
                "columns": [
                    {"name": c["name"], "type": c["type"], "not_null": bool(c["notnull"]),
                     "default": c["dflt_value"], "primary_key": bool(c["pk"])}
                    for c in cols
                ],
                "foreign_keys": [
                    {"column": f["from"], "references": f'{f["table"]}({f["to"]})', "on_delete": f["on_delete"]}
                    for f in fks
                ],
                "sql": t["sql"],
            }
        return {"database": str(DB_PATH), "tables": result}


_SELECT_RE = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)


@server.tool(annotations=READ_ONLY)
def run_select(sql: str, limit: int = 100) -> dict:
    """Выполняет один запрос SELECT (или WITH … SELECT) и возвращает строки.

    Только чтение: база открыта read-only, другие команды отклоняются.
    Не больше `limit` строк (максимум 500). Пример:
    SELECT name, qty, price_cents FROM items WHERE bought = 0
    """
    text = sql.strip().rstrip(";")
    if not _SELECT_RE.match(text):
        raise DbError("Разрешены только запросы SELECT или WITH … SELECT")
    if not sqlite3.complete_statement(text + ";") or ";" in text:
        raise DbError("Разрешён только один запрос, без ';' внутри")
    limit = max(1, min(int(limit), MAX_ROWS))
    with connect() as conn:
        try:
            cur = conn.execute(text)
        except sqlite3.Error as exc:
            raise DbError(f"Ошибка SQLite: {exc}") from exc
        columns = [d[0] for d in cur.description or []]
        rows = cur.fetchmany(limit + 1)
    return {
        "columns": columns,
        "rows": [list(r) for r in rows[:limit]],
        "truncated": len(rows) > limit,
    }


@server.tool(annotations=READ_ONLY)
def check_integrity() -> dict:
    """Проверяет базу на нарушения правил приложения.

    integrity_check SQLite, внешние ключи, qty > 0, цена ≥ 0, bought ∈ {0,1},
    совпадение name_key с правилом из db.py и отсутствие дублей name_key в одном списке.
    """
    problems = []
    with connect() as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            problems.append(f"integrity_check: {integrity}")
        for r in conn.execute("PRAGMA foreign_key_check").fetchall():
            problems.append(f"Товар id={r['rowid']} ссылается на несуществующий список")
        for r in conn.execute("SELECT id, qty FROM items WHERE qty <= 0 OR typeof(qty) != 'integer'"):
            problems.append(f"Товар id={r['id']}: неверное количество {r['qty']!r}")
        for r in conn.execute("SELECT id, price_cents FROM items WHERE price_cents < 0 OR (price_cents IS NOT NULL AND typeof(price_cents) != 'integer')"):
            problems.append(f"Товар id={r['id']}: неверная цена {r['price_cents']!r}")
        for r in conn.execute("SELECT id, bought FROM items WHERE bought NOT IN (0, 1)"):
            problems.append(f"Товар id={r['id']}: bought = {r['bought']!r}")
        groups = {}  # (list_id, ключ по правилу приложения) -> id товаров
        for r in conn.execute("SELECT id, list_id, name, name_key FROM items ORDER BY id"):
            key = name_key(r["name"])
            if r["name_key"] != key:
                problems.append(f"Товар id={r['id']}: name_key {r['name_key']!r} не соответствует названию {r['name']!r}")
            groups.setdefault((r["list_id"], key), []).append(r["id"])
        for (list_id, key), ids in groups.items():
            if len(ids) > 1:
                problems.append(f"Список id={list_id}: товары {ids} с одинаковым названием {key!r} должны быть объединены")
        for r in conn.execute("SELECT id, name FROM lists WHERE trim(name) = ''"):
            problems.append(f"Список id={r['id']}: пустое название")
        counts = {
            "lists": conn.execute("SELECT COUNT(*) FROM lists").fetchone()[0],
            "items": conn.execute("SELECT COUNT(*) FROM items").fetchone()[0],
        }
    return {"ok": not problems, "problems": problems, "counts": counts, "database": str(DB_PATH)}


if __name__ == "__main__":
    server.run()
