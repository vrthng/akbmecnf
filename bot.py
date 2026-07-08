"""
Главный файл запуска Telegram бота для поиска и загрузки книг из Flibusta.
Работает через Webhook на Render
"""
import asyncio
import os
import sys
from flask import Flask, request

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command
from aiogram.types import Update

import config
from handlers import commands, callbacks, messages
from opds_client import FlibustaOPDS
from services.cache import CacheService
from services.download import DownloadService
from utils.logger import logger
from utils.whitelist import WhitelistFilter

# ===== ИНИЦИАЛИЗАЦИЯ =====
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(bot)

# Инициализация сервисов
opds = FlibustaOPDS()
cache_service = CacheService()
download_service = DownloadService(opds)

# ===== Flask для Webhook =====
app = Flask(__name__)

# ===== ВСЕ ОБРАБОТЧИКИ КОМАНД =====

@dp.message_handler(Command("start"))
async def cmd_start_handler(message: types.Message):
    logger.debug(f"Получена команда /start от пользователя {message.from_user.id}")
    await commands.cmd_start(message)

@dp.message_handler(Command("help"))
async def cmd_help_handler(message: types.Message):
    logger.debug(f"Получена команда /help от пользователя {message.from_user.id}")
    await commands.cmd_help(message)

@dp.message_handler(Command("search"))
async def cmd_search_handler(message: types.Message):
    query = message.text.replace("/search", "").strip()
    logger.debug(f"Получена команда /search от пользователя {message.from_user.id}, запрос: '{query}'")
    await commands.cmd_search(message, opds, cache_service)

@dp.callback_query_handler(lambda c: c.data.startswith("page_"))
async def process_page_callback_handler(callback: types.CallbackQuery):
    logger.debug(f"Получен callback page_ от пользователя {callback.from_user.id}, данные: {callback.data}")
    await callbacks.process_page_callback(callback, opds, cache_service)

@dp.callback_query_handler(lambda c: c.data.startswith("book_"))
async def process_book_callback_handler(callback: types.CallbackQuery):
    logger.debug(f"Получен callback book_ от пользователя {callback.from_user.id}, данные: {callback.data}")
    await callbacks.process_book_callback(callback, opds, cache_service)

@dp.callback_query_handler(lambda c: c.data.startswith("download_"))
async def process_download_callback_handler(callback: types.CallbackQuery):
    logger.debug(f"Получен callback download_ от пользователя {callback.from_user.id}, данные: {callback.data}")
    await callbacks.process_download_callback(callback, opds, cache_service, download_service)

@dp.callback_query_handler(lambda c: c.data == "back_to_search")
async def process_back_callback_handler(callback: types.CallbackQuery):
    logger.debug(f"Получен callback back_to_search от пользователя {callback.from_user.id}")
    await callbacks.process_back_callback(callback)

@dp.message_handler()
async def handle_text_message_handler(message: types.Message):
    logger.debug(
        f"Получено текстовое сообщение от пользователя {message.from_user.id}, текст: '{message.text[:50]}...'")
    await messages.handle_text_message(message, opds, cache_service)

@dp.callback_query_handler()
async def unauthorized_callback_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    logger.warning(f"Попытка доступа от неавторизованного пользователя {user_id}")
    try:
        await callback.answer()
    except:
        pass

# ===== ВЕБХУК =====

WEBHOOK_PATH = f"/{config.BOT_TOKEN}"

@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    """Принимает обновления от Telegram"""
    try:
        update_data = request.get_json()
        update = types.Update(**update_data)
        # Обрабатываем обновление в синхронном режиме
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(dp.process_update(update))
        return "OK", 200
    except Exception as e:
        logger.
        error(f"Ошибка в вебхуке: {e}")
        return "Error", 500

@app.route('/')
def health():
    """Проверка здоровья сервера"""
    return "Bot is running!", 200

@app.route('/health')
def health_check():
    return "OK", 200

# ===== НАСТРОЙКА ВЕБХУКА =====

def setup_webhook():
    """Устанавливает вебхук при запуске"""
    try:
        hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
        if not hostname:
            logger.warning("RENDER_EXTERNAL_HOSTNAME не установлен, пропускаем настройку вебхука")
            return
        
        webhook_url = f"https://{hostname}{WEBHOOK_PATH}"
        logger.info(f"Установка вебхука: {webhook_url}")
        
        # Удаляем старый вебхук и устанавливаем новый
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(bot.delete_webhook())
        loop.run_until_complete(bot.set_webhook(url=webhook_url))
        logger.info("Вебхук успешно установлен!")
    except Exception as e:
        logger.error(f"Ошибка при установке вебхука: {e}")

# ===== ЗАПУСК =====

if name == "__main__":
    # Настраиваем вебхук
    setup_webhook()
    
    # Запускаем Flask
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Запуск веб-сервера на порту {port}")
    
    app.run(host='0.0.0.0', port=port)
