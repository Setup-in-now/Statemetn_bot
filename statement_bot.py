import asyncio
import sqlite3
import aiogram
import re
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, Filter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import os
import tempfile

from PyPDF2 import PdfReader
import fitz  # PyMuPDF

API_TOKEN = os.getenv("TELEGRAM_API_TOKEN")
if not API_TOKEN:
    raise ValueError("TELEGRAM_API_TOKEN environment variable not set")
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot=bot)

ALLOWED_USERS = [6881852604, 7044014332, 5938965495]
ADMIN_USERS = [6881852604, 7044014332]

main_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Список выписок", callback_data="list")],
        [InlineKeyboardButton(text="Добавить реквезит", callback_data="add")],
        [InlineKeyboardButton(text="Добавить ордер", callback_data="add_id")],
        [InlineKeyboardButton(text="Мои ордера", callback_data="number")],
        [InlineKeyboardButton(text="Удалить выписку", callback_data="delreq")],
        [InlineKeyboardButton(text="Прикрепить выписку", callback_data="attach_pdf")],
        [InlineKeyboardButton(text="Новые реквизиты", callback_data="seen_reqs")],
    ]
)

class AddReqStates(StatesGroup):
    waiting_for_req = State()
class AddOrderStates(StatesGroup):
    waiting_for_order = State()
class NumberStates(StatesGroup):
    waiting_for_number = State()
class DelReqStates(StatesGroup):
    waiting_for_delreq = State()
class PDFReqStates(StatesGroup):
    waiting_for_req = State()
    waiting_for_pdf = State()

def db_connect():
    conn = sqlite3.connect("requisites.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS requisites
                 (req TEXT PRIMARY KEY, date_time TEXT, trader TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS orders
                 (id TEXT, req TEXT, FOREIGN KEY(req) REFERENCES requisites(req))''')
    c.execute('''CREATE TABLE IF NOT EXISTS seen_reqs (req TEXT PRIMARY KEY)''')
    conn.commit()
    return conn

def add_requisite(req, date_time, trader):
    conn = db_connect()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO requisites VALUES (?, ?, ?)", (req, date_time, trader))
    conn.commit()
    conn.close()

def get_requisites():
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT req, date_time, trader FROM requisites")
    data = c.fetchall()
    conn.close()
    return data

def add_order(id_, req):
    conn = db_connect()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO orders VALUES (?, ?)", (id_, req))
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

def delete_requisite(req):
    conn = db_connect()
    c = conn.cursor()
    c.execute("DELETE FROM orders WHERE req=?", (req,))
    c.execute("DELETE FROM requisites WHERE req=?", (req,))
    conn.commit()
    conn.close()

def extract_req_from_pdf(file_path):
    try:
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        match = re.search(r"\b\d{10,}\b", text)
        if match:
            return match.group(0)
        return None
    except Exception:
        return None

def get_seen_reqs():
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT req FROM seen_reqs")
    data = c.fetchall()
    conn.close()
    return [row[0] for row in data]

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "Выберите действие:",
        reply_markup=main_menu
    )

@dp.callback_query()
async def process_callback(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bot_msg_ids = data.get("bot_msg_ids", [])
    for msg_id in bot_msg_ids:
        try:
            await callback.message.bot.delete_message(callback.message.chat.id, msg_id)
        except Exception:
            pass
    await state.update_data(bot_msg_ids=[])

    user_id = callback.from_user.id
    if callback.data == "list":
        if user_id not in ALLOWED_USERS:
            msg = await callback.message.answer("У вас нет доступа к этой команде.")
            await state.update_data(bot_msg_ids=[msg.message_id])
        else:
            data = get_requisites()
            if not data:
                msg = await callback.message.answer("Нет данных.")
                await state.update_data(bot_msg_ids=[msg.message_id])
            else:
                result = []
                for req, date_time, trader in data:
                    orders_count = count_orders(req)
                    pdf_path = f"pdfs/{req}.pdf"
                    pdf_note = " +выписка" if os.path.exists(pdf_path) else ""
                    result.append(f"{req} — {date_time} — {trader} — ордеров: {orders_count}{pdf_note}")
                msg = await callback.message.answer("\n".join(result))
                await state.update_data(bot_msg_ids=[msg.message_id])
        try:
            await callback.answer()
        except aiogram.exceptions.TelegramBadRequest as e:
            if "query is too old" in str(e):
                pass
            else:
                raise
    elif callback.data == "add":
        msg = await callback.message.answer(
            "Введите реквизит, дату, время и ник через пробел (например: 1234567890 20.06.2025 12:00 trader_nick):"
        )
        await state.set_state(AddReqStates.waiting_for_req)
        await state.update_data(bot_msg_ids=[msg.message_id])
        try:
            await callback.answer()
        except aiogram.exceptions.TelegramBadRequest as e:
            if "query is too old" in str(e):
                pass
            else:
                raise
    elif callback.data == "add_id":
        msg = await callback.message.answer("Введите id и реквизит через пробел (например: 1234567890 1234567890):")
        await state.set_state(AddOrderStates.waiting_for_order)
        await state.update_data(bot_msg_ids=[msg.message_id])
        try:
            await callback.answer()
        except aiogram.exceptions.TelegramBadRequest as e:
            if "query is too old" in str(e):
                pass
            else:
                raise
    elif callback.data == "number":
        msg = await callback.message.answer("Введите реквизит для просмотра ордеров:")
        await state.set_state(NumberStates.waiting_for_number)
        await state.update_data(bot_msg_ids=[msg.message_id])
        try:
            await callback.answer()
        except aiogram.exceptions.TelegramBadRequest as e:
            if "query is too old" in str(e):
                pass
            else:
                raise
    elif callback.data == "delreq":
        if user_id not in ADMIN_USERS:
            msg = await callback.message.answer("У вас нет прав для удаления выписок.")
            await state.update_data(bot_msg_ids=[msg.message_id])
        else:
            msg = await callback.message.answer("Введите реквизит для удаления:")
            await state.set_state(DelReqStates.waiting_for_delreq)
            await state.update_data(bot_msg_ids=[msg.message_id])
        try:
            await callback.answer()
        except aiogram.exceptions.TelegramBadRequest as e:
            if "query is too old" in str(e):
                pass
            else:
                raise
    elif callback.data == "attach_pdf":
        msg = await callback.message.answer("Введите реквизит, к которому прикрепить PDF-файл:")
        await state.set_state(PDFReqStates.waiting_for_req)
        await state.update_data(bot_msg_ids=[msg.message_id])
        try:
            await callback.answer()
        except aiogram.exceptions.TelegramBadRequest as e:
            if "query is too old" in str(e):
                pass
            else:
                raise
    elif callback.data == "seen_reqs":
        if user_id not in ADMIN_USERS:
            msg = await callback.message.answer("У вас нет доступа к этой команде.")
            await state.update_data(bot_msg_ids=[msg.message_id])
        else:
            seen = get_seen_reqs()
            if not seen:
                msg = await callback.message.answer("Нет новых замеченных реквизитов.")
            else:
                msg = await callback.message.answer("Замеченные реквизиты:\n" + "\n".join(seen))
            await state.update_data(bot_msg_ids=[msg.message_id])
        try:
            await callback.answer()
        except aiogram.exceptions.TelegramBadRequest as e:
            if "query is too old" in str(e):
                pass
            else:
                raise

@dp.message(PDFReqStates.waiting_for_req)
async def pdfreq_get_req(message: types.Message, state: FSMContext):
    req = message.text.strip()
    data = await state.get_data()
    ids = data.get("bot_msg_ids", [])
    if req not in [r[0] for r in get_requisites()]:
        msg = await message.answer("Такого реквизита нет. Сначала добавьте его через 'Добавить выписку'.")
        ids.append(msg.message_id)
        await state.update_data(bot_msg_ids=ids)
        await message.delete()
        return
    await state.update_data(pdf_req=req, bot_msg_ids=ids)
    msg = await message.answer("Теперь отправьте PDF-файл выписки.")
    ids.append(msg.message_id)
    await state.update_data(bot_msg_ids=ids)
    await state.set_state(PDFReqStates.waiting_for_pdf)
    await message.delete()

@dp.message(PDFReqStates.waiting_for_pdf)
async def pdfreq_get_pdf(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        ids = data.get("bot_msg_ids", [])
        req = data.get("pdf_req")
        if not req:
            msg = await message.answer("Ошибка: реквизит не найден. Начните заново.")
            ids.append(msg.message_id)
            await state.update_data(bot_msg_ids=ids)
            await state.clear()
            await message.delete()
            return
        if not message.document or not message.document.file_name.lower().endswith(".pdf"):
            msg = await message.answer("Пожалуйста, отправьте PDF-файл.")
            ids.append(msg.message_id)
            await state.update_data(bot_msg_ids=ids)
            await message.delete()
            return
        file = await bot.get_file(message.document.file_id)
        file_path = file.file_path
        os.makedirs("pdfs", exist_ok=True)
        save_path = f"pdfs/{req}.pdf"
        import shutil
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            await bot.download_file(file_path, tmp.name)
            with open(save_path, "wb") as f_out, open(tmp.name, "rb") as f_in:
                shutil.copyfileobj(f_in, f_out)
            os.unlink(tmp.name)
        msg = await message.answer(f"PDF-файл прикреплён к реквизиту {req}.")
        ids.append(msg.message_id)
        await state.update_data(bot_msg_ids=ids)
        await state.clear()
        await message.delete()
    except Exception as e:
        print("Ошибка при обработке PDF:", e)
        await message.answer("Произошла ошибка при сохранении PDF. Сообщите администратору.")

@dp.message(AddReqStates.waiting_for_req)
async def process_req(message: types.Message, state: FSMContext):
    parts = message.text.strip().split(maxsplit=3)
    data = await state.get_data()
    ids = data.get("bot_msg_ids", [])
    if len(parts) != 4:
        msg = await message.answer("Формат: <реквизит> <дата> <время> <ник>\nПример: 1234567890 20.06.2025 12:00 trader_nick")
        ids.append(msg.message_id)
        await state.update_data(bot_msg_ids=ids)
        await message.delete()
        return
    req, date, time, trader = parts
    date_time = f"{date} {time}"
    add_requisite(req, date_time, trader)
    msg = await message.answer(f"Добавлен реквизит {req} с датой и временем {date_time} и трейдером {trader}")
    ids.append(msg.message_id)
    await state.update_data(bot_msg_ids=ids)
    await message.delete()
    await state.clear()

@dp.message(AddOrderStates.waiting_for_order)
async def process_order(message: types.Message, state: FSMContext):
    parts = message.text.strip().split(maxsplit=1)
    data = await state.get_data()
    ids = data.get("bot_msg_ids", [])
    if len(parts) != 2:
        msg = await message.answer("Формат: <id> <реквизит>")
        ids.append(msg.message_id)
        await state.update_data(bot_msg_ids=ids)
        await message.delete()
        return
    id_, req = parts
    if req not in [r[0] for r in get_requisites()]:
        msg = await message.answer("Сначала добавьте реквизит через 'Добавить выписку'.")
        ids.append(msg.message_id)
        await state.update_data(bot_msg_ids=ids)
        await message.delete()
        return
    add_order(id_, req)
    msg = await message.answer(f"Добавлен ордер {id_} к реквизиту {req}")
    ids.append(msg.message_id)
    await state.update_data(bot_msg_ids=ids)
    await message.delete()
    await state.clear()

@dp.message(NumberStates.waiting_for_number)
async def process_number(message: types.Message, state: FSMContext):
    req = message.text.strip()
    data = await state.get_data()
    ids = data.get("bot_msg_ids", [])
    orders = get_orders(req)
    if not orders:
        msg = await message.answer("Нет ордеров по этому реквизиту.")
        ids.append(msg.message_id)
        await state.update_data(bot_msg_ids=ids)
        await message.delete()
    else:
        msg = await message.answer("ID ордеров для реквизита " + req + ":\n" + "\n".join(orders))
        ids.append(msg.message_id)
        # Если есть PDF — отправить его
        pdf_path = f"pdfs/{req}.pdf"
        if os.path.exists(pdf_path):
            await message.answer_document(types.FSInputFile(pdf_path), caption=f"Выписка для реквизита {req}")
        await state.update_data(bot_msg_ids=ids)
        await message.delete()
    await state.clear()

@dp.message(DelReqStates.waiting_for_delreq)
async def process_delreq(message: types.Message, state: FSMContext):
    req = message.text.strip()
    data = await state.get_data()
    ids = data.get("bot_msg_ids", [])
    if req not in [r[0] for r in get_requisites()]:
        msg = await message.answer("Такого реквизита нет.")
        ids.append(msg.message_id)
        await state.update_data(bot_msg_ids=ids)
        await message.delete()
        return
    delete_requisite(req)
    msg = await message.answer(f"Реквизит {req} и все его ордера удалены.")
    ids.append(msg.message_id)
    await state.update_data(bot_msg_ids=ids)
    await message.delete()
    await state.clear()

# ID группы, куда бот будет отправлять выписки и где слушает сообщения
TARGET_GROUP_ID = -1002762638022  # замените на ваш ID группы
ALERT_CHAT_ID = -1002762638022    # id чата alert-бота (может быть другой)

class IsReplyToPDF(Filter):
    async def __call__(self, message: types.Message) -> bool:
        return (
            message.reply_to_message is not None and
            message.reply_to_message.document is not None and
            message.reply_to_message.document.file_name.lower().endswith('.pdf')
        )

class NotReplyToPDF(Filter):
    async def __call__(self, message: types.Message) -> bool:
        return not (
            message.reply_to_message is not None and
            message.reply_to_message.document is not None and
            message.reply_to_message.document.file_name.lower().endswith('.pdf')
        )

@dp.message(IsReplyToPDF())
async def handle_reply_search(message: types.Message):
    print("handle_reply_search called", message.text)

    if message.reply_to_message and message.reply_to_message.document:
        doc = message.reply_to_message.document
        if doc.file_name.lower().endswith('.pdf'):
            file = await bot.get_file(doc.file_id)
            file_path = file.file_path
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                await bot.download_file(file_path, tmp.name)
                pdf_path = tmp.name
            query = message.text.strip()
            if not query:
                await message.answer("Укажите, что искать в выписке.", reply_to_message_id=message.message_id)
                return

            # Получаем сумму из caption PDF-сообщения или из базы (пример: ищем в caption)
            amount = None
            if message.reply_to_message.caption:
                # Пример: "Сумма 3000 найдена и выделена в выписке по реквизиту ..."
                import re
                m = re.search(r"Сумма (\d+)", message.reply_to_message.caption)
                if m:
                    amount = m.group(1)
            # Если не нашли сумму — можно запросить у пользователя или не искать
            if not amount:
                await message.answer("Не удалось определить сумму для поиска совместно с запросом.", reply_to_message_id=message.message_id)
                return

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                highlighted_path = tmp.name
            if highlight_amount_and_query_in_pdf(pdf_path, amount, query, highlighted_path):
                await message.answer_document(
                    types.FSInputFile(highlighted_path),
                    caption=f"Найдено совпадение по сумме {amount} и запросу '{query}'.",
                    reply_to_message_id=message.message_id
                )
            else:
                await message.answer(
                    f"Совпадений по сумме {amount} и запросу '{query}' не найдено.",
                    reply_to_message_id=message.message_id
                )

@dp.message(NotReplyToPDF())
async def handle_group_message(message: types.Message):
    print("handle_group_message called", message.text)
    if not message.text or message.chat.id != TARGET_GROUP_ID:
        return

    all_reqs = [r[0] for r in get_requisites()]
    lines = [line for line in message.text.splitlines() if line.strip()]
    if len(lines) < 2:
        return
    if len(lines) == 2:
        amount = lines[0]
        req = lines[1]
        possible_id = None
    elif len(lines) >= 3:
        possible_id = lines[0]
        amount = lines[1]
        req = lines[-1]
    else:
        return
    if not re.fullmatch(r"\d{10,}", req):
        return
    if req not in all_reqs:
        # Новый реквизит — алертим и добавляем в seen_reqs (реплаем)
        await bot.send_message(
            ALERT_CHAT_ID,
            f"⚠️ Замечен новый реквизит: {req}",
            reply_to_message_id=message.message_id
        )
        conn = db_connect()
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO seen_reqs (req) VALUES (?)", (req,))
        conn.commit()
        conn.close()
    else:
        # Реквизит есть — добавляем id, если его ещё нет
        existing_ids = get_orders(req)
        pdf_path = f"pdfs/{req}.pdf"
        if possible_id not in existing_ids:
            add_order(possible_id, req)
            await bot.send_message(
                message.chat.id,
                f"Добавлен ордер {possible_id} к реквизиту {req}"
            )
            # Если есть PDF — отправить его обычным сообщением
            if os.path.exists(pdf_path):
                await bot.send_document(
                    chat_id=TARGET_GROUP_ID,
                    document=types.FSInputFile(pdf_path),
                    caption=f"Выписка по реквизиту {req}"
                )
        else:
            # Если ордер уже есть — только PDF реплаем, без текста!
            if os.path.exists(pdf_path):
                await bot.send_document(
                    chat_id=TARGET_GROUP_ID,
                    document=types.FSInputFile(pdf_path),
                    caption=f"Выписка по реквизиту {req}",
                    reply_to_message_id=message.message_id
                )
    if len(lines) >= 3:
        amount = lines[1]  # сумма на второй строке
    else:
        amount = None

    if os.path.exists(pdf_path) and amount:

        amount = amount.replace(' ', '')
        if pdf_contains_amount(pdf_path, amount):
            await bot.send_message(
                message.chat.id,
                f"Сумма {amount} найдена в выписке по реквизиту {req}",
                reply_to_message_id=message.message_id
            )
        else:
            await bot.send_message(
                message.chat.id,
                f"Сумма {amount} не найдена в выписке по реквизиту {req}",
                reply_to_message_id=message.message_id
            )
    if os.path.exists(pdf_path) and amount and pdf_contains_amount(pdf_path, amount):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            highlighted_path = tmp.name
        if highlight_amount_in_pdf(pdf_path, amount, highlighted_path):
            await bot.send_document(
                chat_id=TARGET_GROUP_ID,
                document=types.FSInputFile(highlighted_path),
                caption=f"Сумма {amount} найдена и выделена в выписке по реквизиту {req}",
                reply_to_message_id=message.message_id
            )
        else:
            await bot.send_message(
                message.chat.id,
                f"Сумма {amount} найдена, но выделить не удалось.",
                reply_to_message_id=message.message_id
            )
def pdf_contains_amount(pdf_path, amount: str) -> bool:
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        text = text.replace('\xa0', ' ').replace('\u202f', ' ')
        patterns = make_amount_regex(amount)
        print("PATTERNS:", patterns)
        for pattern in patterns:
            if re.search(pattern, text):
                return True
        return False
    except Exception:
        return False

def highlight_amount_in_pdf(pdf_path, amount, out_path):
    doc = fitz.open(pdf_path)
    found = False
    patterns = make_amount_regex(amount)
    for page in doc:
        text = page.get_text("text").replace('\xa0', ' ').replace('\u202f', ' ')
        print("=== PAGE TEXT ===")
        print(repr(text))
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                inst = page.search_for(match.group())
                for rect in inst:
                    page.add_highlight_annot(rect)
                    found = True
    if found:
        doc.save(out_path)
    doc.close()
    return found

def highlight_text_in_pdf(pdf_path, text, out_path):
    doc = fitz.open(pdf_path)
    found = False
    for page in doc:
        for inst in page.search_for(text):
            page.add_highlight_annot(inst)
            found = True
    if found:
        doc.save(out_path)
    doc.close()
    return found
def highlight_amount_and_query_in_pdf(pdf_path, amount, query, out_path):
    doc = fitz.open(pdf_path)
    found = False
    patterns = make_amount_regex(amount)
    for page in doc:
        lines = [line.replace('\xa0', ' ').replace('\u202f', ' ') for line in page.get_text("text").splitlines()]
        window_size = 10
        for i in range(len(lines) - window_size + 1):
            window = "\n".join(lines[i:i+window_size])
            # Если в окне есть сумма и запрос
            if any(re.search(pattern, window) for pattern in patterns) and re.search(re.escape(query), window, re.IGNORECASE):
                print("Совпадение найдено в окне:\n", window)
                # Теперь выделяем только строки, где есть сумма или запрос
                for line in lines[i:i+window_size]:
                    is_amount = any(re.search(pattern, line) for pattern in patterns)
                    is_query = re.search(re.escape(query), line, re.IGNORECASE)
                    if is_amount or is_query:
                        for inst in page.search_for(line):
                            page.add_highlight_annot(inst)
                            found = True
    if found:
        doc.save(out_path)
    doc.close()
    return found
def make_amount_regex(amount):
    # amount: "10000"
    spaced = f"{amount[:-3]}[ \xa0\u202f]?{amount[-3:]}" if len(amount) > 3 else amount
    return [
        rf"\+?{amount}[.,]00\s?₽",
        rf"\+?{spaced}[.,]00\s?₽",
        rf"\+?{amount}\s?₽",
        rf"\+?{spaced}\s?₽",
        rf"\+?{amount}[.,]00",
        rf"\+?{spaced}[.,]00",
        rf"\+?{amount}",
        rf"\+?{spaced}",
        rf"-{amount}[.,]00\s?₽",
        rf"-{spaced}[.,]00\s?₽",
        rf"-{amount}\s?₽",
        rf"-{spaced}\s?₽",
        rf"-{amount}[.,]00",
        rf"-{spaced}[.,]00",
        rf"-{amount}",
        rf"-{spaced}",
    ]
if __name__ == "__main__":
    print("Бот запущен...")
    import asyncio
    asyncio.run(dp.start_polling(bot))