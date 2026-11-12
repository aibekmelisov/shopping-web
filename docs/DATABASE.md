# База данных

Приложение хранит данные в SQLite, в файле `shopping.db` в корне проекта. Схема описана в [schema.sql](../schema.sql), запросы — в [db.py](../db.py). Устройство кода — в [CODE_GUIDE.md](CODE_GUIDE.md).

## Создание

Файл создаётся сам при запуске сервера: `create_app()` вызывает `db.init_db()`, а тот выполняет `schema.sql`. Все таблицы создаются через `CREATE TABLE IF NOT EXISTS`, поэтому повторный запуск ничего не ломает и данные не стирает.

Каждое соединение включает `PRAGMA foreign_keys = ON`. Без этой настройки SQLite игнорирует `REFERENCES` и `ON DELETE CASCADE`.

## Схема

```
lists 1 ──── * items
```

### lists — списки покупок

| Колонка | Тип | Ограничения | Смысл |
|---------|-----|-------------|-------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | номер списка |
| `name` | TEXT | NOT NULL | название; пустое отсекается в `app.py` |

Одинаковые названия у разных списков разрешены.

### items — товары

| Колонка | Тип | Ограничения | Смысл |
|---------|-----|-------------|-------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | номер товара |
| `list_id` | INTEGER | NOT NULL, REFERENCES `lists(id)` ON DELETE CASCADE | список, к которому относится товар |
| `name` | TEXT | NOT NULL | название, как его ввели (при объединении остаётся первое) |
| `name_key` | TEXT | NOT NULL | ключ для поиска одинаковых: пробелы схлопнуты, `casefold()` |
| `qty` | INTEGER | NOT NULL, CHECK `qty > 0` | количество |
| `price_cents` | INTEGER | NULL или CHECK `≥ 0` | цена **за всю позицию в копейках**; `NULL` — цена не указана |
| `bought` | INTEGER | NOT NULL DEFAULT 0, CHECK `IN (0, 1)` | 1 — куплено |

Ограничение `UNIQUE (list_id, name_key)`: в одном списке не может быть двух строк с одинаковым ключом. Это защищает правило объединения на уровне базы.

Таблица `sqlite_sequence` — служебная, SQLite создаёт её сам для `AUTOINCREMENT`.

### Почему так

- **`name_key` хранится, а не вычисляется в запросе.** Встроенный `lower()` в SQLite меняет только латиницу: «Молоко» и «молоко» он считает разными. Ключ считается в Python (`db.name_key`) и правильно работает с кириллицей.
- **Цена в копейках целым числом.** С дробными числами (`REAL`) суммы дают ошибки округления вроде `0.1 + 0.2 = 0.30000000000000004`. Рубли получаются делением на 100 при выводе.
- **Цена за позицию, а не за штуку.** По ТЗ при объединении цены складываются — это имеет смысл только для цены всей позиции.

## Правила изменения данных

| Действие | Что происходит в базе |
|----------|------------------------|
| Добавить товар, такого `name_key` в списке нет | `INSERT` новой строки, `bought = 0` |
| Добавить товар, такой `name_key` уже есть | `UPDATE`: `qty = qty + новое`; цены складываются (`NULL` считается 0, но `NULL + NULL = NULL`); `bought = 0` |
| Отметить / снять отметку | `UPDATE items SET bought = 1 / 0` |
| Удалить товар | `DELETE` строки |
| Переименовать список | `UPDATE lists SET name` |
| Удалить список | `DELETE` из `lists`; его товары удаляются каскадом |

Каждое изменение выполняется в транзакции (`with conn:` в `db.py`).

## Итоги

Итоги не хранятся — они считаются при каждом запросе списка (`list_view` в `app.py`). Тот же расчёт на SQL:

```sql
SELECT
    COUNT(*)                                             AS total_count,
    COALESCE(SUM(bought), 0)                             AS bought_count,
    COUNT(*) - COALESCE(SUM(bought), 0)                  AS left_count,
    COALESCE(SUM(price_cents), 0)                        AS total_cents,
    COALESCE(SUM(CASE WHEN bought = 1 THEN price_cents END), 0) AS bought_cents,
    COALESCE(SUM(CASE WHEN bought = 0 THEN price_cents END), 0) AS left_cents
FROM items
WHERE list_id = ?;
```

## Как заглянуть в базу

Из Claude Code удобнее всего через MCP-сервер `shopping-db` (только чтение): `list_lists`, `get_list`, `run_select`, `check_integrity`. `check_integrity` проверяет все правила из раздела выше: дубли, `name_key`, количество, цены, висячие товары.

Отдельная программа `sqlite3` не нужна — хватит Python из `.venv`:

```bash
.venv\Scripts\python.exe -X utf8 -c "import sqlite3; c = sqlite3.connect('shopping.db'); [print(r) for r in c.execute('SELECT * FROM lists')]"
```

```bash
.venv\Scripts\python.exe -X utf8 -c "import sqlite3; c = sqlite3.connect('shopping.db'); [print(r) for r in c.execute('SELECT id, list_id, name, qty, price_cents, bought FROM items')]"
```

Флаг `-X utf8` нужен, чтобы русские названия выводились в консоли Windows без ошибки кодировки.

Подойдёт и любая программа для SQLite, например DB Browser for SQLite. Вносить правки руками лучше при остановленном сервере и с `PRAGMA foreign_keys = ON`.

## Сброс и резервная копия

- **Начать с пустой базы:** остановить сервер, удалить `shopping.db`, запустить сервер снова.
- **Резервная копия:** остановить сервер и скопировать `shopping.db`. Восстановление — положить файл обратно.

## Изменение схемы

`CREATE TABLE IF NOT EXISTS` не меняет уже существующие таблицы. Если в `schema.sql` добавлена колонка, старой базе нужен отдельный `ALTER TABLE`, например:

```sql
ALTER TABLE items ADD COLUMN department TEXT;
```

Сложные изменения (новые ограничения, смена типа) в SQLite делаются через новую таблицу: создать `items_new`, перенести данные `INSERT INTO … SELECT …`, удалить старую, переименовать новую. Перед этим — резервная копия.
