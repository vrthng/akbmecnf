"""
Обработчики текстовых сообщений.
"""
from aiogram import types

from handlers.search import search_books
from utils.logger import logger


async def handle_text_message(message: types.Message, opds=None, cache_service=None):
    """
    Обработчик текстовых сообщений для поиска книг.
    
    Алгоритм:
        1. Извлекает текст сообщения и удаляет пробелы
        2. Проверяет длину запроса (минимум 2 символа)
        3. Если запрос слишком короткий, отправляет предупреждение
        4. Если запрос валиден, вызывает функцию поиска книг
    
    Args:
        message: Объект сообщения от пользователя
        opds: Клиент OPDS для работы с Flibusta (опционально)
        cache_service: Сервис кэширования (опционально)
    """
    query = message.text.strip()

    if len(query) < 2:
        logger.debug(f"Текстовое сообщение слишком короткое от пользователя {message.from_user.id}: '{query}'")
        await message.answer(
            "❌ Запрос слишком короткий. Введите минимум 2 символа.\n\n"
            "💡 Используйте /help для получения справки."
        )
        return

    logger.info(f"Текстовый запрос от пользователя {message.from_user.id}: '{query}'")
    await search_books(message, query, opds=opds, cache_service=cache_service)
