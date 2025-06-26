import asyncio
import sqlite3
import re
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from datetime import datetime, timedelta

API_TOKEN = '8001292292:AAErSSPAftQ0hBkdAzhOpXzVrPnDta10N9Y'
ALERT_CHAT_ID = -4654354066  # id чата для алертов
SOURCE_CHAT_ID = -1001234567890  # id чата, где бот ищет новые реквизиты (замените на свой)

def get_upcoming_requisites():
    """Все выписки, которые еще не наступили (date_time > сейчас)"""
    conn = sqlite3.connect("requisites.db")
    c = conn.cursor()
    c.execute("SELECT req, date_time, trader FROM requisites")
    data = c.fetchall()
    conn.close()
    now = datetime.now()
    upcoming = []
    for req, date_time_str, trader in data:
        try:
            dt = datetime.strptime(date_time_str, "%d.%m.%Y %H:%M")
            if dt > now:
                upcoming.append((req, date_time_str, trader))
        except Exception:
            continue
    return sorted(upcoming, key=lambda x: datetime.strptime(x[1], "%d.%m.%Y %H:%M"))

def get_due_requisites():
    """Все выписки, время которых уже наступило (date_time <= сейчас)"""
    conn = sqlite3.connect("requisites.db")
    c = conn.cursor()
    c.execute("SELECT req, date_time, trader FROM requisites")
    data = c.fetchall()
    conn.close()
    now = datetime.now()
    due = []
    for req, date_time_str, trader in data:
        try:
            dt = datetime.strptime(date_time_str, "%d.%m.%Y %H:%M")
            if dt <= now:
                due.append((req, date_time_str, trader))
        except Exception:
            continue
    return due

def req_in_main_table(req):
    conn = sqlite3.connect("requisites.db")
    c = conn.cursor()
    c.execute("SELECT 1 FROM requisites WHERE req=?", (req,))
    found = c.fetchone() is not None
    conn.close()
    return found

def add_seen_req(req):
    conn = sqlite3.connect("requisites.db")
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS seen_reqs (req TEXT PRIMARY KEY)")
    c.execute("INSERT OR IGNORE INTO seen_reqs (req) VALUES (?)", (req,))
    conn.commit()
    conn.close()

async def report_loop(bot):
    """Отправляет отчет по всем ожидаемым выпискам в 12:00 и 20:00"""
    while True:
        now = datetime.now()
        # Найти ближайшее 12:00 или 20:00
        next_times = [
            now.replace(hour=12, minute=0, second=0, microsecond=0),
            now.replace(hour=20, minute=0, second=0, microsecond=0)
        ]
        next_times = [t if t > now else t + timedelta(days=1) for t in next_times]
        next_report = min(next_times)
        wait_seconds = (next_report - now).total_seconds()
        print(f"[REPORT] Жду {wait_seconds/60:.1f} минут до следующей отправки отчета ({next_report.strftime('%H:%M')})")
        await asyncio.sleep(wait_seconds)

        upcoming = get_upcoming_requisites()
        if upcoming:
            text = "🗓 Ожидаемые выписки:\n"
            for req, date_time_str, trader in upcoming:
                text += f"{req} — {date_time_str} — {trader}\n"
        else:
            text = "Нет ожидаемых выписок."
        await bot.send_message(ALERT_CHAT_ID, text)

async def alert_loop(bot):
    """Алертит при наступлении времени выписки (каждую минуту)"""
    already_alerted = set()
    while True:
        due = get_due_requisites()
        for req, date_time_str, trader in due:
            key = f"{req}|{date_time_str}|{trader}"
            if key not in already_alerted:
                text = f"⚠️ Время выписки наступило!\n{req} — {date_time_str} — {trader}"
                await bot.send_message(ALERT_CHAT_ID, text)
                already_alerted.add(key)
        await asyncio.sleep(60)

async def handle_group_message(message: types.Message, bot: Bot):
    # Только для сообщений из SOURCE_CHAT_ID
    if message.chat.id != SOURCE_CHAT_ID:
        return
    if not message.text:
        return
    # Ищем все строки, похожие на реквизит (10+ цифр)
    lines = [line.strip() for line in message.text.splitlines()]
    for line in lines:
        match = re.fullmatch(r"\d{10,}", line)
        if match:
            req = match.group(0)
            if not req_in_main_table(req):
                # Новый реквизит — алертим и заносим в seen_reqs
                await bot.send_message(ALERT_CHAT_ID, f"⚠️ Замечен новый реквизит: {req}")
                add_seen_req(req)
            # Можно добавить логику для фиксации заявки по реквизиту
            break

async def main():
    bot = Bot(token=API_TOKEN)
    dp = Dispatcher()
    dp.message.register(lambda m: handle_group_message(m, bot))
    await bot.send_message(ALERT_CHAT_ID, "✅ Алерт-бот запущен и ожидает 12:00/20:00 для отправки отчетов и алертов по выпискам.")
    await asyncio.gather(
        report_loop(bot),
        alert_loop(bot),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())