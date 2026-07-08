import re
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from urllib.parse import urljoin

import aiohttp

import config
from utils.logger import logger


class FlibustaOPDS:

    def __init__(self):
        """
        Инициализация клиента OPDS для работы с Flibusta.
        
        Алгоритм:
            1. Устанавливает базовый URL для OPDS API
            2. Инициализирует переменную сессии как None
        """
        self.base_url = config.FLIBUSTA_OPDS_BASE_URL
        self.session = None

    async def _get_session(self):
        """
        Получить или создать HTTP сессию для запросов.
        
        Алгоритм:
            1. Проверяет наличие активной сессии
            2. Если сессии нет или она закрыта, создает новую с таймаутом
            3. Возвращает активную сессию
        
        Returns:
            aiohttp.ClientSession: HTTP сессия для выполнения запросов
        """
        if self.session is None or self.session.closed:
            logger.debug("Создание новой HTTP сессии")
            timeout = aiohttp.ClientTimeout(total=config.REQUEST_TIMEOUT)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    async def close(self):
        """
        Закрыть HTTP сессию.
        
        Алгоритм:
            1. Проверяет наличие активной сессии
            2. Если сессия открыта, закрывает ее
        """
        if self.session and not self.session.closed:
            logger.debug("Закрытие HTTP сессии")
            await self.session.close()

    def _parse_opds_entry(self, entry_elem) -> Optional[Dict]:
        """
        Парсит XML элемент entry из OPDS каталога в словарь с данными книги.
        
        Алгоритм:
            1. Извлекает базовую информацию (id, title, authors, updated, content)
            2. Обрабатывает все ссылки из элемента entry
            3. Определяет URL книги, обложки и ссылки для скачивания
            4. Извлекает ID книги из различных источников
            5. Формирует словарь с данными книги
        
        Args:
            entry_elem: XML элемент entry из OPDS каталога
            
        Returns:
            Optional[Dict]: Словарь с данными книги или None при ошибке парсинга
        """
        try:
            namespace = {'atom': 'http://www.w3.org/2005/Atom'}

            entry_id = entry_elem.find('atom:id', namespace) or entry_elem.find('{http://www.w3.org/2005/Atom}id')
            title_elem = entry_elem.find('atom:title', namespace) or entry_elem.find(
                '{http://www.w3.org/2005/Atom}title')
            author_elems = entry_elem.findall('atom:author/atom:name', namespace) or entry_elem.findall(
                '{http://www.w3.org/2005/Atom}author/{http://www.w3.org/2005/Atom}name')
            updated_elem = entry_elem.find('atom:updated', namespace) or entry_elem.find(
                '{http://www.w3.org/2005/Atom}updated')
            content_elem = entry_elem.find('atom:content', namespace) or entry_elem.find(
                '{http://www.w3.org/2005/Atom}content')

            links = entry_elem.findall('atom:link', namespace) or entry_elem.findall(
                '{http://www.w3.org/2005/Atom}link')

            book_data = {
                'id': entry_id.text if entry_id is not None else None,
                'title': title_elem.text if title_elem is not None else 'Без названия',
                'authors': [author.text for author in author_elems] if author_elems else [],
                'updated': updated_elem.text if updated_elem is not None else None,
                'content': content_elem.text if content_elem is not None else '',
                'download_links': {},
                'book_url': None,
                'cover_url': None
            }

            for link in links:
                rel = link.get('rel', '')
                href = link.get('href', '')
                type_attr = link.get('type', '')

                if rel == 'alternate' or 'html' in type_attr:
                    if href.startswith('http'):
                        book_data['book_url'] = href
                    else:
                        book_data['book_url'] = urljoin(config.FLIBUSTA_BASE_URL, href)

                if (rel == 'http://opds-spec.org/image' or
                        rel == 'x-stanza-cover-image'):
                    if not book_data.get('cover_url'):
                        if href.startswith('http'):
                            book_data['cover_url'] = href
                        else:
                            book_data['cover_url'] = urljoin(config.FLIBUSTA_BASE_URL, href)
                elif rel == 'http://opds-spec.org/thumbnail' or rel == 'x-stanza-cover-image-thumbnail':
                    if not book_data.get('cover_url'):
                        if href.startswith('http'):
                            book_data['cover_url'] = href
                        else:
                            book_data['cover_url'] = urljoin(config.FLIBUSTA_BASE_URL, href)

                if ('download' in rel or
                        'acquisition' in rel or
                        'opds-spec.org/acquisition' in rel or
                        rel.startswith('http://opds-spec.org/acquisition')):
                    fmt = self._detect_format(href, type_attr)
                    if fmt:
                        if href.startswith('http'):
                            book_data['download_links'][fmt] = href
                        else:
                            book_data['download_links'][fmt] = urljoin(config.FLIBUSTA_BASE_URL, href)

                    if not book_data.get('book_id'):
                        match = re.search(r'/b/(\d+)', href)
                        if match:
                            book_data['book_id'] = match.group(1)

            if not book_data['book_url']:
                book_id = self._extract_book_id(book_data['id'])
                if book_id:
                    book_data['book_url'] = f"{config.FLIBUSTA_BOOK_URL}/{book_id}"

            return book_data
        except Exception as e:
            logger.error(f"Ошибка парсинга entry: {e}", exc_info=True)
            return None

    def _extract_book_id(self, entry_id: str) -> Optional[str]:
        """
        Извлекает ID книги из строки идентификатора entry.
        
        Алгоритм:
            1. Проверяет наличие entry_id
            2. Разбивает строку по двоеточию и извлекает последнюю часть
            3. Проверяет, является ли извлеченная часть числом
            4. Если не удалось, ищет паттерн /b/число в строке
            5. Возвращает найденный ID или None
        
        Args:
            entry_id: Строка идентификатора entry из OPDS
            
        Returns:
            Optional[str]: ID книги или None, если не найден
        """
        if not entry_id:
            return None
        parts = entry_id.split(':')
        if len(parts) >= 3:
            book_id = parts[-1]
            if book_id.isdigit():
                return book_id
        if '/b/' in entry_id:
            match = re.search(r'/b/(\d+)', entry_id)
            if match:
                return match.group(1)
        return None

    def _detect_format(self, href: str, content_type: str) -> Optional[str]:
        """
        Определяет формат файла по URL и типу контента.
        
        Алгоритм:
            1. Приводит href и content_type к нижнему регистру
            2. Проверяет наличие паттернов форматов в href и content_type
            3. Возвращает найденный формат (fb2, epub, mobi, pdf, txt, rtf, html)
            4. Возвращает None, если формат не определен
        
        Args:
            href: URL ссылки на файл
            content_type: MIME-тип контента
            
        Returns:
            Optional[str]: Формат файла или None, если не определен
        """
        href_lower = href.lower()
        type_lower = content_type.lower()

        format_map = {
            'fb2': ['/fb2', 'fb2', 'fictionbook'],
            'epub': ['/epub', 'epub'],
            'mobi': ['/mobi', 'mobi', 'mobipocket'],
            'pdf': ['/pdf', 'pdf'],
            'txt': ['/txt', 'txt', 'text/plain'],
            'rtf': ['/rtf', 'rtf'],
            'html': ['/html', 'html']
        }

        for fmt, patterns in format_map.items():
            if any(pattern in href_lower or pattern in type_lower for pattern in patterns):
                return fmt

        return None

    async def search_books(self, query: str, limit: int = config.MAX_SEARCH_RESULTS) -> List[Dict]:
        """
        Выполняет поиск книг через OPDS API Flibusta.
        
        Алгоритм:
            1. Получает HTTP сессию
            2. Формирует URL и параметры для поиска
            3. Выполняет GET запрос к OPDS API
            4. Парсит XML ответ
            5. Фильтрует результаты, исключая каталоги
            6. Парсит каждую entry в данные книги
            7. Ограничивает количество результатов по limit
            8. Возвращает список найденных книг
        
        Args:
            query: Поисковый запрос (название книги или автор)
            limit: Максимальное количество результатов (по умолчанию из config)
            
        Returns:
            List[Dict]: Список словарей с данными найденных книг
        """
        session = await self._get_session()

        search_url = f"{self.base_url}/search"
        params = {
            'searchTerm': query,
            'searchType': 'books'
        }

        try:
            logger.debug(f"Выполнение поиска через OPDS API: запрос='{query}', limit={limit}")
            async with session.get(search_url, params=params) as response:
                if response.status != 200:
                    logger.warning(f"Ошибка OPDS API: статус {response.status} для запроса '{query}'")
                    return []

                content = await response.text()
                logger.debug(f"Получен ответ от OPDS API, размер: {len(content)} байт")

                try:
                    root = ET.fromstring(content)
                except ET.ParseError as e:
                    logger.error(f"Ошибка парсинга XML для запроса '{query}': {e}", exc_info=True)
                    return []

                namespace = {'atom': 'http://www.w3.org/2005/Atom'}
                entries = root.findall('.//atom:entry', namespace)

                if not entries:
                    entries = root.findall('.//{http://www.w3.org/2005/Atom}entry')

                results = []
                for entry in entries:
                    links = entry.findall('atom:link', namespace) or entry.findall('{http://www.w3.org/2005/Atom}link')
                    has_download_link = False
                    is_catalog = False

                    for link in links:
                        rel = link.get('rel', '')
                        link_type = link.get('type', '')

                        if ('acquisition' in rel and 'opds-spec.org/acquisition' in rel) or rel.startswith(
                                'http://opds-spec.org/acquisition'):
                            has_download_link = True

                        if 'catalog' in link_type.lower() and 'atom+xml' in link_type.lower() and 'acquisition' not in rel:
                            is_catalog = True

                    if is_catalog or not has_download_link:
                        continue

                    book_data = self._parse_opds_entry(entry)
                    if book_data:
                        book_id = self._extract_book_id(book_data.get('id', ''))
                        if book_id:
                            book_data['book_id'] = book_id
                        results.append(book_data)

                        if len(results) >= limit:
                            break

                logger.info(f"Поиск завершен: найдено {len(results)} книг по запросу '{query}'")
                return results
        except aiohttp.ClientError as e:
            logger.error(f"Ошибка HTTP запроса при поиске '{query}': {e}", exc_info=True)
            return []
        except Exception as e:
            logger.error(f"Ошибка поиска для запроса '{query}': {e}", exc_info=True)
            return []

    async def get_book_info(self, book_id: str) -> Optional[Dict]:
        """
        Получает подробную информацию о книге по её ID.
        
        Алгоритм:
            1. Получает HTTP сессию
            2. Пытается найти книгу через поиск по ID
            3. Если не найдено, запрашивает напрямую через OPDS API
            4. Если не найдено, парсит HTML страницу книги
            5. Извлекает название, авторов, обложку и ссылки для скачивания
            6. Возвращает словарь с данными книги или пустой словарь
        
        Args:
            book_id: ID книги в системе Flibusta
            
        Returns:
            Optional[Dict]: Словарь с данными книги или None при ошибке
        """
        session = await self._get_session()
        logger.debug(f"Получение информации о книге с ID: {book_id}")

        try:
            search_url = f"{self.base_url}/search"
            params = {
                'searchTerm': book_id,
                'searchType': 'books'
            }

            try:
                logger.debug(f"Попытка найти книгу через поиск по ID: {book_id}")
                async with session.get(search_url, params=params) as response:
                    if response.status == 200:
                        content = await response.text()
                        root = ET.fromstring(content)

                        namespace = {'atom': 'http://www.w3.org/2005/Atom'}
                        entries = root.findall('.//atom:entry', namespace) or root.findall(
                            './/{http://www.w3.org/2005/Atom}entry')

                        for entry in entries:
                            entry_id = entry.find('atom:id', namespace) or entry.find('{http://www.w3.org/2005/Atom}id')
                            if entry_id is not None:
                                extracted_id = self._extract_book_id(entry_id.text)
                                if extracted_id == book_id:
                                    links = entry.findall('atom:link', namespace) or entry.findall(
                                        '{http://www.w3.org/2005/Atom}link')
                                    has_download_link = False

                                    for link in links:
                                        rel = link.get('rel', '')
                                        if (
                                                'acquisition' in rel and 'opds-spec.org/acquisition' in rel) or rel.startswith(
                                                'http://opds-spec.org/acquisition'):
                                            has_download_link = True
                                            break

                                    if has_download_link:
                                        book_data = self._parse_opds_entry(entry)
                                        if book_data:
                                            title = book_data.get('title', '')
                                            if title and title not in ['Новинки', 'По авторам', 'По сериям',
                                                                       'По жанрам', 'Моя полка']:
                                                book_data['book_id'] = book_id
                                                book_data['book_url'] = f"{config.FLIBUSTA_BASE_URL}/b/{book_id}"
                                                logger.debug(f"Книга {book_id} найдена через поиск")
                                                return book_data
            except Exception as e:
                logger.warning(f"Ошибка получения информации о книге {book_id} через поиск: {e}")

            opds_book_url = f"{self.base_url}/book/{book_id}"
            logger.debug(f"Попытка получить информацию о книге через OPDS API: {opds_book_url}")

            try:
                async with session.get(opds_book_url) as response:
                    if response.status == 200:
                        content = await response.text()
                        root = ET.fromstring(content)

                        namespace = {'atom': 'http://www.w3.org/2005/Atom'}
                        entry = root.find('atom:entry', namespace) or root.find('{http://www.w3.org/2005/Atom}entry')

                        if entry:
                            links = entry.findall('atom:link', namespace) or entry.findall(
                                '{http://www.w3.org/2005/Atom}link')
                            has_download_link = False
                            is_catalog = False

                            for link in links:
                                rel = link.get('rel', '')
                                link_type = link.get('type', '')

                                if ('acquisition' in rel and 'opds-spec.org/acquisition' in rel) or rel.startswith(
                                        'http://opds-spec.org/acquisition'):
                                    has_download_link = True

                                if 'catalog' in link_type.lower() and 'atom+xml' in link_type.lower() and 'acquisition' not in rel:
                                    is_catalog = True

                            if is_catalog or not has_download_link:
                                logger.warning(f"Получен каталог вместо книги для ID {book_id}")
                            else:
                                book_data = self._parse_opds_entry(entry)
                                if book_data:
                                    title = book_data.get('title', '')
                                    if title and title not in ['Новинки', 'По авторам', 'По сериям', 'По жанрам',
                                                               'Моя полка']:
                                        book_data['book_id'] = book_id
                                        book_data['book_url'] = f"{config.FLIBUSTA_BASE_URL}/b/{book_id}"
                                        logger.debug(f"Книга {book_id} найдена через OPDS API: '{title}'")
                                        return book_data
            except Exception as e:
                logger.warning(f"Ошибка получения информации о книге {book_id} через OPDS API: {e}")

            book_url = f"{config.FLIBUSTA_BASE_URL}/b/{book_id}"
            logger.debug(f"Попытка получить информацию о книге через HTML парсинг: {book_url}")
            try:
                async with session.get(book_url) as response:
                    if response.status == 200:
                        html_content = await response.text()

                        cover_url = None
                        cover_patterns = [
                            r'<img[^>]*src="([^"]*cover[^"]*)"[^>]*>',
                            r'<img[^>]*src="([^"]*image[^"]*)"[^>]*>',
                            r'<img[^>]*class="[^"]*cover[^"]*"[^>]*src="([^"]*)"[^>]*>',
                            r'<img[^>]*class="[^"]*book[^"]*"[^>]*src="([^"]*)"[^>]*>',
                        ]
                        for pattern in cover_patterns:
                            cover_match = re.search(pattern, html_content, re.IGNORECASE)
                            if cover_match:
                                cover_url = cover_match.group(1)
                                if not cover_url.startswith('http'):
                                    cover_url = urljoin(config.FLIBUSTA_BASE_URL, cover_url)
                                break

                        title_match = re.search(r'<h1[^>]*class="title"[^>]*>(.*?)</h1>', html_content, re.DOTALL)
                        if not title_match:
                            title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html_content, re.DOTALL)

                        title = None
                        if title_match:
                            title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
                            title = re.sub(r'\s+', ' ', title)
                            title = re.sub(r'\s*\([^)]*\)\s*$', '', title)

                        authors = []
                        author_block_patterns = [
                            r'<div[^>]*class="[^"]*author[^"]*"[^>]*>(.*?)</div>',
                            r'Автор[^:]*:\s*<a[^>]*href="/a/\d+"[^>]*>(.*?)</a>',
                            r'<a[^>]*href="/a/\d+"[^>]*class="[^"]*author[^"]*"[^>]*>(.*?)</a>',
                        ]

                        found_authors = False
                        for pattern in author_block_patterns:
                            matches = re.findall(pattern, html_content, re.IGNORECASE | re.DOTALL)
                            if matches:
                                for match in matches:
                                    if isinstance(match, tuple):
                                        match = match[-1]
                                    author_text = re.sub(r'<[^>]+>', '', match).strip()
                                    if author_text and author_text not in authors:
                                        authors.append(author_text)
                                if authors:
                                    found_authors = True
                                    break

                        if not found_authors:
                            content_match = re.search(r'<div[^>]*id="content"[^>]*>(.*?)</div>', html_content,
                                                      re.DOTALL | re.IGNORECASE)
                            if not content_match:
                                content_match = re.search(r'<div[^>]*class="[^"]*content[^"]*"[^>]*>(.*?)</div>',
                                                          html_content, re.DOTALL | re.IGNORECASE)

                            search_content = content_match.group(1) if content_match else html_content

                            author_matches = re.findall(r'<a[^>]*href="/a/(\d+)"[^>]*>(.*?)</a>', search_content)
                            if author_matches:
                                nav_words = ['Все', 'А', 'Б', 'В', 'Г', 'Д', 'Е', 'Ж', 'З', 'И', 'Й', 'К', 'Л', 'М',
                                             'Н', 'О', 'П', 'Р', 'С', 'Т', 'У', 'Ф', 'Х', 'Ц', 'Ч', 'Ш', 'Щ', 'Э', 'Ю',
                                             'Я']
                                for author_id, author_name in author_matches:
                                    author_text = re.sub(r'<[^>]+>', '', author_name).strip()
                                    if author_text and author_text not in nav_words:
                                        if author_text not in authors:
                                            authors.append(author_text)
                                        if len(authors) >= 3:
                                            break

                        download_links = {}

                        content_match = re.search(r'<div[^>]*id="content"[^>]*>(.*?)</div>', html_content,
                                                  re.DOTALL | re.IGNORECASE)
                        if not content_match:
                            content_match = re.search(r'<div[^>]*class="[^"]*content[^"]*"[^>]*>(.*?)</div>',
                                                      html_content, re.DOTALL | re.IGNORECASE)

                        search_content = content_match.group(1) if content_match else html_content

                        format_patterns = [
                            r'href="([^"]*/b/' + re.escape(
                                book_id) + r'/(fb2|epub|mobi|pdf|txt|rtf|html|djvu)(?:\?[^"]*)?)"',
                            r'href="([^"]*/b/\d+/(fb2|epub|mobi|pdf|txt|rtf|html|djvu)(?:\?[^"]*)?)"',
                            r'href=["\']([^"\']*/b/' + re.escape(
                                book_id) + r'/(fb2|epub|mobi|pdf|txt|rtf|html|djvu)(?:\?[^"\']*)?)["\']',
                        ]

                        all_format_links = []
                        for pattern in format_patterns:
                            matches = re.findall(pattern, html_content, re.IGNORECASE)
                            if matches:
                                all_format_links = matches
                                break

                        for link_data in all_format_links:
                            if isinstance(link_data, tuple):
                                link, fmt = link_data
                            else:
                                link = link_data
                                fmt_match = re.search(r'/(fb2|epub|mobi|pdf|txt|rtf|html|djvu)(?:\?|$)', link,
                                                      re.IGNORECASE)
                                if not fmt_match:
                                    continue
                                fmt = fmt_match.group(1)

                            fmt_lower = fmt.lower()
                            if fmt_lower not in download_links:
                                if book_id in link:
                                    clean_link = link.split('?')[0].split('"')[0].split("'")[0]
                                    if not clean_link.startswith('http'):
                                        clean_link = urljoin(config.FLIBUSTA_BASE_URL, clean_link)
                                    download_links[fmt_lower] = clean_link

                        if not download_links:
                            download_section = re.search(
                                r'(<a[^>]*href="[^"]*/b/' + re.escape(book_id) + r'/[^"]*"[^>]*>.*?</a>)', html_content,
                                re.IGNORECASE | re.DOTALL)
                            if download_section:
                                section_content = download_section.group(1)
                                format_links = re.findall(r'href="([^"]*/b/' + re.escape(
                                    book_id) + r'/(fb2|epub|mobi|pdf|txt|rtf|html|djvu))', section_content,
                                                          re.IGNORECASE)
                                for link, fmt in format_links:
                                    fmt_lower = fmt.lower()
                                    if fmt_lower not in download_links:
                                        clean_link = link.split('?')[0]
                                        if not clean_link.startswith('http'):
                                            clean_link = urljoin(config.FLIBUSTA_BASE_URL, clean_link)
                                        download_links[fmt_lower] = clean_link

                        if title and title not in ['Новинки', 'По авторам', 'По сериям', 'По жанрам', 'Моя полка']:
                            book_data = {
                                'id': f"tag:book:{book_id}",
                                'book_id': book_id,
                                'book_url': book_url,
                                'download_links': download_links,
                                'title': title,
                                'authors': authors,
                                'cover_url': cover_url
                            }

                            logger.debug(f"Книга {book_id} найдена через HTML парсинг: '{title}'")
                            return book_data
            except Exception as e:
                logger.warning(f"Ошибка парсинга HTML страницы для книги {book_id}: {e}")

            book_data = {
                'id': f"tag:book:{book_id}",
                'book_id': book_id,
                'book_url': book_url,
                'download_links': {},
                'title': None,
                'authors': []
            }

            logger.warning(f"Не удалось получить полную информацию о книге {book_id}, возвращаются базовые данные")
            return book_data
        except Exception as e:
            logger.error(f"Критическая ошибка получения информации о книге {book_id}: {e}", exc_info=True)
            return None

    def get_book_download_url(self, book_id: str, file_type: str = 'fb2') -> str:
        """
        Формирует URL для скачивания книги в указанном формате.
        
        Алгоритм:
            1. Приводит file_type к нижнему регистру
            2. Формирует URL по шаблону: BASE_URL/b/BOOK_ID/FILE_TYPE
        
        Args:
            book_id: ID книги в системе Flibusta
            file_type: Формат файла (fb2, epub, mobi, pdf, txt, rtf, html)
            
        Returns:
            str: URL для скачивания книги
        """
        return f"{config.FLIBUSTA_BOOK_URL}/{book_id}/{file_type.lower()}"

    def get_available_formats(self, book_data: Dict) -> List[str]:
        """
        Извлекает список доступных форматов для скачивания книги.
        
        Алгоритм:
            1. Проверяет наличие ключа 'download_links' в данных книги
            2. Если ссылки есть, возвращает список ключей (форматов)
            3. Если ссылок нет, возвращает пустой список
        
        Args:
            book_data: Словарь с данными книги
            
        Returns:
            List[str]: Список доступных форматов (fb2, epub, mobi и т.д.)
        """
        if 'download_links' in book_data and book_data['download_links']:
            return list(book_data['download_links'].keys())
        return []
