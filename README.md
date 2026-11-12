# Shopping List (веб)

Веб-приложение для списков покупок: Flask (сервер и REST API), SQLite (база), HTML, CSS и JavaScript (страница). Требования — в [TZ.md](TZ.md).

## Возможности

- Списки покупок: создать, переименовать, удалить (вместе с товарами).
- Товары: название, количество (целое > 0), цена за позицию (необязательно, можно с копейками: `40,50` или `40.50`).
- Отметка «куплено» и её снятие, удаление товара.
- Одинаковые товары в одном списке (без учёта регистра и лишних пробелов) объединяются: количество и цена складываются, отметка «куплено» снимается.
- Итоги внизу списка: всего, куплено, осталось — число позиций и сумма.
- Ошибки ввода показываются на странице.
- Данные хранятся в `shopping.db` и сохраняются после перезапуска.

## Требования

- Python 3.10 или новее (проверено на 3.14).

## Установка

Команды для Windows (PowerShell или cmd), из папки проекта.

1. Создать виртуальное окружение (если папки `.venv` ещё нет):

   ```bash
   python -m venv .venv
   ```

2. Установить зависимости:

   ```bash
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

<details>
<summary>macOS / Linux</summary>

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m flask --app app run
```

</details>

## Запуск

```bash
.venv\Scripts\python.exe -m flask --app app run
```

Откройте в браузере http://127.0.0.1:5000. Остановить сервер — **Ctrl+C**.

Если порт 5000 занят, укажите другой и откройте http://127.0.0.1:5001:

```bash
.venv\Scripts\python.exe -m flask --app app run --port 5001
```

База `shopping.db` создаётся автоматически при первом запуске. Чтобы начать с чистого листа, остановите сервер и удалите `shopping.db`.

## Структура

```
app.py              Flask: страница и REST API, проверка ввода, итоги
db.py               подключение к SQLite, запросы, объединение товаров
schema.sql          таблицы lists и items
templates/index.html  страница
static/style.css    стили
static/app.js       работа с API и отрисовка
shopping.db         база (создаётся сама)
mcp_server/server.py  MCP-сервер базы для Claude Code (только чтение)
.mcp.json           подключение MCP-сервера в Claude Code
.claude/skills/     skill с правилами проекта для Claude Code
docs/               CODE_GUIDE.md (код), DATABASE.md (база)
```

## MCP-сервер и skill для Claude Code

**MCP-сервер `shopping-db`** даёт Claude Code доступ к `shopping.db` **только на чтение**: списки и итоги (`list_lists`, `get_list`), поиск товара (`find_items`), схема (`describe_schema`), произвольный `SELECT` (`run_select`) и проверка целостности (`check_integrity`). Изменить данные через него нельзя — только через приложение.

- Нужен пакет `mcp` — он ставится вместе с остальными из `requirements.txt`.
- Подключение описано в `.mcp.json`. При первом открытии проекта Claude Code спросит, разрешить ли этот сервер.
- В `.mcp.json` указаны абсолютные пути к `.venv` и `mcp_server/server.py`. Если проект перенесён в другую папку, их нужно поправить.
- Другая база: переменная окружения `SHOPPING_DB` в разделе `env` в `.mcp.json`.

Проверить сервер вручную (запустится и будет ждать команд по stdio, выход — **Ctrl+C**):

```bash
.venv\Scripts\python.exe mcp_server\server.py
```

**Skill `shopping-web-conventions`** (`.claude/skills/shopping-web-conventions/SKILL.md`) — правила проекта для Claude Code: где какая логика, как хранить деньги и сравнивать названия, как менять схему, как проверять изменения и когда использовать MCP-инструменты. Claude Code подхватывает его сам, когда работает с этим проектом.

## REST API

| Метод | Путь | Что делает |
|-------|------|------------|
| GET | `/api/lists` | все списки |
| POST | `/api/lists` | создать список `{"name"}` |
| GET | `/api/lists/<id>` | список с товарами и итогами |
| PATCH | `/api/lists/<id>` | переименовать `{"name"}` |
| DELETE | `/api/lists/<id>` | удалить список и его товары |
| POST | `/api/lists/<id>/items` | добавить товар `{"name", "qty", "price"}` (или объединить с существующим) |
| PATCH | `/api/items/<id>` | отметить/снять отметку `{"bought": true\|false}` |
| DELETE | `/api/items/<id>` | удалить товар |

Цены в ответах — в копейках (`price_cents`). При ошибке ввода сервер отвечает `400` с полями `error` (текст) и `errors` (по полям).
