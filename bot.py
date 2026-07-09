from flask import Flask
import threading
import os
import time
import requests

app = Flask(__name__)

@app.route('/')
def hello():
    return "I'm alive!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

"""
Главный файл запуска Telegram бота для поиска и загрузки книг из Flibusta.
"""
import asyncio

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

import config
from handlers import commands, callbacks, messages
from opds_client import FlibustaOPDS
from services.cache import CacheService
from services.download import DownloadService
from utils.logger import logger
from utils.whitelist import WhitelistFilter

# Инициализация бота и диспетчера
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

# Инициализация сервисов
opds = FlibustaOPDS()
cache_service = CacheService()
download_service = DownloadService(opds)


# Регистрация обработчиков команд
@dp.message(Command("start"), WhitelistFilter())
async def cmd_start_handler(message):
    logger.debug(f"Получена команда /start от пользователя {message.from_user.id}")
    await commands.cmd_start(message)


@dp.message(Command("help"), WhitelistFilter())
async def cmd_help_handler(message):
    logger.debug(f"Получена команда /help от пользователя {message.from_user.id}")
    await commands.cmd_help(message)


@dp.message(Command("search"), WhitelistFilter())
async def cmd_search_handler(message):
    query = message.text.replace("/search", "").strip()
    logger.debug(f"Получена команда /search от пользователя {message.from_user.id}, запрос: '{query}'")
    await commands.cmd_search(message, opds, cache_service)


# Регистрация обработчиков callback
@dp.callback_query(lambda c: c.data.startswith("page_"), WhitelistFilter())
async def process_page_callback_handler(callback):
    logger.debug(f"Получен callback page_ от пользователя {callback.from_user.id}, данные: {callback.data}")
    await callbacks.process_page_callback(callback, opds, cache_service)


@dp.callback_query(lambda c: c.data.startswith("book_"), WhitelistFilter())
async def process_book_callback_handler(callback):
    logger.debug(f"Получен callback book_ от пользователя {callback.from_user.id}, данные: {callback.data}")
    await callbacks.process_book_callback(callback, opds, cache_service)


@dp.callback_query(lambda c: c.data.startswith("download_"), WhitelistFilter())
async def process_download_callback_handler(callback):
    logger.debug(f"Получен callback download_ от пользователя {callback.from_user.id}, данные: {callback.data}")
    await callbacks.process_download_callback(callback, opds, cache_service, download_service)


@dp.callback_query(lambda c: c.data == "back_to_search", WhitelistFilter())
async def process_back_callback_handler(callback):
    logger.debug(f"Получен callback back_to_search от пользователя {callback.from_user.id}")
    await callbacks.process_back_callback(callback)


# Регистрация обработчика текстовых сообщений
@dp.message(WhitelistFilter())
async def handle_text_message_handler(message):
    logger.debug(
        f"Получено текстовое сообщение от пользователя {message.from_user.id}, текст: '{message.text[:50]}...'")
    await messages.handle_text_message(message, opds, cache_service)


# Обработчик для callback-запросов от неавторизованных пользователей (тихий ответ, чтобы избежать ошибок API)
@dp.callback_query()
async def unauthorized_callback_handler(callback: types.CallbackQuery):
    """Обработчик для callback-запросов от пользователей, не входящих в белый список."""
    user_id = callback.from_user.id
    logger.warning(f"Попытка доступа от неавторизованного пользователя {user_id}")
    # Тихий ответ, чтобы не было ошибок в Telegram API
    try:
        await callback.answer()
    except:
        pass


async def main():
    """
    Главная функция запуска Telegram бота.
    
    Алгоритм:
        1. Проверяет наличие BOT_TOKEN в конфигурации
        2. Выводит информацию о запуске бота
        3. Запускает polling для обработки сообщений
        4. Закрывает соединение с OPDS клиентом при завершении
    
    Raises:
        Exception: При ошибке запуска бота или polling
    """
    logger.info("Инициализация бота...")

    if not config.BOT_TOKEN:
        logger.critical(
            "BOT_TOKEN не установлен! Установите токен через переменную окружения BOT_TOKEN или в config.py")
        return

    logger.info("Бот запущен!")
    logger.info("Используется OPDS API Flibusta")
    logger.info("Готов к поиску книг...")

    try:
        logger.debug("Запуск polling для обработки сообщений")
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки (KeyboardInterrupt)")
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}", exc_info=True)
    finally:
        logger.debug("Закрытие соединения с OPDS клиентом")
        await opds.close()
        logger.info("Бот остановлен")


def keep_alive():
    """Раз в 590 секунд пингует себя, чтобы Render не усыпил"""
    while True:
        time.sleep(590)
        try:
            requests.get("http://localhost:10000/")
        except:
            pass
            
if name == "main":
    threading.Thread(target=run_web).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    asyncio.run(main())
