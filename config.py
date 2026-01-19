import os
from dotenv import load_dotenv

load_dotenv()

# Получаем значения из переменных окружения или используем значения по умолчанию
BOT_TOKEN = os.getenv("BOT_TOKEN", "8137212504:AAHUyVbh634U0gINFOuTCSOpjMnern9HDRk")

# Админы (через запятую)
ADMIN_IDS = [int(admin_id.strip()) for admin_id in os.getenv("ADMIN_IDS", "6933111964,506336774").split(",") if admin_id.strip()]
# Операторы (через запятую)
OPERATOR_IDS = [int(operator_id.strip()) for operator_id in os.getenv("OPERATOR_IDS", "1182543866").split(",") if operator_id.strip()]

# Для обратной совместимости
ADMIN_ID = ADMIN_IDS[0] if ADMIN_IDS else 6933111964
OPERATOR_ID = OPERATOR_IDS[0] if OPERATOR_IDS else 1182543866

NOTIFICATION_CHAT_ID = int(os.getenv("NOTIFICATION_CHAT_ID", "-1003597334389"))

DATA_DIR = os.getenv("DATA_DIR", "data")
TEXTS_FILE = os.path.join(DATA_DIR, "texts.json")
BUTTONS_FILE = os.path.join(DATA_DIR, "buttons.json")
PHONES_FILE = os.path.join(DATA_DIR, "phones.json")
DIALOGS_FILE = os.path.join(DATA_DIR, "dialogs.json")