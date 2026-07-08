"""
Логика поиска книг.
"""
from typing import List, Dict

from aiogram import types

import config
from keyboards.builders import build_results_keyboard
from opds_client import FlibustaOPDS
from services.cache import CacheService
from utils.logger import logger


def build_results_text(results: List[Dict], current_page: int, total_pages: int, start_idx: int, end_idx: int,
                       opds: FlibustaOPDS) -> str:
    """
    Формирует текстовое представление результатов поиска для отправки пользователю.
    
    Алгоритм:
        1. Формирует заголовок с общим количеством найденных книг и номером страницы
        2. Итерируется по книгам в диапазоне текущей страницы
        3. Для каждой книги добавляет номер, название, авторов и доступные форматы
        4. Добавляет инструкцию для выбора книги
    
    Args:
        results: Полный список найденных книг
        current_page: Номер текущей страницы (начиная с 0)
        total_pages: Общее количество страниц
        start_idx: Индекс начала текущей страницы
        end_idx: Индекс конца текущей страницы
        opds: Клиент OPDS для получения доступных форматов
        
    Returns:
        str: Отформатированный текст с результатами поиска
    """
    text = f"📚 Найдено книг: {len(results)}\n"
    text += f"📄 Страница {current_page + 1} из {total_pages}\n\n"

    for i, book in enumerate(results[start_idx:end_idx], start_idx + 1):
        authors = ', '.join(book.get('authors', [])) or 'Неизвестный автор'
        title = book.get('title', 'Без названия')
        text += f"{i}. <b>{title}</b>\n"
        if authors:
            text += f"   👤 {authors}\n"
        formats = opds.get_available_formats(book)
        if formats:
            text += f"   📄 {', '.join([f.upper() for f in formats])}\n"
        text += "\n"

    text += "\n💡 Выберите книгу из списка для загрузки:"
    return text


async def search_books(
        message: types.Message,
        query: str,
        page: int = 0,
        opds: FlibustaOPDS = None,
        cache_service: CacheService = None
):
    """
    Выполняет поиск книг через OPDS API и отображает результаты пользователю.
    
    Алгоритм:
        1. Проверяет валидность запроса (минимум 2 символа)
        2. Инициализирует opds и cache_service, если не переданы
        3. Нормализует запрос (удаляет лишние пробелы)
        4. Отправляет сообщение о загрузке (только для первой страницы)
        5. Выполняет поиск через OPDS API
        6. Если результаты не найдены, отправляет сообщение об ошибке
        7. Сохраняет результаты в кэш
        8. Вычисляет параметры пагинации
        9. Формирует текст и клавиатуру с результатами
        10. Обновляет или отправляет сообщение с результатами
    
    Args:
        message: Объект сообщения от пользователя
        query: Поисковый запрос
        page: Номер страницы результатов (по умолчанию 0)
        opds: Клиент OPDS для работы с Flibusta (опционально)
        cache_service: Сервис кэширования результатов (опционально)
    """
    if not query or len(query) < 2:
        logger.debug(f"Запрос слишком короткий от пользователя {message.from_user.id}: '{query}'")
        await message.answer("❌ Запрос слишком короткий. Введите минимум 2 символа.")
        return

    if opds is None:
        opds = FlibustaOPDS()
    if cache_service is None:
        cache_service = CacheService()

    query = ' '.join(query.split()).strip()
    logger.info(f"Начало поиска: пользователь={message.from_user.id}, запрос='{query}', страница={page}")
    loading_msg = await message.answer("🔍 Ищу книги через OPDS API...") if page == 0 else None

    try:
        results = await opds.search_books(query, limit=config.MAX_SEARCH_RESULTS)

        if not results:
            logger.info(f"Книги не найдены для запроса '{query}' от пользователя {message.from_user.id}")
            if loading_msg:
                await loading_msg.edit_text(
                    f"❌ Книги по запросу \"{query}\" не найдены.\n\n"
                    "💡 Попробуйте:\n"
                    "• Использовать другое название или имя автора\n"
                    "• Упростить запрос\n"
                    "• Проверить правописание"
                )
            return

        logger.info(f"Найдено {len(results)} книг по запросу '{query}' для пользователя {message.from_user.id}")
        cache_service.set_search_results(message.from_user.id, query, results)

        results_per_page = config.RESULTS_PER_PAGE
        total_pages = (len(results) + results_per_page - 1) // results_per_page
        current_page = min(page, total_pages - 1)
        start_idx = current_page * results_per_page
        end_idx = min(start_idx + results_per_page, len(results))

        logger.debug(f"Пагинация: страница {current_page + 1}/{total_pages}, результаты {start_idx}-{end_idx}")
        text = build_results_text(results, current_page, total_pages, start_idx, end_idx, opds)
        keyboard = build_results_keyboard(
            results, current_page, total_pages, start_idx, end_idx,
            message.from_user.id, query, opds, cache_service.books_info_cache
        )

        if loading_msg:
            await loading_msg.edit_text(
                text,
                reply_markup=keyboard.as_markup(),
                parse_mode="HTML"
            )
        else:
            await message.edit_text(
                text,
                reply_markup=keyboard.as_markup(),
                parse_mode="HTML"
            )
        logger.info(f"Результаты поиска успешно отправлены пользователю {message.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка при поиске книг для запроса '{query}': {e}", exc_info=True)
        if loading_msg:
            await loading_msg.edit_text(
                f"❌ Произошла ошибка при поиске: {str(e)}\n\n"
                "Попробуйте позже или измените запрос."
            )
