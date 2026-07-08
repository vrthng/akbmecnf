import asyncio
import os
import shutil
import tempfile
import time
import zipfile

from utils.logger import logger


async def process_zip_file(temp_file_path: str, file_name: str, file_type: str) -> tuple:
    """
    Обрабатывает ZIP архив, извлекая файл нужного формата.
    
    Алгоритм:
        1. Проверяет, является ли файл ZIP архивом (по заголовку PK)
        2. Открывает ZIP архив и получает список файлов
        3. Ищет файл с нужным расширением (file_type)
        4. Если не найден, берет первый файл из архива
        5. Извлекает найденный файл во временную директорию
        6. Копирует извлеченный файл с временным именем
        7. Удаляет оригинальный ZIP файл
        8. Пытается удалить старый файл с таким же именем (до 3 попыток)
        9. Переименовывает временный файл в финальное имя
        10. Если переименование не удалось, создает уникальное имя или копирует файл
        11. Возвращает путь к финальному файлу и флаг успешной распаковки
    
    Args:
        temp_file_path: Путь к временному ZIP файлу
        file_name: Желаемое имя итогового файла
        file_type: Формат файла для поиска в архиве (fb2, epub, mobi и т.д.)
        
    Returns:
        tuple: Кортеж (путь к финальному файлу, был_ли_файл_извлечен: bool)
    """
    logger.debug(f"Обработка ZIP файла: {temp_file_path}, ожидаемый формат: {file_type}")
    try:
        with open(temp_file_path, 'rb') as f:
            header = f.read(2)
            if header == b'PK':
                logger.debug(f"Файл является ZIP архивом, извлечение файлов...")
                with zipfile.ZipFile(temp_file_path, 'r') as zip_ref:
                    file_list = zip_ref.namelist()
                    logger.debug(f"Найдено файлов в архиве: {len(file_list)}")

                    extracted_file = None
                    for zip_file in file_list:
                        if zip_file.endswith(f'.{file_type}') or zip_file.endswith(f'.{file_type.upper()}'):
                            extracted_file = zip_file
                            break

                    if not extracted_file and file_list:
                        extracted_file = file_list[0]
                        logger.debug(
                            f"Файл с расширением .{file_type} не найден, используется первый файл: {extracted_file}")

                    if extracted_file:
                        logger.debug(f"Извлечение файла: {extracted_file}")
                        with tempfile.TemporaryDirectory() as temp_dir:
                            zip_ref.extract(extracted_file, temp_dir)
                            extracted_path = os.path.join(temp_dir, extracted_file)

                            temp_final_name = f"{file_name}.tmp"
                            shutil.copy2(extracted_path, temp_final_name)

                try:
                    os.remove(temp_file_path)
                except:
                    pass

                old_file_removed = False
                if os.path.exists(file_name):
                    for attempt in range(3):
                        try:
                            os.remove(file_name)
                            old_file_removed = True
                            break
                        except (OSError, PermissionError):
                            if attempt < 2:
                                await asyncio.sleep(0.1)

                if old_file_removed:
                    final_file_name = file_name
                else:
                    unique_suffix = int(time.time() * 1000) % 100000
                    base_name, ext = os.path.splitext(file_name)
                    final_file_name = f"{base_name}_{unique_suffix}{ext}"

                try:
                    if os.path.exists(temp_final_name):
                        if os.path.exists(final_file_name) and final_file_name != temp_final_name:
                            unique_suffix = int(time.time() * 1000) % 100000
                            base_name, ext = os.path.splitext(file_name)
                            final_file_name = f"{base_name}_{unique_suffix}{ext}"

                        os.rename(temp_final_name, final_file_name)
                        logger.debug(f"Файл успешно переименован: {final_file_name}")
                    else:
                        final_file_name = file_name
                except Exception as e:
                    logger.warning(f"Не удалось переименовать файл {temp_final_name} в {final_file_name}: {e}")
                    try:
                        shutil.copy2(temp_final_name, file_name)
                        final_file_name = file_name
                        logger.debug(f"Файл скопирован вместо переименования: {file_name}")
                    except Exception as copy_error:
                        logger.error(f"Не удалось скопировать файл: {copy_error}")
                        final_file_name = temp_final_name

                logger.info(f"ZIP файл успешно обработан: {final_file_name}")
                return final_file_name, True
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as e:
        logger.warning(f"Файл не является валидным ZIP архивом или слишком большой: {e}")
    except Exception as e:
        logger.error(f"Ошибка распаковки ZIP файла {temp_file_path}: {e}", exc_info=True)

    return file_name, False
