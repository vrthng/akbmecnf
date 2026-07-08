"""
Фильтр для проверки белого списка пользователей.
"""
from typing import Union

from aiogram import types
from aiogram.filters import BaseFilter

import config
from utils.logger import logger


class WhitelistFilter(BaseFilter):
    """
    Фильтр для проверки, находится ли пользователь в белом списке.
    
    Если белый список пуст, доступ открыт для всех.
    Если белый список не пуст, доступ только для пользователей из списка.
    """

    async def __call__(self, message: Union[types.Message, types.CallbackQuery]) -> bool:
        """
        Проверяет, находится ли пользователь в белом списке.
        
        Args:
            message: Сообщение или callback-запрос от пользователя
            
        Returns:
            bool: True, если пользователь имеет доступ, False - если нет
        """
        # Если белый список пуст, доступ открыт для всех
        if not config.WHITELIST_USER_IDS:
            return True

        # Получаем ID пользователя
        user_id = None
        if isinstance(message, types.Message):
            user_id = message.from_user.id
        elif isinstance(message, types.CallbackQuery):
            user_id = message.from_user.id

        if user_id is None:
            logger.warning("Не удалось получить ID пользователя")
            return False

        # Проверяем, есть ли пользователь в белом списке
        is_allowed = user_id in config.WHITELIST_USER_IDS

        if not is_allowed:
            logger.warning(f"Пользователь {user_id} не находится в белом списке")

        return is_allowed
