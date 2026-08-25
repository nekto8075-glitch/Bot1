import os
import asyncio
import sqlite3
import logging
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, types

# --- НАСТРОЙКИ ---
API_TOKEN = os.getenv('BOT_TOKEN', '8943596179:AAFZ4rN8jZI4vURgxKR6NOqipNcaQ__L3Jk')
LOG_GROUP_ID = -1003995649688
PORT = int(os.getenv('PORT', 10000))

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

def init_db():
    conn = sqlite3.connect('messages_cache.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS business_messages (
            message_id INTEGER PRIMARY KEY,
            chat_id INTEGER,
            user_name TEXT,
            text TEXT,
            sticker_id TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS muted_users (
            user_id INTEGER PRIMARY KEY,
            until_date TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_business_msg(message_id: int, chat_id: int, user_name: str, text: str, sticker_id: str = None):
    conn = sqlite3.connect('messages_cache.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR REPLACE INTO business_messages (message_id, chat_id, user_name, text, sticker_id) VALUES (?, ?, ?, ?, ?)',
        (message_id, chat_id, user_name, text, sticker_id)
    )
    conn.commit()
    conn.close()

def get_business_msg(message_id: int):
    conn = sqlite3.connect('messages_cache.db')
    cursor = conn.cursor()
    cursor.execute('SELECT chat_id, user_name, text, sticker_id FROM business_messages WHERE message_id = ?', (message_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def delete_business_msg(message_id: int):
    conn = sqlite3.connect('messages_cache.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM business_messages WHERE message_id = ?', (message_id,))
    conn.commit()
    conn.close()

# --- МУТ В БАЗЕ ---
def mute_user(user_id: int, minutes: int):
    conn = sqlite3.connect('messages_cache.db')
    cursor = conn.cursor()
    until_date = (datetime.now() + timedelta(minutes=minutes)).isoformat()
    cursor.execute('INSERT OR REPLACE INTO muted_users (user_id, until_date) VALUES (?, ?)', (user_id, until_date))
    conn.commit()
    conn.close()

def is_user_muted(user_id: int) -> bool:
    conn = sqlite3.connect('messages_cache.db')
    cursor = conn.cursor()
    cursor.execute('SELECT until_date FROM muted_users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        until_date = datetime.fromisoformat(row[0])
        if datetime.now() < until_date:
            return True
        else:
            unmute_user(user_id)
    return False

def unmute_user(user_id: int):
    conn = sqlite3.connect('messages_cache.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM muted_users WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

# --- ОБРАБОТКА ВХОДЯЩИХ БИЗНЕС-СООБЩЕНИЙ В ЛС ---
@dp.business_message()
async def handle_business_message(message: types.Message):
    sender = message.from_user
    text = message.text or message.caption or ""

    # Проверка на команду /mute (ответом на сообщение)
    if text.startswith("/mute"):
        args = text.split()
        minutes = 15
        if len(args) > 1 and args[1].isdigit():
            minutes = int(args[1])

        if message.reply_to_message and message.reply_to_message.from_user:
            target = message.reply_to_message.from_user
            mute_user(target.id, minutes)
            await message.reply(f"🤐 Пользователь {target.full_name} замучен на {minutes} мин.")
        else:
            await message.reply("Ответь этой командой на сообщение собеседника!")
        return

    # Проверка на команду /unmute (ответом на сообщение)
    if text.startswith("/unmute"):
        if message.reply_to_message and message.reply_to_message.from_user:
            target = message.reply_to_message.from_user
            unmute_user(target.id)
            await message.reply(f"🔊 Пользователь {target.full_name} размучен.")
        return

    if not sender:
        return

    # Если отправитель в муте — удаляем его входящие сообщения
    if is_user_muted(sender.id):
        try:
            await message.delete()
            return
        except Exception as e:
            logging.error(f"Не удалось удалить сообщение: {e}")

    # Кэшируем обычные сообщения для логов
    user_name = sender.full_name
    if sender.username:
        user_name += f" (@{sender.username})"

    sticker_id = message.sticker.file_id if message.sticker else None
    msg_text = f"[Стикер {message.sticker.emoji or ''}]" if message.sticker else text or "[Медиасообщение]"

    save_business_msg(
        message_id=message.message_id,
        chat_id=message.chat.id,
        user_name=user_name,
        text=msg_text,
        sticker_id=sticker_id
    )

# --- ОБРАБОТКА ИЗМЕНЕННЫХ СООБЩЕНИЙ ---
@dp.edited_business_message()
async def handle_edited_business_message(message: types.Message):
    sender = message.from_user
    if not sender:
        return

    user_name = sender.full_name
    if sender.username:
        user_name += f" (@{sender.username})"

    new_text = message.text or message.caption or "[Медиасообщение]"
    cached_data = get_business_msg(message.message_id)

    old_text = cached_data[2] if cached_data else "Неизвестно (до запуска бота)"

    report = (
        f"✏️ **Сообщение отредактировано в ЛС!**\n\n"
        f"👤 **Автор:** {user_name}\n"
        f"🔻 **Было:** {old_text}\n"
        f"🔺 **Стало:** {new_text}"
    )

    try:
        await bot.send_message(chat_id=LOG_GROUP_ID, text=report)
    except Exception as e:
        logging.error(f"Ошибка отправки лога редактирования: {e}")

    sticker_id = message.sticker.file_id if message.sticker else None
    save_business_msg(
        message_id=message.message_id,
        chat_id=message.chat.id,
        user_name=user_name,
        text=new_text,
        sticker_id=sticker_id
    )

# --- ОБРАБОТКА УДАЛЕННЫХ СООБЩЕНИЙ ---
@dp.deleted_business_messages()
async def handle_deleted_business_messages(event: types.BusinessMessagesDeleted):
    for msg_id in event.message_ids:
        cached_data = get_business_msg(msg_id)
        if cached_data:
            chat_id, user_name, text, sticker_id = cached_data
            
            report = (
                f"🗑 **Удалено сообщение в ЛС!**\n\n"
                f"👤 **Автор:** {user_name}\n"
                f"💬 **Текст/Тип:** {text}"
            )
            
            try:
                await bot.send_message(chat_id=LOG_GROUP_ID, text=report)
                if sticker_id:
                    await bot.send_sticker(chat_id=LOG_GROUP_ID, sticker=sticker_id)
            except Exception as e:
                logging.error(f"Ошибка отправки лога: {e}")
                
            delete_business_msg(msg_id)

# Заглушка веб-сервера для Render
async def handle_web(request):
    return web.Response(text="Bot is running!")

async def web_server():
    app = web.Application()
    app.router.add_get("/", handle_web)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

async def main():
    init_db()
    await web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
