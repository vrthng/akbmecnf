"""
Сервис кэширования результатов поиска и информации о книгах.
"""
from utils.logger import logger


class CacheService:
    """Управление кэшем результатов поиска и информации о книгах."""

    def __init__(self, max_search_cache_size: int = 10):
        """
        Инициализация сервиса кэширования.
        
        Алгоритм:
        1. Создает словарь для кэширования результатов поиска
        2. Создает словарь для кэширования информации о книгах
        3. Устанавливает максимальный размер кэша поиска
        
        Args:
            max_search_cache_size: Максимальное количество записей в кэше поиска (по умолчанию 10)
        """
        self.search_results_cache = {}
        self.books_info_cache = {}
        self.max_search_cache_size = max_search_cache_size

    def get_search_results(self, user_id: int, query: str):
        """
        Получает закэшированные результаты поиска для пользователя.
        
        Алгоритм:
            1. Формирует ключ кэша из user_id и query
            2. Ищет результаты в кэше по ключу
            3. Возвращает результаты или None, если не найдено
        
        Args:
            user_id: ID пользователя
            query: Поисковый запрос
            
        Returns:
            list: Список результатов поиска или None, если не найдено в кэше
        """
        cache_key = f"{user_id}_{query}"
        return self.search_results_cache.get(cache_key)

    def set_search_results(self, user_id: int, query: str, results: list):
        """
        Сохраняет результаты поиска в кэш.
        
        Алгоритм:
            1. Формирует ключ кэша из user_id и query
            2. Проверяет размер кэша
            3. Если превышен лимит, удаляет самую старую запись
            4. Сохраняет новые результаты в кэш
        
        Args:
            user_id: ID пользователя
            query: Поисковый запрос
            results: Список результатов поиска для сохранения
        """
        cache_key = f"{user_id}_{query}"

        # Очистка старых записей при превышении лимита
        if len(self.search_results_cache) > self.max_search_cache_size:
            oldest_key = next(iter(self.search_results_cache))
            logger.debug(f"Очистка кэша: удаление старой записи {oldest_key}")
            del self.search_results_cache[oldest_key]

        self.search_results_cache[cache_key] = results
        logger.debug(
            f"Результаты поиска сохранены в кэш: пользователь={user_id}, запрос='{query}', результатов={len(results)}")

    def get_book_info(self, book_id: str):
        """
        Получает закэшированную информацию о книге.
        
        Алгоритм:
            1. Ищет информацию о книге в кэше по book_id
            2. Возвращает словарь с информацией или None
        
        Args:
            book_id: ID книги в системе Flibusta
            
        Returns:
            dict: Словарь с информацией о книге (title, authors) или None
        """
        return self.books_info_cache.get(book_id)

    def set_book_info(self, book_id: str, title: str, authors: list):
        """
        Сохраняет информацию о книге в кэш.
        
        Алгоритм:
            1. Создает словарь с названием и авторами книги
            2. Сохраняет словарь в кэш по ключу book_id
        
        Args:
            book_id: ID книги в системе Flibusta
            title: Название книги
            authors: Список авторов книги
        """
        self.books_info_cache[book_id] = {
            'title': title,
            'authors': authors
        }

    def find_book_in_cache(self, book_id: str, opds=None):
        """
        Ищет книгу в кэше результатов поиска по ID.
        
        Алгоритм:
            1. Итерируется по всем закэшированным результатам поиска
            2. Для каждого результата извлекает ID книги
            3. Сравнивает извлеченный ID с искомым book_id
            4. Если найдено совпадение, возвращает копию данных книги
            5. Если не найдено, возвращает None
        
        Args:
            book_id: ID книги для поиска
            opds: Клиент OPDS для извлечения ID из entry (опционально)
            
        Returns:
            dict: Словарь с данными книги или None, если не найдено
        """
        for cache_key, results in self.search_results_cache.items():
            for book in results:
                if opds:
                    cached_book_id = book.get('book_id') or opds._extract_book_id(book.get('id', ''))
                else:
                    cached_book_id = book.get('book_id')
                if cached_book_id == book_id:
                    return book.copy()
        return None

    def get_book_info_for_download(self, book_id: str):
        """
        Получает информацию о книге для загрузки из кэша.
        
        Алгоритм:
            1. Ищет книгу в кэше результатов поиска
            2. Если найдено, возвращает данные книги
            3. Если не найдено, ищет в кэше информации о книгах
            4. Если найдено, формирует словарь с данными для загрузки
            5. Если не найдено, возвращает None
        
        Args:
            book_id: ID книги для поиска
            
        Returns:
            dict: Словарь с данными книги (book_id, title, authors) или None
        """
        # Сначала ищем в кэше результатов поиска
        book = self.find_book_in_cache(book_id)
        if book:
            return book

        # Затем в кэше информации о книгах
        if book_id in self.books_info_cache:
            cached_info = self.books_info_cache[book_id]
            return {
                'book_id': book_id,
                'title': cached_info.get('title', ''),
                'authors': cached_info.get('authors', [])
            }

        return None
