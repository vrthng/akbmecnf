"""
Модуль для настройки логирования с записью в файлы.
"""
import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler


def setup_logger(name: str = "flibusta_bot", log_dir: str = "logs") -> logging.Logger:
    """
    Настраивает и возвращает логгер с записью в файл и консоль.
    
    Алгоритм:
        1. Создает директорию для логов, если её нет
        2. Создает уникальное имя файла с временной меткой
        3. Настраивает формат логов
        4. Добавляет обработчик для записи в файл (с ротацией)
        5. Добавляет обработчик для вывода в консоль
        6. Устанавливает уровень логирования
        7. Возвращает настроенный логгер
    
    Args:
        name: Имя логгера (по умолчанию "flibusta_bot")
        log_dir: Директория для сохранения логов (по умолчанию "logs")
        
    Returns:
        logging.Logger: Настроенный логгер
    """
    # Создаем директорию для логов, если её нет
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Создаем уникальное имя файла с временной меткой
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(log_dir, f"{name}_{timestamp}.log")

    # Создаем логгер
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Удаляем существующие обработчики, чтобы избежать дублирования
    logger.handlers.clear()

    # Формат логов
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Обработчик для записи в файл (с ротацией, максимум 10MB на файл, 5 файлов)
    file_handler = RotatingFileHandler(
        log_filename,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Обработчик для вывода в консоль
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)  # В консоль только INFO и выше
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


# Создаем глобальный логгер для использования во всем проекте
logger = setup_logger()
