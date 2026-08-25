import os
import asyncio
import sqlite3
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# --- ТВОИ НАСТРОЙКИ ---
API_TOKEN = os.getenv('BOT_TOKEN', '8943596179:AAGKTnFE1Kd81NuX6osAB7EeR-EhNG9Qm14')
LOG_GROUP_ID = '@NewrebornSky'

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

# --- ФУНКЦИИ МУТА ---
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

# --- КОМАНДЫ МУТА В БИЗНЕС-ЧАТАХ (ЛС) ---
@dp.business_message(Command("mute"))
async def cmd_business_mute(message: types.Message):
    args = message.text.split() if message.text else []
    minutes = 15
    if len(args) > 1 and args[1].isdigit():
        minutes = int(args[1])

    target_user = None
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user

    if not target_user:
        await message.reply("Ответь командой `/mute [минуты]` на сообщение того, кого хочешь замутить.")
        return

    mute_user(target_user.id, minutes)
    await message.reply(f"🤐 Пользователь {target_user.full_name} замучен на {minutes} мин.")

@dp.business_message(Command("unmute"))
async def cmd_business_unmute(message: types.Message):
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        unmute_user(target_user.id)
        await message.reply(f"🔊 Пользователь {target_user.full_name} размучен.")

# --- ОБРАБОТКА ВХОДЯЩИХ СООБЩЕНИЙ В ЛС ---
@dp.business_message()
async def handle_business_message(message: types.Message):
    sender = message.from_user
    if not sender:
        return

    # Если человек в муте — удаляем его входящее сообщение
    if is_user_muted(sender.id):
        try:
            await message.delete()
            return
        except Exception as e:
            logging.error(f"Не удалось удалить сообщение: {e}")

    user_name = sender.full_name
    if sender.username:
        user_name += f" (@{sender.username})"

    sticker_id = None
    if message.sticker:
        msg_text = f"[Стикер {message.sticker.emoji or ''}]"
        sticker_id = message.sticker.file_id
    else:
        msg_text = message.text or message.caption or "[Медиасообщение без текста]"

    save_business_msg(
        message_id=message.message_id,
        chat_id=message.chat.id,
        user_name=user_name,
        text=msg_text,
        sticker_id=sticker_id
    )

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

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
