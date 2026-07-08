import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Белый список пользователей (через запятую, например: "123456789,987654321")
# Если пусто, то доступ открыт для всех
WHITELIST_USER_IDS = os.getenv("WHITELIST_USER_IDS", "")
if WHITELIST_USER_IDS:
    # Преобразуем строку в список целых чисел
    WHITELIST_USER_IDS = [int(uid.strip()) for uid in WHITELIST_USER_IDS.split(",") if uid.strip().isdigit()]
else:
    WHITELIST_USER_IDS = []

FLIBUSTA_OPDS_BASE_URL = "https://flibusta.is/opds"
FLIBUSTA_BASE_URL = "https://flibusta.is"
FLIBUSTA_BOOK_URL = f"{FLIBUSTA_BASE_URL}/b"

MAX_SEARCH_RESULTS = 20
RESULTS_PER_PAGE = 5
MAX_FILE_SIZE = 50 * 1024 * 1024

REQUEST_TIMEOUT = 30
