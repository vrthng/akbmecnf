"""
Сервис загрузки книг.
"""
import asyncio
import os
from typing import Optional, Tuple

import aiohttp

import config
from opds_client import FlibustaOPDS
from utils.file_utils import process_zip_file
from utils.logger import logger
from utils.text_utils import transliterate


class DownloadService:
    """Сервис для загрузки книг с Flibusta."""

    def __init__(self, opds_client: FlibustaOPDS):
        """
        Инициализация сервиса загрузки книг.
        
        Алгоритм:
            1. Сохраняет ссылку на клиент OPDS для получения URL загрузки
        
        Args:
            opds_client: Клиент OPDS для работы с Flibusta
        """
        self.opds = opds_client

    async def send_error_message(self, progress_msg, callback, error_text):
        """
        Отправляет сообщение об ошибке пользователю.
        
        Алгоритм:
            1. Пытается отредактировать сообщение о прогрессе с текстом ошибки
            2. Если не удалось, отправляет новое сообщение с ошибкой
        
        Args:
            progress_msg: Сообщение о прогрессе загрузки
            callback: Объект callback-запроса
            error_text: Текст сообщения об ошибке
        """
        try:
            await progress_msg.edit_text(error_text)
        except:
            await callback.message.answer(error_text)

    async def download_book(
            self,
            book_id: str,
            file_type: str,
            book_info_for_filename: Optional[dict],
            callback,
            progress_msg
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Загружает книгу с Flibusta в указанном формате.
        
        Алгоритм:
            1. Получает URL для скачивания книги
            2. Определяет безопасное имя файла из названия книги или использует 'book'
            3. Создает HTTP сессию с увеличенным таймаутом
            4. Выполняет GET запрос для загрузки файла
            5. Проверяет первый чанк на наличие HTML (признак недоступности)
            6. Записывает файл по частям, контролируя размер
            7. Если файл превышает лимит, удаляет его и возвращает ошибку
            8. Если файл является ZIP архивом, обрабатывает его
            9. Возвращает путь к файлу или сообщение об ошибке
        
        Args:
            book_id: ID книги в системе Flibusta
            file_type: Формат файла (fb2, epub, mobi, pdf, txt, rtf, html)
            book_info_for_filename: Словарь с информацией о книге для имени файла (опционально)
            callback: Объект callback-запроса
            progress_msg: Сообщение о прогрессе загрузки
            
        Returns:
            Tuple[Optional[str], Optional[str]]: Кортеж (путь к файлу, сообщение об ошибке)
        """
        download_url = self.opds.get_book_download_url(book_id, file_type)
        logger.info(f"Начало загрузки книги {book_id} в формате {file_type}, URL: {download_url}")

        # Определяем имя файла
        book_title = None
        if book_info_for_filename:
            book_title = book_info_for_filename.get('title')
            if not book_title or book_title == 'Новинки' or book_title.startswith('tag:'):
                book_title = None

        if book_title:
            safe_filename = transliterate(book_title)
            if not safe_filename or safe_filename == 'book':
                safe_filename = 'book'
        else:
            safe_filename = 'book'

        file_name = f"{safe_filename}.{file_type}"
        logger.debug(f"Имя файла для загрузки: {file_name}")

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as session:
                async with session.get(download_url, allow_redirects=True) as response:
                    logger.debug(
                        f"HTTP ответ получен: статус {response.status}, Content-Type: {response.headers.get('Content-Type', 'неизвестно')}")
                    if response.status == 200:
                        content_type = response.headers.get('Content-Type', '').lower()
                        is_zip = 'zip' in content_type or file_type in ['html', 'txt', 'rtf']
                        logger.debug(f"Тип контента: {content_type}, является ZIP: {is_zip}")

                        total_size = 0
                        temp_file_path = file_name
                        final_file_name = file_name

                        first_chunk = None
                        is_html = False

                        with open(temp_file_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                if first_chunk is None:
                                    first_chunk = chunk[:1024] if len(chunk) >= 1024 else chunk
                                    if first_chunk.startswith(b'<!DOCTYPE') or first_chunk.startswith(
                                            b'<html') or first_chunk.startswith(b'<HTML'):
                                        is_html = True
                                        logger.warning(
                                            f"Получен HTML вместо файла для книги {book_id}, формат {file_type}")
                                        f.close()
                                        os.remove(temp_file_path)
                                        error_msg = (
                                            f"❌ Файл недоступен для прямой загрузки.\n\n"
                                            f"💡 {file_type.upper()} файлы на Flibusta требуют авторизации.\n"
                                            f"Используйте кнопку \"Открыть на Flibusta\" для загрузки через браузер."
                                        )
                                        await self.send_error_message(progress_msg, callback, error_msg)
                                        return None, error_msg

                                f.write(chunk)
                                total_size += len(chunk)

                                if total_size > config.MAX_FILE_SIZE:
                                    logger.warning(
                                        f"Файл превышает максимальный размер ({total_size} > {config.MAX_FILE_SIZE}) для книги {book_id}")
                                    f.close()
                                    os.remove(temp_file_path)
                                    error_msg = (
                                        f"❌ Файл слишком большой для загрузки.\n\n"
                                        f"💡 Используйте кнопку \"Открыть на Flibusta\" для загрузки."
                                    )
                                    await self.send_error_message(progress_msg, callback, error_msg)
                                    return None, error_msg

                        logger.debug(f"Файл загружен, размер: {total_size} байт")
                        if is_zip:
                            logger.debug(f"Обработка ZIP архива для книги {book_id}")
                            final_file_name, _ = await process_zip_file(temp_file_path, file_name, file_type)

                        logger.info(
                            f"Книга {book_id} успешно загружена в файл {final_file_name}, размер: {os.path.getsize(final_file_name) if os.path.exists(final_file_name) else 'неизвестно'} байт")
                        return final_file_name, None

                    elif response.status == 404:
                        logger.warning(f"Книга {book_id} не найдена на сервере (404)")
                        error_msg = (
                            f"❌ Книга не найдена на сервере.\n\n"
                            f"💡 Возможно, файл был удален или недоступен."
                        )
                        await self.send_error_message(progress_msg, callback, error_msg)
                        return None, error_msg
                    else:
                        logger.warning(f"Ошибка загрузки книги {book_id}: HTTP статус {response.status}")
                        error_msg = (
                            f"❌ Не удалось загрузить книгу. Статус: {response.status}\n\n"
                            f"💡 Попробуйте использовать кнопку \"Открыть на Flibusta\"."
                        )
                        await self.send_error_message(progress_msg, callback, error_msg)
                        return None, error_msg

        except asyncio.TimeoutError:
            logger.error(f"Таймаут при загрузке книги {book_id} в формате {file_type}")
            error_msg = (
                f"❌ Превышено время ожидания при загрузке.\n\n"
                f"💡 Попробуйте позже или используйте кнопку \"Открыть на Flibusta\"."
            )
            await self.send_error_message(progress_msg, callback, error_msg)
            return None, error_msg
        except Exception as e:
            logger.error(f"Ошибка при загрузке книги {book_id} в формате {file_type}: {e}", exc_info=True)
            error_msg = (
                f"❌ Произошла ошибка при загрузке: {str(e)}\n\n"
                f"💡 Попробуйте использовать кнопку \"Открыть на Flibusta\"."
            )
            await self.send_error_message(progress_msg, callback, error_msg)
            try:
                if os.path.exists(file_name):
                    os.remove(file_name)
            except Exception as cleanup_error:
                logger.warning(f"Ошибка при удалении временного файла {file_name}: {cleanup_error}")
            return None, error_msg

    def get_caption_for_book(self, book_info: Optional[dict], file_type: str) -> str:
        """
        Формирует подпись (caption) для отправляемого файла книги.
        
        Алгоритм:
            1. Проверяет наличие информации о книге
            2. Если информация есть и валидна, формирует подпись с названием и авторами
            3. Добавляет информацию о формате файла
            4. Если информации нет, формирует только информацию о формате
        
        Args:
            book_info: Словарь с информацией о книге (title, authors) (опционально)
            file_type: Формат файла (fb2, epub, mobi, pdf, txt, rtf, html)
            
        Returns:
            str: Текст подписи для файла
        """
        if book_info:
            title = book_info.get('title')
            authors = book_info.get('authors', [])

            if title and title != 'Новинки' and not title.startswith('tag:') and title.strip():
                authors_str = ', '.join(authors) if authors else ''
                caption = f"📖 {title}\n"
                if authors_str:
                    caption += f"👤 {authors_str}\n"
                caption += f"📄 Формат: {file_type.upper()}"
            else:
                caption = f"📄 Формат: {file_type.upper()}"
        else:
            caption = f"📄 Формат: {file_type.upper()}"

        return caption
