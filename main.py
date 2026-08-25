import asyncio
import sqlite3
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.exceptions import TelegramBadRequest

# --- ТВОИ НАСТРОЙКИ ---
API_TOKEN = '8943596179:AAFBGtbA-4DWggK03e4Zzlib4Z5qKJ3EVDU'
LOG_GROUP_ID = '@NewrebornSky'

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

def init_db():
    conn = sqlite3.connect('messages_cache.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            message_id INTEGER PRIMARY KEY,
            chat_id INTEGER,
            user_name TEXT,
            text TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_msg(message_id: int, chat_id: int, user_name: str, text: str):
    conn = sqlite3.connect('messages_cache.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR REPLACE INTO messages (message_id, chat_id, user_name, text) VALUES (?, ?, ?, ?)',
        (message_id, chat_id, user_name, text)
    )
    conn.commit()
    conn.close()

def get_all_msgs():
    conn = sqlite3.connect('messages_cache.db')
    cursor = conn.cursor()
    cursor.execute('SELECT message_id, chat_id, user_name, text FROM messages')
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_msg_from_db(message_id: int):
    conn = sqlite3.connect('messages_cache.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM messages WHERE message_id = ?', (message_id,))
    conn.commit()
    conn.close()

@dp.message()
async def handle_incoming_message(message: types.Message):
    # Игнорируем сообщения из самого канала логов
    if str(message.chat.username) == 'NewrebornSky':
        return

    if message.text:
        user_name = message.from_user.full_name
        if message.from_user.username:
            user_name += f" (@{message.from_user.username})"

        save_msg(
            message_id=message.message_id,
            chat_id=message.chat.id,
            user_name=user_name,
            text=message.text
        )

async def check_deleted_loop():
    while True:
        await asyncio.sleep(5)
        records = get_all_msgs()
        
        for msg_id, chat_id, user_name, text in records:
            try:
                await bot.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=msg_id
                )
            except TelegramBadRequest as e:
                err_msg = str(e).lower()
                if "message is not modified" in err_msg:
                    continue
                
                if "message to edit not found" in err_msg or "message can't be edited" in err_msg:
                    report = (
                        f"🗑 **Удалено сообщение!**\n\n"
                        f"👤 **Автор:** {user_name}\n"
                        f"💬 **Текст:** {text}"
                    )
                    await bot.send_message(chat_id=LOG_GROUP_ID, text=report, parse_mode="Markdown")
                    delete_msg_from_db(msg_id)
            except Exception:
                pass

async def main():
    init_db()
    asyncio.create_task(check_deleted_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
