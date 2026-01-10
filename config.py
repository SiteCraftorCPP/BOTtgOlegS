import os
from dotenv import load_dotenv

load_dotenv()

# Получаем значения из переменных окружения или используем значения по умолчанию
BOT_TOKEN = os.getenv("BOT_TOKEN", "8137212504:AAHUyVbh634U0gINFOuTCSOpjMnern9HDRk")
ADMIN_ID = int(os.getenv("ADMIN_ID", "6933111964"))
OPERATOR_ID = int(os.getenv("OPERATOR_ID", "7600749840"))
NOTIFICATION_CHAT_ID = int(os.getenv("NOTIFICATION_CHAT_ID", "-1003591909192"))

DATA_DIR = os.getenv("DATA_DIR", "data")
TEXTS_FILE = os.path.join(DATA_DIR, "texts.json")
BUTTONS_FILE = os.path.join(DATA_DIR, "buttons.json")
PHONES_FILE = os.path.join(DATA_DIR, "phones.json")
DIALOGS_FILE = os.path.join(DATA_DIR, "dialogs.json")