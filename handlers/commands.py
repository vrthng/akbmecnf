"""
Обработчики команд бота.
"""
from aiogram import types

from handlers.search import search_books
from utils.logger import logger


async def cmd_start(message: types.Message):
    """
    Обработчик команды /start.
    
    Алгоритм:
        1. Отправляет приветственное сообщение пользователю
        2. Информирует о возможностях бота
        3. Предлагает использовать /help для справки
    
    Args:
        message: Объект сообщения от пользователя
    """
    logger.info(f"Команда /start от пользователя {message.from_user.id} (@{message.from_user.username})")
    await message.answer(
        "📚 Привет! Я бот для поиска и загрузки книг из библиотеки Flibusta.\n\n"
        "🔍 Для поиска книги просто напишите название или имя автора.\n"
        "Например: \"Война и мир\" или \"Толстой\"\n\n"
        "💡 Используйте /help для получения справки."
    )


async def cmd_help(message: types.Message):
    """
    Обработчик команды /help.
    
    Алгоритм:
        1. Формирует текст справки с инструкциями по использованию бота
        2. Включает информацию о поиске, загрузке и примерах запросов
        3. Отправляет сообщение в формате HTML
    
    Args:
        message: Объект сообщения от пользователя
    """
    logger.debug(f"Команда /help от пользователя {message.from_user.id}")
    await message.answer(
        "📖 Справка по использованию бота:\n\n"
        "🔍 <b>Поиск книг</b>\n"
        "Просто напишите название книги или имя автора в чат.\n"
        "Поиск работает через OPDS API Flibusta!\n\n"
        "📥 <b>Загрузка книги</b>\n"
        "После поиска выберите нужную книгу из списка и выберите формат для загрузки.\n\n"
        "💡 <b>Примеры запросов:</b>\n"
        "• Война и мир\n"
        "• Толстой\n"
        "• Гарри Поттер\n"
        "• Достоевский Преступление\n\n"
        "✨ <b>Особенности:</b>\n"
        "• Поиск работает через OPDS API\n"
        "• Можно выбрать формат загрузки (FB2, EPUB, MOBI, PDF)\n"
        "• Результаты с пейджингом (по 5 на странице)",
        parse_mode="HTML"
    )


async def cmd_search(message: types.Message, opds=None, cache_service=None):
    """
    Обработчик команды /search.
    
    Алгоритм:
        1. Извлекает поисковый запрос из текста сообщения
        2. Проверяет наличие запроса
        3. Если запрос пустой, отправляет инструкцию по использованию
        4. Если запрос есть, вызывает функцию поиска книг
    
    Args:
        message: Объект сообщения от пользователя
        opds: Клиент OPDS для работы с Flibusta (опционально)
        cache_service: Сервис кэширования (опционально)
    """
    query = message.text.replace("/search", "").strip()

    if not query:
        logger.debug(f"Команда /search без запроса от пользователя {message.from_user.id}")
        await message.answer(
            "🔍 Использование: /search <запрос>\n\n"
            "Пример: /search Война и мир"
        )
        return

    logger.info(f"Команда /search от пользователя {message.from_user.id}, запрос: '{query}'")
    await search_books(message, query, opds=opds, cache_service=cache_service)
