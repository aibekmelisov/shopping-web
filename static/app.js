"use strict";

const $ = (id) => document.getElementById(id);

const state = {
    lists: [],
    currentId: null,
};

// ---------- API ----------

class ApiError extends Error {
    constructor(message, errors) {
        super(message);
        this.errors = errors || {};
    }
}

async function api(method, url, data) {
    const options = { method, headers: {} };
    if (data !== undefined) {
        options.headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(data);
    }
    let response;
    try {
        response = await fetch(url, options);
    } catch {
        throw new ApiError("Сервер недоступен. Проверьте, что он запущен.");
    }
    if (response.status === 204) return null;
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new ApiError(payload.error || `Ошибка ${response.status}`, payload.errors);
    }
    return payload;
}

// ---------- утилиты ----------

function formatMoney(cents) {
    if (cents === null || cents === undefined) return "—";
    return (cents / 100).toLocaleString("ru-RU", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
}

function showText(el, text) {
    el.textContent = text || "";
    el.hidden = !text;
}

function el(tag, props = {}, children = []) {
    const node = document.createElement(tag);
    Object.assign(node, props);
    for (const child of children) node.append(child);
    return node;
}

// ---------- списки ----------

function renderLists() {
    const ul = $("lists");
    ul.replaceChildren();
    for (const list of state.lists) {
        const btn = el("button", {
            type: "button",
            textContent: list.name,
            title: list.name,
            className: list.id === state.currentId ? "active" : "",
        });
        btn.addEventListener("click", () => openList(list.id));
        ul.append(el("li", {}, [btn]));
    }
    $("lists-empty").hidden = state.lists.length > 0;
}

async function loadLists() {
    state.lists = await api("GET", "/api/lists");
    renderLists();
}

async function openList(id) {
    try {
        const view = await api("GET", `/api/lists/${id}`);
        state.currentId = id;
        history.replaceState(null, "", `#list-${id}`);
        clearItemMessages();
        closeRename();
        renderListView(view);
        renderLists();
    } catch (err) {
        showNoList();
        if (state.currentId === id) state.currentId = null;
        renderLists();
    }
}

function showNoList() {
    state.currentId = null;
    $("list-view").hidden = true;
    $("placeholder").hidden = false;
    history.replaceState(null, "", location.pathname);
}

$("new-list-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = $("new-list-name");
    try {
        const list = await api("POST", "/api/lists", { name: input.value });
        input.value = "";
        input.classList.remove("invalid");
        showText($("new-list-error"), "");
        await loadLists();
        await openList(list.id);
    } catch (err) {
        input.classList.add("invalid");
        showText($("new-list-error"), err.message);
    }
});

// ---------- переименование и удаление списка ----------

function openRename() {
    const current = state.lists.find((l) => l.id === state.currentId);
    $("rename-input").value = current ? current.name : "";
    $("list-title").hidden = true;
    $("list-actions").hidden = true;
    $("rename-form").hidden = false;
    $("rename-input").focus();
    $("rename-input").select();
}

function closeRename() {
    $("list-title").hidden = false;
    $("list-actions").hidden = false;
    $("rename-form").hidden = true;
    $("rename-input").classList.remove("invalid");
    showText($("rename-error"), "");
}

$("rename-btn").addEventListener("click", openRename);
$("rename-cancel").addEventListener("click", closeRename);

$("rename-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
        const list = await api("PATCH", `/api/lists/${state.currentId}`, {
            name: $("rename-input").value,
        });
        $("list-title").textContent = list.name;
        closeRename();
        await loadLists();
    } catch (err) {
        $("rename-input").classList.add("invalid");
        showText($("rename-error"), err.message);
    }
});

$("delete-list-btn").addEventListener("click", async () => {
    const current = state.lists.find((l) => l.id === state.currentId);
    if (!current) return;
    if (!confirm(`Удалить список «${current.name}» вместе со всеми товарами?`)) return;
    try {
        await api("DELETE", `/api/lists/${current.id}`);
        showNoList();
        await loadLists();
    } catch (err) {
        showText($("rename-error"), err.message);
    }
});

// ---------- товары ----------

const fieldInputs = { name: "item-name", qty: "item-qty", price: "item-price" };

function clearItemMessages() {
    const list = $("item-errors");
    list.replaceChildren();
    list.hidden = true;
    showText($("item-notice"), "");
    for (const id of Object.values(fieldInputs)) $(id).classList.remove("invalid");
}

function showItemErrors(err) {
    const list = $("item-errors");
    list.replaceChildren();
    const messages = Object.keys(err.errors).length ? err.errors : { _: err.message };
    for (const [field, message] of Object.entries(messages)) {
        list.append(el("li", { textContent: message }));
        if (fieldInputs[field]) $(fieldInputs[field]).classList.add("invalid");
    }
    list.hidden = false;
}

function renderListView(view) {
    $("placeholder").hidden = true;
    $("list-view").hidden = false;
    $("list-title").textContent = view.list.name;

    const tbody = $("items");
    tbody.replaceChildren();
    for (const item of view.items) {
        const checkbox = el("input", {
            type: "checkbox",
            checked: item.bought,
            title: item.bought ? "Снять отметку" : "Отметить купленным",
        });
        checkbox.addEventListener("change", () => toggleItem(item.id, checkbox.checked));

        const del = el("button", {
            type: "button",
            className: "danger icon",
            textContent: "✕",
            title: "Удалить товар",
        });
        del.addEventListener("click", () => deleteItem(item.id));

        tbody.append(
            el("tr", { className: item.bought ? "bought" : "" }, [
                el("td", { className: "col-check" }, [checkbox]),
                el("td", { className: "name", textContent: item.name }),
                el("td", { className: "num", textContent: String(item.qty) }),
                el("td", { className: "num", textContent: formatMoney(item.price_cents) }),
                el("td", { className: "col-del" }, [del]),
            ])
        );
    }
    $("items-empty").hidden = view.items.length > 0;
    renderTotals(view.totals);
}

function renderTotals(totals) {
    const cards = [
        ["Всего", totals.total],
        ["Куплено", totals.bought],
        ["Осталось", totals.left],
    ];
    $("totals").replaceChildren(
        ...cards.map(([label, t]) =>
            el("div", { className: "card" }, [
                el("div", { className: "label", textContent: label }),
                el("div", { className: "value", textContent: `${t.count} поз.` }),
                el("div", { className: "money", textContent: `${formatMoney(t.price_cents)} ₽` }),
            ])
        )
    );
}

$("add-item-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    clearItemMessages();
    const data = {
        name: $("item-name").value,
        qty: $("item-qty").value,
        price: $("item-price").value,
    };
    try {
        const view = await api("POST", `/api/lists/${state.currentId}/items`, data);
        renderListView(view);
        if (view.merged) {
            showText(
                $("item-notice"),
                `«${view.item.name}» уже был в списке — количество и цена сложены.`
            );
        }
        $("item-name").value = "";
        $("item-qty").value = "1";
        $("item-price").value = "";
        $("item-name").focus();
    } catch (err) {
        showItemErrors(err);
    }
});

async function toggleItem(id, bought) {
    try {
        renderListView(await api("PATCH", `/api/items/${id}`, { bought }));
    } catch (err) {
        showItemErrors(err);
        await openList(state.currentId);
    }
}

async function deleteItem(id) {
    try {
        clearItemMessages();
        renderListView(await api("DELETE", `/api/items/${id}`));
    } catch (err) {
        showItemErrors(err);
    }
}

// ---------- старт ----------

async function openFromHash() {
    const match = location.hash.match(/^#list-(\d+)$/);
    if (match) await openList(Number(match[1]));
}

window.addEventListener("hashchange", openFromHash);

(async function start() {
    try {
        await loadLists();
    } catch (err) {
        showText($("new-list-error"), err.message);
        return;
    }
    await openFromHash();
})();
