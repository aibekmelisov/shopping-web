"""Shopping List: Flask-сервер и REST API."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import Flask, jsonify, render_template, request

import db


class ValidationError(Exception):
    def __init__(self, errors):
        super().__init__("; ".join(errors.values()))
        self.errors = errors  # {"поле": "сообщение"}


def create_app(database=None):
    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.json.sort_keys = False  # ошибки идут в порядке полей формы
    app.config["DATABASE"] = str(database or db.DEFAULT_DB_PATH)

    db.init_db(app.config["DATABASE"])
    app.teardown_appcontext(db.close_db)

    # ---------- валидация ----------

    def clean_name(value, errors, field="name", label="Название"):
        if not isinstance(value, str) or not value.strip():
            errors[field] = f"{label} не может быть пустым"
            return None
        name = " ".join(value.split())
        if len(name) > 100:
            errors[field] = f"{label} слишком длинное (максимум 100 символов)"
            return None
        return name

    def clean_qty(value, errors):
        if isinstance(value, bool):
            value = None
        if isinstance(value, str):
            value = value.strip()
            value = int(value) if value.lstrip("-").isdigit() else None
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        if not isinstance(value, int):
            errors["qty"] = "Количество должно быть целым числом"
            return None
        if value <= 0:
            errors["qty"] = "Количество должно быть больше нуля"
            return None
        if value > 1_000_000:
            errors["qty"] = "Количество слишком большое"
            return None
        return value

    def clean_price(value, errors):
        """Возвращает цену в копейках или None, если цена не указана."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        if isinstance(value, bool):
            errors["price"] = "Цена должна быть числом"
            return None
        try:
            price = Decimal(str(value).strip().replace(",", "."))
        except InvalidOperation:
            errors["price"] = "Цена должна быть числом"
            return None
        if not price.is_finite():
            errors["price"] = "Цена должна быть числом"
            return None
        if price < 0:
            errors["price"] = "Цена не может быть отрицательной"
            return None
        if price > Decimal("100000000"):
            errors["price"] = "Цена слишком большая"
            return None
        return int((price * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def body():
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}

    def not_found(what="Не найдено"):
        return jsonify(error=what), 404

    @app.errorhandler(ValidationError)
    def on_validation_error(exc):
        return jsonify(error=str(exc), errors=exc.errors), 400

    # ---------- представление списка ----------

    def list_view(list_id):
        lst = db.get_list(list_id)
        if lst is None:
            return None
        items = db.list_items(list_id)
        bought = [i for i in items if i["bought"]]
        left = [i for i in items if not i["bought"]]

        def money(rows):
            return sum(i["price_cents"] or 0 for i in rows)

        totals = {
            "total": {"count": len(items), "price_cents": money(items)},
            "bought": {"count": len(bought), "price_cents": money(bought)},
            "left": {"count": len(left), "price_cents": money(left)},
        }
        return {"list": lst, "items": items, "totals": totals}

    # ---------- страница ----------

    @app.get("/")
    def index():
        return render_template("index.html")

    # ---------- списки ----------

    @app.get("/api/lists")
    def api_lists():
        return jsonify(db.all_lists())

    @app.post("/api/lists")
    def api_create_list():
        errors = {}
        name = clean_name(body().get("name"), errors, label="Название списка")
        if errors:
            raise ValidationError(errors)
        return jsonify(db.create_list(name)), 201

    @app.get("/api/lists/<int:list_id>")
    def api_get_list(list_id):
        view = list_view(list_id)
        return jsonify(view) if view else not_found("Список не найден")

    @app.patch("/api/lists/<int:list_id>")
    def api_rename_list(list_id):
        errors = {}
        name = clean_name(body().get("name"), errors, label="Название списка")
        if errors:
            raise ValidationError(errors)
        if not db.rename_list(list_id, name):
            return not_found("Список не найден")
        return jsonify(db.get_list(list_id))

    @app.delete("/api/lists/<int:list_id>")
    def api_delete_list(list_id):
        if not db.delete_list(list_id):
            return not_found("Список не найден")
        return "", 204

    # ---------- товары ----------

    @app.post("/api/lists/<int:list_id>/items")
    def api_add_item(list_id):
        if db.get_list(list_id) is None:
            return not_found("Список не найден")
        data = body()
        errors = {}
        name = clean_name(data.get("name"), errors, label="Название товара")
        qty = clean_qty(data.get("qty"), errors)
        price = clean_price(data.get("price"), errors)
        if errors:
            raise ValidationError(errors)
        item, merged = db.add_item(list_id, name, qty, price)
        view = list_view(list_id)
        view.update(item=item, merged=merged)
        return jsonify(view), 200 if merged else 201

    @app.patch("/api/items/<int:item_id>")
    def api_update_item(item_id):
        bought = body().get("bought")
        if not isinstance(bought, bool):
            raise ValidationError({"bought": "Поле bought должно быть true или false"})
        item = db.get_item(item_id)
        if item is None:
            return not_found("Товар не найден")
        db.set_bought(item_id, bought)
        return jsonify(list_view(item["list_id"]))

    @app.delete("/api/items/<int:item_id>")
    def api_delete_item(item_id):
        item = db.get_item(item_id)
        if item is None:
            return not_found("Товар не найден")
        db.delete_item(item_id)
        return jsonify(list_view(item["list_id"]))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
