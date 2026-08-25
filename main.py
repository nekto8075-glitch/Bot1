import asyncio
import sqlite3
import logging
from aiogram import Bot, Dispatcher, types

# --- ТВОИ НАСТРОЙКИ ---
API_TOKEN = '8943596179:AAHgaOdD1MANELrQLb2kZBWd3z-dZW1mjHw'
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
            text TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_business_msg(message_id: int, chat_id: int, user_name: str, text: str):
    conn = sqlite3.connect('messages_cache.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR REPLACE INTO business_messages (message_id, chat_id, user_name, text) VALUES (?, ?, ?, ?)',
        (message_id, chat_id, user_name, text)
    )
    conn.commit()
    conn.close()

def get_business_msg(message_id: int):
    conn = sqlite3.connect('messages_cache.db')
    cursor = conn.cursor()
    cursor.execute('SELECT chat_id, user_name, text FROM business_messages WHERE message_id = ?', (message_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def delete_business_msg(message_id: int):
    conn = sqlite3.connect('messages_cache.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM business_messages WHERE message_id = ?', (message_id,))
    conn.commit()
    conn.close()

# 1. Сохранение сообщений (и твоих, и собеседника)
@dp.business_message()
async def handle_business_message(message: types.Message):
    msg_text = message.text or message.caption or "[Медиасообщение без текста]"

    sender = message.from_user
    user_name = sender.full_name if sender else "Собеседник"
    if sender and sender.username:
        user_name += f" (@{sender.username})"

    save_business_msg(
        message_id=message.message_id,
        chat_id=message.chat.id,
        user_name=user_name,
        text=msg_text
    )

# 2. Лог при удалении сообщения
@dp.deleted_business_messages()
async def handle_deleted_business_messages(event: types.BusinessMessagesDeleted):
    for msg_id in event.message_ids:
        cached_data = get_business_msg(msg_id)
        if cached_data:
            chat_id, user_name, text = cached_data
            
            report = (
                f"🗑 **Удалено сообщение в ЛС!**\n\n"
                f"👤 **Автор:** {user_name}\n"
                f"💬 **Текст:** {text}"
            )
            
            try:
                await bot.send_message(chat_id=LOG_GROUP_ID, text=report)
            except Exception as e:
                logging.error(f"Ошибка отправки лога: {e}")
                
            delete_business_msg(msg_id)

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
