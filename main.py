import os
import asyncio
import sqlite3
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ChatPermissions

# --- ТВОИ НАСТРОЙКИ ---
API_TOKEN = os.getenv('BOT_TOKEN', '8943596179:AAFZ4rN8jZl4vURgxKR6NOqipNcaQ__L3Jk')
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

# --- КОМАНДА МУТА ДЛЯ ГРУПП ---
@dp.message(Command("mute"))
async def cmd_mute(message: types.Message):
    # Проверяем, что команда вызвана в группе или супергруппе
    if message.chat.type not in ["group", "supergroup"]:
        await message.reply("Команда /mute работает только в группах!")
        return

    # Проверяем права автора команды
    member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ["administrator", "creator"]:
        await message.reply("Эта команда доступна только администраторам.")
        return

    # Проверяем, сделан ли ответ на сообщение нарушителя
    if not message.reply_to_message:
        await message.reply("Ответь командой /mute на сообщение того, кого нужно замутить.")
        return

    args = message.text.split()
    minutes = 15  # Время мута по умолчанию (в минутах)
    
    if len(args) > 1 and args[1].isdigit():
        minutes = int(args[1])

    target_user = message.reply_to_message.from_user
    until_date = datetime.now() + timedelta(minutes=minutes)

    try:
        # Ограничиваем отправку сообщений
        await message.chat.restrict(
            user_id=target_user.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )
        await message.reply(f"🤐 Пользователь {target_user.full_name} замучен на {minutes} мин.")
    except Exception as e:
        await message.reply(f"Не удалось замутить пользователя. Убедись, что у бота есть права админа!\nОшибка: {e}")

# --- БИЗНЕС-ЛОГИКА (ПЕРЕХВАТ СООБЩЕНИЙ И СТИКЕРОВ) ---
@dp.business_message()
async def handle_business_message(message: types.Message):
    sender = message.from_user
    user_name = sender.full_name if sender else "Собеседник"
    if sender and sender.username:
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
                # Отправляем текстовый отчет
                await bot.send_message(chat_id=LOG_GROUP_ID, text=report)
                # Если удален стикер — отправляем сам стикер в канал
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
