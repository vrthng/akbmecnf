"""
Обработчики callback-запросов.
"""
import base64
import json
import os

from aiogram import types
from aiogram.types import FSInputFile

from handlers.search import search_books
from keyboards.builders import build_book_formats_keyboard
from opds_client import FlibustaOPDS
from services.cache import CacheService
from services.download import DownloadService
from utils.logger import logger


def extract_book_id_from_callback(callback_data: str) -> str:
    """
    Извлекает ID книги из данных callback-запроса.
    
    Алгоритм:
        1. Разбивает строку callback_data по символу "_"
        2. Пытается декодировать base64 и распарсить JSON
        3. Если успешно, извлекает ID из JSON
        4. Если не удалось, возвращает вторую часть разбитой строки
    
    Args:
        callback_data: Строка данных из callback-запроса
        
    Returns:
        str: ID книги или None, если не удалось извлечь
    """
    parts = callback_data.split("_", 2)
    if len(parts) < 2:
        return None

    book_id_or_data = parts[1]
    try:
        book_data_json = base64.b64decode(book_id_or_data.encode('ascii')).decode('utf-8')
        book_data = json.loads(book_data_json)
        return book_data.get('id')
    except:
        return book_id_or_data


async def process_page_callback(
        callback: types.CallbackQuery,
        opds: FlibustaOPDS,
        cache_service: CacheService
):
    """
    Обработчик callback-запроса для пагинации результатов поиска.
    
    Алгоритм:
        1. Отвечает на callback-запрос
        2. Извлекает user_id, query и номер страницы из данных
        3. Получает закэшированные результаты поиска
        4. Если результаты есть, формирует текст и клавиатуру для нужной страницы
        5. Обновляет сообщение с новыми результатами
        6. Если результатов нет, выполняет новый поиск
    
    Args:
        callback: Объект callback-запроса от пользователя
        opds: Клиент OPDS для работы с Flibusta
        cache_service: Сервис кэширования результатов
    """
    try:
        await callback.answer()
    except Exception as e:
        logger.debug(f"Ошибка при ответе на callback: {e}")

    parts = callback.data.split("_", 2)
    if len(parts) >= 3:
        user_id = int(parts[1])
        query_page = parts[2]
        last_underscore = query_page.rfind("_")
        if last_underscore > 0:
            query = query_page[:last_underscore]
            page = int(query_page[last_underscore + 1:])
            logger.debug(f"Обработка пагинации: пользователь {user_id}, запрос '{query}', страница {page}")

            results = cache_service.get_search_results(user_id, query)
            if results:
                logger.debug(f"Найдены закэшированные результаты для пользователя {user_id}, запрос '{query}'")
                import config
                from keyboards.builders import build_results_keyboard
                from handlers.search import build_results_text

                results_per_page = config.RESULTS_PER_PAGE
                total_pages = (len(results) + results_per_page - 1) // results_per_page
                current_page = min(page, total_pages - 1)
                start_idx = current_page * results_per_page
                end_idx = min(start_idx + results_per_page, len(results))

                text = build_results_text(results, current_page, total_pages, start_idx, end_idx, opds)
                keyboard = build_results_keyboard(
                    results, current_page, total_pages, start_idx, end_idx,
                    user_id, query, opds, cache_service.books_info_cache
                )

                await callback.message.edit_text(
                    text,
                    reply_markup=keyboard.as_markup(),
                    parse_mode="HTML"
                )
            else:
                logger.info(f"Кэш пуст для пользователя {user_id}, запрос '{query}', выполняется новый поиск")
                await callback.message.edit_text("⏳ Обновляю результаты поиска...")
                await search_books(callback.message, query, page=0, opds=opds, cache_service=cache_service)


async def process_book_callback(
        callback: types.CallbackQuery,
        opds: FlibustaOPDS,
        cache_service: CacheService
):
    """
    Обработчик callback-запроса для выбора книги из результатов поиска.
    
    Алгоритм:
        1. Отвечает на callback-запрос с уведомлением о загрузке
        2. Извлекает ID книги из данных callback
        3. Ищет информацию о книге в кэше
        4. Если не найдено, запрашивает через OPDS API
        5. Сохраняет информацию о книге в кэш
        6. Получает доступные форматы для скачивания
        7. Формирует текст с информацией о книге
        8. Создает клавиатуру с форматами и ссылками
        9. Отправляет сообщение с обложкой (если есть) или без неё
    
    Args:
        callback: Объект callback-запроса от пользователя
        opds: Клиент OPDS для работы с Flibusta
        cache_service: Сервис кэширования результатов
    """
    try:
        await callback.answer("Загрузка информации о книге...")
    except Exception as e:
        logger.debug(f"Ошибка при ответе на callback: {e}")

    try:
        callback_data_parts = callback.data.split("_", 1)
        if len(callback_data_parts) < 2:
            logger.warning(f"Неверный формат callback данных: {callback.data}")
            await callback.message.answer("❌ Неверный формат запроса.")
            return

        book_id = callback_data_parts[1]
        logger.info(f"Обработка запроса информации о книге: ID={book_id}, пользователь={callback.from_user.id}")

        # Ищем книгу в кэше
        book_info = cache_service.find_book_in_cache(book_id, opds)

        if not book_info:
            logger.debug(f"Книга {book_id} не найдена в кэше, запрос через OPDS API")
            book_info = await opds.get_book_info(book_id)
        else:
            logger.debug(f"Книга {book_id} найдена в кэше")

        if not book_info:
            logger.warning(f"Книга {book_id} не найдена для пользователя {callback.from_user.id}")
            await callback.message.answer("❌ Книга не найдена.")
            return

        if not book_info.get('book_id'):
            book_info['book_id'] = book_id

        title = book_info.get('title')
        if title and title not in ['Новинки', 'По авторам', 'По сериям', 'По жанрам', 'Моя полка', 'None', None]:
            cache_service.set_book_info(book_id, title, book_info.get('authors', []))
            logger.debug(f"Информация о книге {book_id} ('{title}') сохранена в кэш")

        available_formats = opds.get_available_formats(book_info)
        logger.debug(f"Доступные форматы для книги {book_id}: {available_formats}")

        title = book_info.get('title')
        if not title or title == 'None' or title == 'Без названия':
            title = f'Книга ID: {book_id}'

        authors = ', '.join(book_info.get('authors', []))
        if not authors:
            authors = 'Неизвестный автор'

        text = f"📖 <b>{title}</b>\n\n"

        if authors and authors != 'Неизвестный автор':
            text += f"👤 <b>Автор:</b> {authors}\n\n"

        text += f"📄 <b>Доступные форматы:</b>\n"

        if not available_formats:
            text += "\n\n⚠️ Информация о доступных форматах не найдена. Используйте кнопку \"Открыть на Flibusta\" для проверки."

        view_url = book_info.get('book_url') or opds.get_book_download_url(book_id)
        keyboard = build_book_formats_keyboard(
            book_id, available_formats, view_url,
            cache_service.books_info_cache, book_info
        )

        cover_url = book_info.get('cover_url')
        if cover_url:
            try:
                await callback.message.answer_photo(
                    photo=cover_url,
                    caption=text,
                    reply_markup=keyboard.as_markup(),
                    parse_mode="HTML"
                )
                logger.debug(f"Обложка книги {book_id} успешно отправлена пользователю {callback.from_user.id}")
            except Exception as e:
                logger.warning(f"Ошибка отправки обложки для книги {book_id}: {e}")
                await callback.message.answer(
                    text,
                    reply_markup=keyboard.as_markup(),
                    parse_mode="HTML"
                )
        else:
            await callback.message.answer(
                text,
                reply_markup=keyboard.as_markup(),
                parse_mode="HTML"
            )
        logger.info(f"Информация о книге {book_id} успешно отправлена пользователю {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка при обработке callback для книги: {e}", exc_info=True)
        await callback.message.answer(
            f"❌ Произошла ошибка: {str(e)}"
        )


async def process_download_callback(
        callback: types.CallbackQuery,
        opds: FlibustaOPDS,
        cache_service: CacheService,
        download_service: DownloadService
):
    """
    Обработчик callback-запроса для загрузки книги в выбранном формате.
    
    Алгоритм:
        1. Отвечает на callback-запрос с уведомлением о начале загрузки
        2. Извлекает ID книги и формат файла из данных callback
        3. Получает информацию о книге из кэша или через API
        4. Сохраняет информацию в кэш для будущего использования
        5. Отправляет сообщение о прогрессе загрузки
        6. Выполняет загрузку файла через download_service
        7. Формирует подпись для файла
        8. Отправляет файл пользователю
        9. Удаляет временный файл и сообщение о прогрессе
    
    Args:
        callback: Объект callback-запроса от пользователя
        opds: Клиент OPDS для работы с Flibusta
        cache_service: Сервис кэширования результатов
        download_service: Сервис загрузки книг
    """
    try:
        await callback.answer("Начинаю загрузку...")
    except Exception as e:
        logger.debug(f"Ошибка при ответе на callback: {e}")

    try:
        parts = callback.data.split("_", 2)
        if len(parts) < 2:
            logger.warning(f"Неверный формат callback данных для загрузки: {callback.data}")
            await callback.message.answer("❌ Неверный формат запроса.")
            return

        book_id = extract_book_id_from_callback(callback.data)
        file_type = parts[2] if len(parts) > 2 else 'fb2'
        logger.info(f"Начало загрузки книги: ID={book_id}, формат={file_type}, пользователь={callback.from_user.id}")

        if not book_id:
            logger.warning(f"Не удалось извлечь ID книги из callback данных: {callback.data}")
            await callback.message.answer("❌ Не удалось определить ID книги.")
            return

        book_info_for_filename = cache_service.get_book_info_for_download(book_id)

        if not book_info_for_filename:
            book_info_for_filename = await opds.get_book_info(book_id)
            if book_info_for_filename:
                if not book_info_for_filename.get('book_id'):
                    book_info_for_filename['book_id'] = book_id
                if book_info_for_filename.get('title'):
                    cache_service.set_book_info(
                        book_id,
                        book_info_for_filename.get('title', ''),
                        book_info_for_filename.get('authors', [])
                    )

        progress_msg = await callback.message.answer(f"⏳ Загружаю книгу в формате {file_type.upper()}...")

        file_path, error_msg = await download_service.download_book(
            book_id, file_type, book_info_for_filename, callback, progress_msg
        )

        if file_path and not error_msg:
            logger.info(
                f"Книга {book_id} успешно загружена в формате {file_type}, размер файла: {os.path.getsize(file_path) if os.path.exists(file_path) else 'неизвестно'} байт")
            file_to_send = FSInputFile(file_path)

            book_info_for_caption = book_info_for_filename
            if not book_info_for_caption:
                book_info_for_caption = await opds.get_book_info(book_id)

            caption = download_service.get_caption_for_book(book_info_for_caption, file_type)

            await callback.message.answer_document(
                file_to_send,
                caption=caption
            )

            # Очистка временных файлов
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass

            try:
                await progress_msg.delete()
            except:
                pass

            try:
                await callback.answer("✅ Книга успешно загружена!")
            except Exception as e:
                logger.debug(f"Ошибка при ответе на callback: {e}")
        else:
            logger.warning(f"Ошибка загрузки книги {book_id} в формате {file_type}: {error_msg}")

    except Exception as e:
        logger.error(f"Критическая ошибка при загрузке книги: {e}", exc_info=True)
        await callback.message.answer(
            f"❌ Произошла ошибка: {str(e)}"
        )


async def process_back_callback(callback: types.CallbackQuery):
    """
    Обработчик callback-запроса для возврата к поиску книг.
    
    Алгоритм:
        1. Отвечает на callback-запрос
        2. Отправляет сообщение с инструкцией для нового поиска
    
    Args:
        callback: Объект callback-запроса от пользователя
    """
    logger.debug(f"Обработка callback back_to_search от пользователя {callback.from_user.id}")
    try:
        await callback.answer()
    except Exception as e:
        logger.debug(f"Ошибка при ответе на callback: {e}")
    await callback.message.answer(
        "🔍 Введите название книги или имя автора для поиска."
    )
