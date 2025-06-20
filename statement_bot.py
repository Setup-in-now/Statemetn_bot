import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

API_TOKEN = '7462222631:AAF1yz4AtGOmRpBwSJSOL68Wrl7oV0gv2Us'

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot=bot)

# --- Работа с базой данных ---
def db_connect():
    conn = sqlite3.connect("requisites.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS requisites
                 (req TEXT PRIMARY KEY, date TEXT, trader TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS orders
                 (id TEXT, req TEXT, FOREIGN KEY(req) REFERENCES requisites(req))''')
    conn.commit()
    return conn

def add_requisite(req, date, trader):
    conn = db_connect()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO requisites VALUES (?, ?, ?)", (req, date, trader))
    conn.commit()
    conn.close()

def get_requisites():
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT req, date, trader FROM requisites")
    data = c.fetchall()
    conn.close()
    return data

def add_order(id_, req):
    conn = db_connect()
    c = conn.cursor()
    c.execute("INSERT INTO orders VALUES (?, ?)", (id_, req))
    conn.commit()
    conn.close()

def get_orders(req):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT id FROM orders WHERE req=?", (req,))
    data = c.fetchall()
    conn.close()
    return [row[0] for row in data]

def count_orders(req):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM orders WHERE req=?", (req,))
    count = c.fetchone()[0]
    conn.close()
    return count

# --- Команды ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "Привет! Для добавления реквизита используй команду:\n"
        "/add <реквизит> <дата> <ник>\n"
        "Пример: /add 1234567890 20.06.2025 trader_nick\n"
        "Для справки используй /help"
    )

@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        "Доступные команды:\n"
        "/start — начать работу\n"
        "/help — список команд\n"
        "/add <реквизит> <дата> <ник> — добавить реквизит\n"
        "/add_id <id> <реквизит> — добавить ордер к реквизиту\n"
        "/number <реквизит> — список ID ордеров по реквизиту\n"
        "/list — список реквизитов\n"
    )

@dp.message(Command("add"))
async def add_cmd(message: types.Message):
    parts = message.text.strip().split(maxsplit=3)
    if len(parts) != 4:
        await message.answer("Формат: /add <реквизит> <дата> <ник>")
        return
    _, req, date, trader = parts
    add_requisite(req, date, trader)
    await message.answer(f"Добавлен реквизит {req} с датой {date} и трейдером {trader}")

@dp.message(Command("add_id"))
async def add_id_cmd(message: types.Message):
    parts = message.text.strip().split(maxsplit=2)
    if len(parts) != 3:
        await message.answer("Формат: /add_id <id> <реквизит>")
        return
    _, id_, req = parts
    if req not in [r[0] for r in get_requisites()]:
        await message.answer("Сначала добавьте реквизит через /add.")
        return
    add_order(id_, req)
    await message.answer(f"Добавлен ордер {id_} к реквизиту {req}")

@dp.message(Command("number"))
async def number_cmd(message: types.Message):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Формат: /number <реквизит>")
        return
    _, req = parts
    orders = get_orders(req)
    if not orders:
        await message.answer("Нет ордеров по этому реквизиту.")
        return
    await message.answer("ID ордеров для реквизита " + req + ":\n" + "\n".join(orders))

@dp.message(Command("list"))
async def list_cmd(message: types.Message):
    data = get_requisites()
    if not data:
        await message.answer("Нет данных.")
        return
    result = []
    for req, date, trader in data:
        orders_count = count_orders(req)
        result.append(f"{req} — {date} — {trader} — ордеров: {orders_count}")
    await message.answer("\n".join(result))

@dp.message()
async def handle_message(message: types.Message):
    text = message.text.strip()

    # Команда /rek<реквизит>
    if text.startswith("/rek"):
        req = text[4:].strip()
        orders = get_orders(req)
        if orders:
            await message.answer("\n".join([f"ID: {oid}" for oid in orders]))
        else:
            await message.answer("Нет ордеров по этому реквизиту.")
        return

    # Добавление ордера к реквизиту: <id> <реквизит>
    if " " in text and text.split()[0].isdigit():
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Формат: <id> <реквизит>")
            return
        id_, req = parts
        if req not in [r[0] for r in get_requisites()]:
            await message.answer("Сначала добавьте реквизит через /add.")
            return
        add_order(id_, req)
        await message.answer(f"Добавлен ордер {id_} к реквизиту {req}")
        return

    await message.answer(
        "Не понял формат. Используй:\n"
        "/add <реквизит> <дата> <ник>\n"
        "<id> <реквизит>\n"
        "/list\n"
        "/rek<реквизит>\n"
        "или /help"
    )

if __name__ == "__main__":
    print("Бот запускается...")
    asyncio.run(dp.start_polling(bot))