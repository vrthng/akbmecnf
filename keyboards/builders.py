"""
Построители клавиатур для бота.
"""
from typing import List, Dict

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from opds_client import FlibustaOPDS


def build_results_keyboard(
        results: List[Dict],
        current_page: int,
        total_pages: int,
        start_idx: int,
        end_idx: int,
        user_id: int,
        query: str,
        opds: FlibustaOPDS,
        books_info_cache: dict
) -> InlineKeyboardBuilder:
    """
    Создает инлайн-клавиатуру с результатами поиска книг.
    
    Алгоритм:
        1. Создает новый объект InlineKeyboardBuilder
        2. Извлекает книги для текущей страницы
        3. Для каждой книги создает кнопку с названием и ID
        4. Сохраняет информацию о книге в кэш
        5. Добавляет кнопки навигации (Назад/Вперед) при необходимости
        6. Настраивает расположение кнопок (по 1 в ряд)
    
    Args:
        results: Полный список найденных книг
        current_page: Номер текущей страницы
        total_pages: Общее количество страниц
        start_idx: Индекс начала текущей страницы
        end_idx: Индекс конца текущей страницы
        user_id: ID пользователя для формирования callback данных
        query: Поисковый запрос для формирования callback данных
        opds: Клиент OPDS для извлечения ID книги
        books_info_cache: Словарь для кэширования информации о книгах
        
    Returns:
        InlineKeyboardBuilder: Готовая инлайн-клавиатура с результатами поиска
    """
    keyboard = InlineKeyboardBuilder()
    page_results = results[start_idx:end_idx]

    for i, book in enumerate(page_results, start_idx + 1):
        title = book.get('title', 'Без названия')
        book_id = book.get('book_id') or opds._extract_book_id(book.get('id', ''))
        authors = book.get('authors', [])

        button_text = f"{i}. {title[:35]}"

        if book_id:
            books_info_cache[book_id] = {
                'title': title,
                'authors': authors
            }

        keyboard.add(
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"book_{book_id}"
            )
        )

    keyboard.adjust(1)

    nav_row = []
    if current_page > 0:
        nav_row.append(
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data=f"page_{user_id}_{query}_{current_page - 1}"
            )
        )
    if current_page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton(
                text="Вперед ▶️",
                callback_data=f"page_{user_id}_{query}_{current_page + 1}"
            )
        )

    if nav_row:
        keyboard.row(*nav_row)

    return keyboard


def build_book_formats_keyboard(
        book_id: str,
        available_formats: List[str],
        book_url: str,
        books_info_cache: dict,
        book_info: Dict
) -> InlineKeyboardBuilder:
    """
    Создает инлайн-клавиатуру с форматами для скачивания книги.
    
    Алгоритм:
        1. Создает новый объект InlineKeyboardBuilder
        2. Сохраняет информацию о книге в кэш
        3. Для каждого доступного формата создает кнопку скачивания
        4. Располагает кнопки форматов по 2 в ряд
        5. Добавляет кнопку для открытия книги на Flibusta
        6. Добавляет кнопку возврата к поиску
        7. Настраивает расположение всех кнопок
    
    Args:
        book_id: ID книги в системе Flibusta
        available_formats: Список доступных форматов (fb2, epub, mobi и т.д.)
        book_url: URL страницы книги на Flibusta
        books_info_cache: Словарь для кэширования информации о книгах
        book_info: Словарь с данными о книге
        
    Returns:
        InlineKeyboardBuilder: Готовая инлайн-клавиатура с форматами и ссылками
    """
    keyboard = InlineKeyboardBuilder()

    book_id_for_download = book_info.get('book_id') or book_id
    if book_id_for_download:
        books_info_cache[book_id_for_download] = {
            'title': book_info.get('title', ''),
            'authors': book_info.get('authors', [])
        }

    if available_formats:
        format_buttons = []
        for fmt in available_formats:
            format_name = fmt.upper() if fmt else 'FB2'
            format_buttons.append(
                InlineKeyboardButton(
                    text=f"📥 {format_name}",
                    callback_data=f"download_{book_id_for_download}_{fmt}"
                )
            )

        for i in range(0, len(format_buttons), 2):
            row_buttons = format_buttons[i:i + 2]
            keyboard.row(*row_buttons)

    keyboard.add(
        InlineKeyboardButton(
            text="🔗 Открыть на Flibusta",
            url=book_url
        )
    )

    keyboard.add(
        InlineKeyboardButton(
            text="🔙 Назад к поиску",
            callback_data="back_to_search"
        )
    )

    keyboard.adjust(2)

    return keyboard
