import asyncio
import json
import os
import aiofiles
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, ADMIN_ID, ADMIN_IDS, OPERATOR_ID, OPERATOR_IDS, DATA_DIR, TEXTS_FILE, BUTTONS_FILE, PHONES_FILE, NOTIFICATION_CHAT_ID, DIALOGS_FILE

# Создаём директорию для данных, если её нет
os.makedirs(DATA_DIR, exist_ok=True)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# Состояния для админки
class AdminStates(StatesGroup):
    editing_text = State()
    editing_button = State()
    waiting_text_content = State()
    waiting_button_content = State()
    waiting_button_text = State()  # Для редактирования текста кнопки


# Состояния для пользователей
class UserStates(StatesGroup):
    waiting_phone = State()  # Ожидание номера телефона
    button_path = State()  # Путь нажатых кнопок (будет храниться в данных состояния)
    in_dialog = State()  # Пользователь в активном диалоге


# Состояния для операторов/админов
class OperatorStates(StatesGroup):
    replying_to_dialog = State()  # Оператор отвечает в диалоге


# Загрузка данных
async def load_texts():
    try:
        async with aiofiles.open(TEXTS_FILE, 'r', encoding='utf-8') as f:
            content = await f.read()
            return json.loads(content)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


async def load_buttons():
    try:
        async with aiofiles.open(BUTTONS_FILE, 'r', encoding='utf-8') as f:
            content = await f.read()
            return json.loads(content)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# Сохранение данных
async def save_texts(data):
    async with aiofiles.open(TEXTS_FILE, 'w', encoding='utf-8') as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=2))


async def save_buttons(data):
    async with aiofiles.open(BUTTONS_FILE, 'w', encoding='utf-8') as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=2))


# Загрузка и сохранение номеров телефонов пользователей
async def load_phones():
    try:
        async with aiofiles.open(PHONES_FILE, 'r', encoding='utf-8') as f:
            content = await f.read()
            return json.loads(content)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


async def save_phones(data):
    async with aiofiles.open(PHONES_FILE, 'w', encoding='utf-8') as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=2))


# Загрузка и сохранение диалогов
async def load_dialogs():
    try:
        async with aiofiles.open(DIALOGS_FILE, 'r', encoding='utf-8') as f:
            content = await f.read()
            return json.loads(content)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "dialogs": {},
            "user_active_dialogs": {},
            "operator_active_dialogs": {}
        }


async def save_dialogs(data):
    async with aiofiles.open(DIALOGS_FILE, 'w', encoding='utf-8') as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=2))


# Проверка админа и оператора
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def is_operator(user_id: int) -> bool:
    return user_id in OPERATOR_IDS

def is_admin_or_operator(user_id: int) -> bool:
    return user_id in ADMIN_IDS or user_id in OPERATOR_IDS


# Функции для работы с диалогами
async def create_dialog(user_id: int, user_name: str, user_phone: str, username: str, button_path: list) -> str:
    """Создает новый диалог и возвращает его ID. Если уже есть активный диалог, возвращает его ID."""
    dialogs_data = await load_dialogs()
    
    # Проверяем, есть ли уже активный диалог
    existing_dialog_id = dialogs_data["user_active_dialogs"].get(str(user_id))
    if existing_dialog_id:
        existing_dialog = dialogs_data["dialogs"].get(existing_dialog_id)
        if existing_dialog and existing_dialog["status"] in ["active", "pending"]:
            # Возвращаем существующий активный диалог
            return existing_dialog_id
    
    # Создаем новый диалог только если активного нет
    dialog_id = f"dialog_{user_id}_{int(datetime.now().timestamp())}"
    
    dialogs_data["dialogs"][dialog_id] = {
        "user_id": user_id,
        "user_name": user_name,
        "user_phone": user_phone,
        "username": username,
        "operator_id": None,
        "status": "pending",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "button_path": button_path,
        "messages": []
    }
    
    dialogs_data["user_active_dialogs"][str(user_id)] = dialog_id
    
    await save_dialogs(dialogs_data)
    return dialog_id


async def accept_dialog(dialog_id: str, operator_id: int):
    """Принимает диалог оператором/админом"""
    dialogs_data = await load_dialogs()
    
    if dialog_id not in dialogs_data["dialogs"]:
        return False
    
    dialog = dialogs_data["dialogs"][dialog_id]
    
    # Если диалог уже активен и назначен этому оператору, просто возвращаем True
    if dialog["status"] == "active" and dialog.get("operator_id") == operator_id:
        return True
    
    # Если диалог уже активен, но назначен другому оператору, не меняем
    if dialog["status"] == "active":
        return False
    
    # Если диалог не pending, не принимаем
    if dialog["status"] != "pending":
        return False
    
    dialog["status"] = "active"
    dialog["operator_id"] = operator_id
    dialog["accepted_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Добавляем диалог в список активных диалогов оператора
    if str(operator_id) not in dialogs_data["operator_active_dialogs"]:
        dialogs_data["operator_active_dialogs"][str(operator_id)] = []
    
    if dialog_id not in dialogs_data["operator_active_dialogs"][str(operator_id)]:
        dialogs_data["operator_active_dialogs"][str(operator_id)].append(dialog_id)
    
    await save_dialogs(dialogs_data)
    return True


async def add_message_to_dialog(dialog_id: str, from_user: str, text: str):
    """Добавляет сообщение в диалог"""
    dialogs_data = await load_dialogs()
    
    if dialog_id not in dialogs_data["dialogs"]:
        return False
    
    dialogs_data["dialogs"][dialog_id]["messages"].append({
        "from": from_user,  # "user" или "operator"
        "text": text,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    
    await save_dialogs(dialogs_data)
    return True


async def close_dialog(dialog_id: str):
    """Закрывает диалог"""
    dialogs_data = await load_dialogs()
    
    if dialog_id not in dialogs_data["dialogs"]:
        return False
    
    dialog = dialogs_data["dialogs"][dialog_id]
    dialog["status"] = "closed"
    dialog["closed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Удаляем из активных диалогов пользователя
    user_id_str = str(dialog["user_id"])
    if user_id_str in dialogs_data["user_active_dialogs"]:
        if dialogs_data["user_active_dialogs"][user_id_str] == dialog_id:
            del dialogs_data["user_active_dialogs"][user_id_str]
    
    # Удаляем из активных диалогов оператора
    operator_id_str = str(dialog.get("operator_id"))
    if operator_id_str and operator_id_str in dialogs_data["operator_active_dialogs"]:
        if dialog_id in dialogs_data["operator_active_dialogs"][operator_id_str]:
            dialogs_data["operator_active_dialogs"][operator_id_str].remove(dialog_id)
    
    await save_dialogs(dialogs_data)
    return True


async def get_user_active_dialog(user_id: int) -> str | None:
    """Получает ID активного или ожидающего диалога пользователя"""
    dialogs_data = await load_dialogs()
    dialog_id = dialogs_data["user_active_dialogs"].get(str(user_id))
    
    if dialog_id:
        dialog = dialogs_data["dialogs"].get(dialog_id)
        if dialog and dialog["status"] in ["active", "pending"]:
            return dialog_id
    
    return None


async def get_active_dialogs_for_operator(operator_id: int) -> list:
    """Получает список активных диалогов для оператора/админа"""
    dialogs_data = await load_dialogs()
    dialog_ids = dialogs_data["operator_active_dialogs"].get(str(operator_id), [])
    
    active_dialogs = []
    for dialog_id in dialog_ids:
        dialog = dialogs_data["dialogs"].get(dialog_id)
        if dialog and dialog["status"] == "active":
            active_dialogs.append((dialog_id, dialog))
    
    return active_dialogs


async def get_pending_dialogs() -> list:
    """Получает список ожидающих диалогов"""
    dialogs_data = await load_dialogs()
    pending = []
    
    for dialog_id, dialog in dialogs_data["dialogs"].items():
        if dialog["status"] == "pending":
            pending.append((dialog_id, dialog))
    
    return pending


# Функция для получения текста кнопки из callback_data
def get_button_text_from_callback(callback_data: str) -> str:
    """Получает читаемый текст кнопки из callback_data"""
    # Убираем префикс service_
    if callback_data.startswith("service_"):
        callback_data = callback_data.replace("service_", "")
    
    # Маппинг для основных услуг
    mapping = {
        "rvp": "РВП",
        "vnzh": "ВНЖ",
        "citizenship": "Гражданство",
        "registration": "Регистрация",
        "migration_account": "Миграционный учёт",
        "declaration_3ndfl": "Декларация (3-НДФЛ)",
        "translation": "Перевод документов",
        "contracts": "Договоры",
        "notifications": "Уведомления",
        "contacts": "Контакты",
        "migration_account_main": "Миграционный учёт",
        "migration_account_marriage": "Продление миграционного учёта по браку",
        "migration_account_parents": "Оформление на основании отца / матери",
        "contracts_gph": "Гражданско-правовой договор (ГПХ) / трудовой договор",
        "contracts_rent": "Договор найма / безвозмездного пользования жилым помещением",
        "contracts_car": "Договор купли-продажи автомобиля / договор аренды",
        "notifications_residence": "Уведомление о проживании",
        "notifications_gph_conclusion": "Уведомление о заключении договора ГПХ",
        "notifications_gph_termination": "Уведомление о расторжении договора ГПХ",
        "back_to_menu": "Назад (в главное меню)",
        "back_to_migration_account": "Назад (в Миграционный учёт)",
        "back_to_contracts": "Назад (в Договоры)",
        "back_to_notifications": "Назад (в Уведомления)"
    }
    
    return mapping.get(callback_data, callback_data.replace("_", " ").title())


# Функция для отправки уведомления о новом диалоге админу и оператору
async def send_dialog_notification(dialog_id: str, user_info: dict, button_path: list):
    """Отправляет уведомление о новом диалоге админу, оператору и в канал"""
    try:
        message_text = "🔔 <b>Новое обращение к оператору</b>\n\n"
        message_text += f"👤 <b>Имя:</b> {user_info.get('name', 'Не указано')}\n"
        message_text += f"📱 <b>Номер телефона:</b> {user_info.get('phone', 'Не указан')}\n"
        
        if user_info.get('username'):
            message_text += f"🔗 <b>Username:</b> @{user_info['username']}\n"
        else:
            message_text += f"🔗 <b>Username:</b> Не указан\n"
        
        if button_path:
            message_text += f"\n📍 <b>Путь нажатых кнопок:</b>\n"
            for i, button in enumerate(button_path, 1):
                message_text += f"{i}. {button}\n"
        else:
            message_text += "\n📍 <b>Путь нажатых кнопок:</b> Главное меню\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Принять диалог", callback_data=f"accept_dialog_{dialog_id}")]
        ])
        
        # Формируем текст для канала (без ID пользователя)
        channel_text = "🔔 <b>Новое обращение к оператору</b>\n\n"
        channel_text += f"👤 <b>Имя:</b> {user_info.get('name', 'Не указано')}\n"
        channel_text += f"📱 <b>Номер телефона:</b> {user_info.get('phone', 'Не указан')}\n"
        
        if user_info.get('username'):
            channel_text += f"🔗 <b>Username:</b> @{user_info['username']}\n"
        
        if button_path:
            channel_text += f"\n📍 <b>Путь нажатых кнопок:</b>\n"
            for i, button in enumerate(button_path, 1):
                channel_text += f"{i}. {button}\n"
        else:
            channel_text += "\n📍 <b>Путь нажатых кнопок:</b> Главное меню\n"
        
        # Отправляем в канал (без ID пользователя)
        try:
            await bot.send_message(
                chat_id=NOTIFICATION_CHAT_ID,
                text=channel_text,
                parse_mode="HTML"
            )
            print(f"[NOTIFICATION] Уведомление отправлено в канал {NOTIFICATION_CHAT_ID}")
        except Exception as e:
            print(f"[NOTIFICATION] Ошибка отправки в канал: {e}")
        
        # Отправляем всем операторам
        for operator_id in OPERATOR_IDS:
            try:
                await bot.send_message(
                    chat_id=operator_id,
                    text=message_text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
                print(f"[NOTIFICATION] Уведомление отправлено оператору {operator_id}")
            except Exception as e:
                print(f"[NOTIFICATION] Ошибка отправки оператору {operator_id}: {e}")
        
        print(f"[NOTIFICATION] Уведомления о диалоге {dialog_id} отправлены")
        
    except Exception as e:
        import traceback
        print(f"[NOTIFICATION ERROR] Ошибка при отправке уведомления о диалоге:")
        traceback.print_exc()


# Функция для создания безопасного callback_data из текста кнопки
def button_to_callback(button_text: str) -> str:
    """Преобразует текст кнопки в безопасный callback_data"""
    # Маппинг для преобразования
    mapping = {
        "РВП": "rvp",
        "ВНЖ": "vnzh",
        "Гражданство": "citizenship",
        "Регистрация": "registration",
        "Миграционный учёт": "migration_account",
        "Декларация (3-НДФЛ)": "declaration_3ndfl",
        "Перевод документов": "translation",
        "Договоры": "contracts",
        "Уведомления": "notifications",
        "Контакты": "contacts"
    }
    return mapping.get(button_text, button_text.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("-", "_"))


# Маппинг для восстановления исходного названия из callback_data
CALLBACK_TO_BUTTON = {
    "rvp": "РВП",
    "vnzh": "ВНЖ",
    "citizenship": "Гражданство",
    "registration": "Регистрация",
    "migration_account": "Миграционный учёт",
    "declaration_3ndfl": "Декларация (3-НДФЛ)",
    "translation": "Перевод документов",
    "contracts": "Договоры",
    "notifications": "Уведомления",
    "contacts": "Контакты"
}


# Функция для создания главного меню
async def get_main_menu_keyboard():
    buttons_data = await load_buttons()
    texts = await load_texts()
    menu_buttons = buttons_data.get("main_menu", [])
    
    keyboard_buttons = []
    for row in menu_buttons:
        row_buttons = []
        for btn in row:
            callback_data_value = button_to_callback(btn)
            full_callback = f"service_{callback_data_value}"
            # Проверяем, есть ли сохраненный текст кнопки
            button_text_key = f"button_text_main_{callback_data_value}"
            button_text = texts.get(button_text_key, btn)
            row_buttons.append(InlineKeyboardButton(text=button_text, callback_data=full_callback))
        keyboard_buttons.append(row_buttons)
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)


# Приветственное сообщение - запрос номера телефона
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    phones = await load_phones()
    
    # Проверяем, есть ли уже сохраненный номер телефона у пользователя
    if user_id in phones and phones[user_id].get("phone"):
        # Номер уже есть - сразу показываем меню
        user_name = message.from_user.first_name or "Пользователь"
        texts = await load_texts()
        
        welcome_text = texts.get("welcome_message", 
            "👋 Добро пожаловать, {name}!\n\n✨ Мы рады приветствовать вас в нашем сервисе!")
        
        welcome_text = welcome_text.format(name=user_name)
        
        keyboard = await get_main_menu_keyboard()
        
        await message.answer(welcome_text, reply_markup=keyboard)
        await state.clear()
        return
    
    # Номера нет - запрашиваем его
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    
    await message.answer(
        "👋 Добро пожаловать!\n\n"
        "Для начала работы с ботом, пожалуйста, поделитесь своим номером телефона.",
        reply_markup=keyboard
    )
    
    await state.set_state(UserStates.waiting_phone)


# Обработка получения номера телефона
@dp.message(UserStates.waiting_phone, F.contact)
async def handle_contact(message: Message, state: FSMContext):
    contact = message.contact
    user_id = str(message.from_user.id)
    
    # Сохраняем номер телефона в файл
    phones = await load_phones()
    phones[user_id] = {
        "phone": contact.phone_number,
        "first_name": contact.first_name or message.from_user.first_name,
        "last_name": contact.last_name or message.from_user.last_name,
        "username": message.from_user.username
    }
    await save_phones(phones)
    
    # Удаляем клавиатуру с кнопкой отправки номера
    await message.answer("✅ Номер телефона сохранён.", reply_markup=ReplyKeyboardRemove())
    
    # Сразу показываем приветственное сообщение и меню
    user_name = message.from_user.first_name or "Пользователь"
    texts = await load_texts()
    
    welcome_text = texts.get("welcome_message", 
        "👋 Добро пожаловать, {name}!\n\n✨ Мы рады приветствовать вас в нашем сервисе!")
    
    welcome_text = welcome_text.format(name=user_name)
    
    keyboard = await get_main_menu_keyboard()
    
    # Инициализируем путь кнопок для пользователя
    await state.update_data(button_path=[])
    
    # Показываем приветствие с inline меню
    await message.answer(welcome_text, reply_markup=keyboard)


# Обработка случая, когда пользователь не отправил контакт, а написал текст
@dp.message(UserStates.waiting_phone)
async def handle_text_instead_of_contact(message: Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    
    await message.answer(
        "❌ Пожалуйста, используйте кнопку ниже для отправки номера телефона.",
        reply_markup=keyboard
    )


# Админка - команда /admin (не требует номер телефона, только для админа)
@dp.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    # Перезагружаем конфигурацию для актуальных значений
    from dotenv import load_dotenv
    import importlib
    import config
    load_dotenv()
    importlib.reload(config)
    from config import ADMIN_IDS
    
    # Проверяем права доступа с обновленными значениями
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет доступа к админ-панели.")
        return
    
    # Очищаем состояние, если админ зашёл в админку
    await state.clear()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Редактировать текст", callback_data="admin_edit_texts")],
        [InlineKeyboardButton(text="🔘 Редактировать кнопки", callback_data="admin_edit_buttons")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])
    
    await message.answer("🔧 Админ-панель", reply_markup=keyboard)


# Команда /dialogs для операторов и админов
@dp.message(Command("dialogs"))
async def cmd_dialogs(message: Message, state: FSMContext):
    if not is_admin_or_operator(message.from_user.id):
        await message.answer("❌ У вас нет доступа к этой команде.")
        return
    
    operator_id = message.from_user.id
    await state.clear()
    
    # Получаем активные диалоги оператора
    active_dialogs = await get_active_dialogs_for_operator(operator_id)
    
    # Получаем ожидающие диалоги (если есть)
    pending_dialogs = await get_pending_dialogs()
    
    if not active_dialogs and not pending_dialogs:
        await message.answer("📭 Активных диалогов нет.")
        return
    
    response_text = "💬 <b>Список диалогов</b>\n\n"
    
    if pending_dialogs:
        response_text += "⏳ <b>Ожидающие диалоги:</b>\n"
        for dialog_id, dialog in pending_dialogs:
            username_text = f"@{dialog['username']}" if dialog.get("username") else "нет"
            response_text += f"\n🔔 <b>{dialog['user_name']}</b>\n"
            response_text += f"📱 {dialog['user_phone']}\n"
            response_text += f"🔗 {username_text}\n"
            response_text += f"⏰ {dialog['created_at']}\n"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Принять диалог", callback_data=f"accept_dialog_{dialog_id}")]
            ])
            await message.answer(response_text, parse_mode="HTML", reply_markup=keyboard)
            response_text = ""  # Очищаем для следующего диалога
    
    if active_dialogs:
        response_text += "\n📞 <b>Активные диалоги:</b>\n"
        for dialog_id, dialog in active_dialogs:
            username_text = f"@{dialog['username']}" if dialog.get("username") else "нет"
            response_text += f"\n👤 <b>{dialog['user_name']}</b>\n"
            response_text += f"📱 {dialog['user_phone']}\n"
            response_text += f"🔗 {username_text}\n"
            response_text += f"⏰ Принят: {dialog.get('accepted_at', 'N/A')}\n"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💬 Ответить", callback_data=f"reply_dialog_{dialog_id}")],
                [InlineKeyboardButton(text="❌ Закрыть", callback_data=f"close_dialog_{dialog_id}")]
            ])
            await message.answer(response_text, parse_mode="HTML", reply_markup=keyboard)
            response_text = ""  # Очищаем для следующего диалога


# Обработка callback админки
@dp.callback_query(F.data.startswith("admin_"))
async def admin_callback(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    action = callback.data
    await callback.answer()
    
    if action == "admin_edit_texts":
        # Группируем услуги по категориям
        buttons_list = [
            [InlineKeyboardButton(text="📝 Приветственное сообщение", callback_data="edit_text_welcome_message")],
            [InlineKeyboardButton(text="━━━ Основные услуги ━━━", callback_data="admin_noop")],
            [InlineKeyboardButton(text="✏️ РВП", callback_data="edit_text_service_rvp")],
            [InlineKeyboardButton(text="✏️ ВНЖ", callback_data="edit_text_service_vnzh")],
            [InlineKeyboardButton(text="✏️ Гражданство", callback_data="edit_text_service_citizenship")],
            [InlineKeyboardButton(text="✏️ Регистрация", callback_data="edit_text_service_registration")],
            [InlineKeyboardButton(text="✏️ Миграционный учёт", callback_data="edit_text_service_migration_account")],
            [InlineKeyboardButton(text="  └─ Миграционный учёт (основной)", callback_data="edit_text_service_migration_account_main")],
            [InlineKeyboardButton(text="  └─ По браку", callback_data="edit_text_service_migration_account_marriage")],
            [InlineKeyboardButton(text="  └─ По отцу/матери", callback_data="edit_text_service_migration_account_parents")],
            [InlineKeyboardButton(text="━━━ Дополнительные услуги ━━━", callback_data="admin_noop")],
            [InlineKeyboardButton(text="✏️ Декларация (3-НДФЛ)", callback_data="edit_text_service_declaration_3ndfl")],
            [InlineKeyboardButton(text="✏️ Перевод документов", callback_data="edit_text_service_translation")],
            [InlineKeyboardButton(text="━━━ Договоры ━━━", callback_data="admin_noop")],
            [InlineKeyboardButton(text="✏️ Договоры (меню)", callback_data="edit_text_service_contracts")],
            [InlineKeyboardButton(text="  └─ ГПХ / Трудовой договор", callback_data="edit_text_service_contracts_gph")],
            [InlineKeyboardButton(text="  └─ Найм жилья", callback_data="edit_text_service_contracts_rent")],
            [InlineKeyboardButton(text="  └─ Автомобиль", callback_data="edit_text_service_contracts_car")],
            [InlineKeyboardButton(text="━━━ Уведомления ━━━", callback_data="admin_noop")],
            [InlineKeyboardButton(text="✏️ Уведомления (меню)", callback_data="edit_text_service_notifications")],
            [InlineKeyboardButton(text="  └─ О проживании", callback_data="edit_text_service_notifications_residence")],
            [InlineKeyboardButton(text="  └─ О заключении ГПХ", callback_data="edit_text_service_notifications_gph_conclusion")],
            [InlineKeyboardButton(text="  └─ О расторжении ГПХ", callback_data="edit_text_service_notifications_gph_termination")],
            [InlineKeyboardButton(text="━━━ Контакты ━━━", callback_data="admin_noop")],
            [InlineKeyboardButton(text="✏️ Контакты", callback_data="edit_text_service_contacts")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons_list)
        await callback.message.edit_text("📝 Выберите текст для редактирования:", reply_markup=keyboard)
    
    elif action == "admin_edit_buttons":
        # Редактирование текстов кнопок главного меню
        buttons_data = await load_buttons()
        main_menu = buttons_data.get("main_menu", [])
        
        buttons_list = [
            [InlineKeyboardButton(text="━━━ Главное меню ━━━", callback_data="admin_noop")]
        ]
        
        for row in main_menu:
            for btn_text in row:
                buttons_list.append([
                    InlineKeyboardButton(text=f"✏️ {btn_text}", callback_data=f"edit_button_text_{btn_text}")
                ])
        
        buttons_list.extend([
            [InlineKeyboardButton(text="━━━ Подуслуги ━━━", callback_data="admin_noop")],
            [InlineKeyboardButton(text="✏️ Миграционный учёт", callback_data="edit_button_text_migration_sub_1")],
            [InlineKeyboardButton(text="✏️ Продление по браку", callback_data="edit_button_text_migration_sub_2")],
            [InlineKeyboardButton(text="✏️ По отцу/матери", callback_data="edit_button_text_migration_sub_3")],
            [InlineKeyboardButton(text="✏️ ГПХ/Трудовой договор", callback_data="edit_button_text_contracts_sub_1")],
            [InlineKeyboardButton(text="✏️ Найм жилья", callback_data="edit_button_text_contracts_sub_2")],
            [InlineKeyboardButton(text="✏️ Автомобиль", callback_data="edit_button_text_contracts_sub_3")],
            [InlineKeyboardButton(text="✏️ Уведомление о проживании", callback_data="edit_button_text_notifications_sub_1")],
            [InlineKeyboardButton(text="✏️ Уведомление о заключении ГПХ", callback_data="edit_button_text_notifications_sub_2")],
            [InlineKeyboardButton(text="✏️ Уведомление о расторжении ГПХ", callback_data="edit_button_text_notifications_sub_3")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons_list)
        await callback.message.edit_text("🔘 Выберите кнопку для редактирования текста:", reply_markup=keyboard)
    
    elif action == "admin_back":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Редактировать текст", callback_data="admin_edit_texts")],
            [InlineKeyboardButton(text="🔘 Редактировать кнопки", callback_data="admin_edit_buttons")]
        ])
        await callback.message.edit_text("🔧 Админ-панель", reply_markup=keyboard)
    
    elif action == "admin_noop":
        # Пустая операция для неактивных кнопок (заголовки)
        await callback.answer("ℹ️ Это заголовок раздела", show_alert=False)


# Редактирование текста услуги
@dp.callback_query(F.data.startswith("edit_text_"))
async def edit_text_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    text_key = callback.data.replace("edit_text_", "")
    # Если это welcome_message, используем его напрямую, иначе добавляем service_
    if text_key == "welcome_message":
        actual_key = "welcome_message"
    else:
        actual_key = text_key
    
    texts = await load_texts()
    current_text = texts.get(actual_key, "")
    
    await state.update_data(text_key=actual_key)
    await state.set_state(AdminStates.waiting_text_content)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_edit_texts")]
    ])
    
    preview_text = current_text[:200] + "..." if len(current_text) > 200 else current_text
    
    await callback.message.edit_text(
        f"✏️ Редактирование текста: <b>{actual_key}</b>\n\n"
        f"Текущий текст (первые 200 символов):\n{preview_text}\n\n"
        f"Отправьте новый текст:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


# Добавление нового текста
@dp.callback_query(F.data == "add_new_text")
async def add_new_text_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    await state.set_state(AdminStates.waiting_text_content)
    await state.update_data(text_key=None)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(
        "➕ Добавление нового текста\n\n"
        "Отправьте сообщение в формате:\n"
        "<code>ключ_текста|текст содержимого</code>\n\n"
        "Пример: welcome_message|Привет, {name}!",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


# Сохранение нового текста
@dp.message(AdminStates.waiting_text_content)
async def save_text_handler(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    data = await state.get_data()
    texts = await load_texts()
    
    if data.get("text_key"):
        # Редактирование существующего
        text_key = data["text_key"]
        texts[text_key] = message.text
        await save_texts(texts)
        await message.answer("✅ Текст успешно обновлён!")
    else:
        # Добавление нового
        if "|" in message.text:
            parts = message.text.split("|", 1)
            text_key = parts[0].strip()
            text_content = parts[1].strip()
            texts[text_key] = text_content
            await save_texts(texts)
            await message.answer(f"✅ Новый текст '{text_key}' успешно добавлен!")
        else:
            await message.answer("❌ Неверный формат. Используйте: ключ|текст")
    
    await state.clear()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Редактировать текст", callback_data="admin_edit_texts")],
        [InlineKeyboardButton(text="🔘 Редактировать кнопки", callback_data="admin_edit_buttons")]
    ])
    await message.answer("🔧 Админ-панель", reply_markup=keyboard)


# Маппинг для редактирования текста кнопок подуслуг
BUTTON_TEXT_MAPPING = {
    "migration_sub_1": ("Миграционный учёт", "service_migration_account_main"),
    "migration_sub_2": ("Продление миграционного учёта по браку", "service_migration_account_marriage"),
    "migration_sub_3": ("Оформление на основании отца / матери", "service_migration_account_parents"),
    "contracts_sub_1": ("Гражданско-правовой договор (ГПХ) / трудовой договор", "service_contracts_gph"),
    "contracts_sub_2": ("Договор найма / безвозмездного пользования жилым помещением", "service_contracts_rent"),
    "contracts_sub_3": ("Договор купли-продажи автомобиля / договор аренды", "service_contracts_car"),
    "notifications_sub_1": ("Уведомление о проживании", "service_notifications_residence"),
    "notifications_sub_2": ("Уведомление о заключении договора ГПХ", "service_notifications_gph_conclusion"),
    "notifications_sub_3": ("Уведомление о расторжении договора ГПХ", "service_notifications_gph_termination"),
}


# Редактирование текста кнопки
@dp.callback_query(F.data.startswith("edit_button_text_"))
async def edit_button_text_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    button_id = callback.data.replace("edit_button_text_", "")
    buttons_data = await load_buttons()
    
    # Получаем текущий текст кнопки
    current_text = None
    button_text_key = None
    
    if button_id.startswith("migration_sub_") or button_id.startswith("contracts_sub_") or button_id.startswith("notifications_sub_"):
        # Это подуслуга - текст берется из маппинга
        if button_id in BUTTON_TEXT_MAPPING:
            current_text, service_key = BUTTON_TEXT_MAPPING[button_id]
            button_text_key = f"button_text_{button_id}"
            # Проверяем, есть ли сохраненный текст кнопки
            texts = await load_texts()
            saved_text = texts.get(button_text_key, current_text)
            current_text = saved_text
    else:
        # Это кнопка главного меню - берем из buttons.json
        main_menu = buttons_data.get("main_menu", [])
        for row in main_menu:
            for btn in row:
                if button_to_callback(btn) == button_id or btn == button_id:
                    current_text = btn
                    button_text_key = f"button_text_main_{button_to_callback(btn)}"
                    break
            if current_text:
                break
        
        if not current_text:
            current_text = button_id
    
    await state.update_data(button_text_key=button_text_key, button_id=button_id)
    await state.set_state(AdminStates.waiting_button_text)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_edit_buttons")]
    ])
    
    await callback.message.edit_text(
        f"✏️ Редактирование текста кнопки\n\n"
        f"Текущий текст: <b>{current_text}</b>\n\n"
        f"Отправьте новый текст кнопки:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


# Редактирование кнопок (структура меню)
@dp.callback_query(F.data.startswith("edit_button_") & ~F.data.startswith("edit_button_text_"))
async def edit_button_structure_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    button_key = callback.data.replace("edit_button_", "")
    buttons = await load_buttons()
    current_buttons = buttons.get(button_key, [])
    
    await state.update_data(button_key=button_key)
    await state.set_state(AdminStates.waiting_button_content)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(
        f"✏️ Редактирование структуры кнопок: <b>{button_key}</b>\n\n"
        f"Текущие кнопки:\n<code>{json.dumps(current_buttons, ensure_ascii=False)}</code>\n\n"
        f"Отправьте новый формат кнопок в JSON формате:\n"
        f"Каждая строка - массив кнопок: [['Кнопка1', 'Кнопка2'], ['Кнопка3']]",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


# Добавление новых кнопок
@dp.callback_query(F.data == "add_new_buttons")
async def add_new_buttons_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    await state.set_state(AdminStates.waiting_button_content)
    await state.update_data(button_key=None)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(
        "➕ Добавление новых кнопок\n\n"
        "Отправьте сообщение в формате:\n"
        "<code>ключ_кнопок|[[\"Кнопка1\", \"Кнопка2\"], [\"Кнопка3\"]]</code>\n\n"
        "Пример: main_menu|[[\"РВП\", \"ВНЖ\"], [\"Контакты\"]]",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


# Сохранение текста кнопки
@dp.message(AdminStates.waiting_button_text)
async def save_button_text_handler(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    data = await state.get_data()
    button_text_key = data.get("button_text_key")
    button_id = data.get("button_id")
    
    if not button_text_key or not button_id:
        await message.answer("❌ Ошибка: не найдены данные кнопки")
        await state.clear()
        return
    
    # Сохраняем текст кнопки в texts.json
    texts = await load_texts()
    texts[button_text_key] = message.text
    await save_texts(texts)
    
    # Если это кнопка главного меню, обновляем buttons.json
    buttons = await load_buttons()
    main_menu = buttons.get("main_menu", [])
    updated = False
    
    for row_idx, row in enumerate(main_menu):
        for btn_idx, btn in enumerate(row):
            callback_val = button_to_callback(btn)
            if f"button_text_main_{callback_val}" == button_text_key:
                main_menu[row_idx][btn_idx] = message.text
                updated = True
                break
        if updated:
            break
    
    if updated:
        buttons["main_menu"] = main_menu
        await save_buttons(buttons)
    
    await message.answer(f"✅ Текст кнопки успешно обновлён!")
    await state.clear()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Редактировать текст", callback_data="admin_edit_texts")],
        [InlineKeyboardButton(text="🔘 Редактировать кнопки", callback_data="admin_edit_buttons")]
    ])
    await message.answer("🔧 Админ-панель", reply_markup=keyboard)


# Сохранение структуры кнопок
@dp.message(AdminStates.waiting_button_content)
async def save_button_structure_handler(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    data = await state.get_data()
    buttons = await load_buttons()
    
    try:
        if data.get("button_key"):
            # Редактирование существующих
            button_key = data["button_key"]
            new_buttons = json.loads(message.text)
            buttons[button_key] = new_buttons
            await save_buttons(buttons)
            await message.answer(f"✅ Кнопки '{button_key}' успешно обновлены!")
        else:
            # Добавление новых
            if "|" in message.text:
                parts = message.text.split("|", 1)
                button_key = parts[0].strip()
                button_content = json.loads(parts[1].strip())
                buttons[button_key] = button_content
                await save_buttons(buttons)
                await message.answer(f"✅ Новые кнопки '{button_key}' успешно добавлены!")
            else:
                await message.answer("❌ Неверный формат. Используйте: ключ|JSON")
    except json.JSONDecodeError:
        await message.answer("❌ Ошибка парсинга JSON. Проверьте формат.")
    
    await state.clear()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Редактировать текст", callback_data="admin_edit_texts")],
        [InlineKeyboardButton(text="🔘 Редактировать кнопки", callback_data="admin_edit_buttons")]
    ])
    await message.answer("🔧 Админ-панель", reply_markup=keyboard)


# Обработка подуслуг "Уведомления" - ДОЛЖЕН БЫТЬ ПЕРЕД общим обработчиком service_
@dp.callback_query(F.data.in_(["service_notifications_residence", "service_notifications_gph_conclusion", "service_notifications_gph_termination"]))
async def handle_notifications_subservices(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        
        # Обновляем путь кнопок
        data = await state.get_data()
        button_path = data.get("button_path", [])
        if "Уведомления" not in button_path:
            button_path.append("Уведомления")
        button_name = get_button_text_from_callback(callback.data)
        button_path.append(button_name)
        await state.update_data(button_path=button_path)
        
        texts = await load_texts()
        callback_data = callback.data
        
        # Определяем текст в зависимости от выбранной подуслуги
        if callback_data == "service_notifications_residence":
            service_text = texts.get("service_notifications_residence", 
                "📌 Уведомление о проживании\nежегодная отметка по ВНЖ или РВП\n\nДля оформления потребуется:\n\n1️⃣ Документы:\n• Паспорт + ВНЖ или РВП\n\n2️⃣ Регистрация:\n• Регистрация по месту жительства\nили миграционный учёт\n\n3️⃣ Доход (для ВНЖ):\n• Размер дохода\n• При официальной работе —\nсправка о доходах, должность, адрес организации\n\n4️⃣ Выезды за границу:\n• Информация обо всех периодах выезда и въезда\nза отчётный год")
        elif callback_data == "service_notifications_gph_conclusion":
            service_text = texts.get("service_notifications_gph_conclusion", 
                "📌 Уведомление о заключении договора ГПХ\n\nДля оформления потребуется:\n\n👤 От заказчика:\n• Паспорта обеих сторон\n(или паспортные данные)\n• ИНН заказчика\n• Номер телефона заказчика\n• Профессия исполнителя\n• Адрес места работы\n• Патент исполнителя\n\n👷 От исполнителя (с патентом):\n• Паспорт (паспортные данные)\n• Патент\n• Медицинский полис\n(страховка)\n• ИНН (если не указан в патенте)\n• Номер телефона\n• Адрес места работы")
        elif callback_data == "service_notifications_gph_termination":
            service_text = texts.get("service_notifications_gph_termination", 
                "📌 Уведомление о расторжении договора ГПХ\n\nДля оформления потребуется:\n• Паспорта обеих сторон\n(или паспортные данные)\n• ИНН заказчика\n• Номер телефона заказчика\n• Профессия исполнителя\n• Адрес места работы\n• Патент исполнителя\n• Дата расторжения договора")
        else:
            service_text = "ℹ️ Функционал находится в разработке."
        
        # Создаём кнопки
        buttons = [
            [InlineKeyboardButton(text="💬 Чат с оператором", callback_data="chat_operator")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_notifications")]
        ]
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        # Пытаемся отредактировать сообщение, если не получается - отправляем новое
        try:
            await callback.message.edit_text(service_text, reply_markup=keyboard)
        except:
            await callback.message.answer(service_text, reply_markup=keyboard)
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            await callback.answer("❌ Произошла ошибка. Попробуйте позже.", show_alert=True)
        except:
            pass


# Обработка кнопки "Назад" (возврат к меню "Уведомления") - ДОЛЖЕН БЫТЬ ПЕРЕД back_to_menu
@dp.callback_query(F.data == "back_to_notifications")
async def handle_back_to_notifications(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        
        # Удаляем последние кнопки из пути до "Уведомления"
        data = await state.get_data()
        button_path = data.get("button_path", [])
        if "Уведомления" in button_path:
            idx = button_path.index("Уведомления")
            button_path = button_path[:idx+1]
        await state.update_data(button_path=button_path)
        
        texts = await load_texts()
        service_text = texts.get("service_notifications", 
            "📋 Ниже представлен полный перечень услуг, которые мы предоставляем:\n\n📌 Уведомление о проживании\n📌 Уведомление о заключении договора ГПХ\n📌 Уведомление о расторжении договора ГПХ\n\n💼 Для получения подробной информации выберите интересующую услугу из меню ниже.")
        
        btn1_text = texts.get("button_text_notifications_sub_1", "Уведомление о проживании")
        btn2_text = texts.get("button_text_notifications_sub_2", "Уведомление о заключении договора ГПХ")
        btn3_text = texts.get("button_text_notifications_sub_3", "Уведомление о расторжении договора ГПХ")
        buttons = [
            [InlineKeyboardButton(text=btn1_text, callback_data="service_notifications_residence")],
            [InlineKeyboardButton(text=btn2_text, callback_data="service_notifications_gph_conclusion")],
            [InlineKeyboardButton(text=btn3_text, callback_data="service_notifications_gph_termination")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
        ]
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        # Пытаемся отредактировать текущее сообщение
        try:
            await callback.message.edit_text(service_text, reply_markup=keyboard)
        except Exception as edit_error:
            # Если не получается отредактировать, отправляем новое сообщение
            try:
                await callback.message.delete()
            except:
                pass
            await callback.message.answer(service_text, reply_markup=keyboard)
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            await callback.answer("❌ Произошла ошибка. Попробуйте позже.", show_alert=True)
        except:
            pass


# Обработка подуслуг "Договоры" - ДОЛЖЕН БЫТЬ ПЕРЕД общим обработчиком service_
@dp.callback_query(F.data.in_(["service_contracts_gph", "service_contracts_rent", "service_contracts_car"]))
async def handle_contracts_subservices(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        
        # Обновляем путь кнопок
        data = await state.get_data()
        button_path = data.get("button_path", [])
        if "Договоры" not in button_path:
            button_path.append("Договоры")
        button_name = get_button_text_from_callback(callback.data)
        button_path.append(button_name)
        await state.update_data(button_path=button_path)
        
        texts = await load_texts()
        callback_data = callback.data
        
        # Определяем текст в зависимости от выбранной подуслуги
        if callback_data == "service_contracts_gph":
            service_text = texts.get("service_contracts_gph", 
                "📌 Гражданско-правовой договор (ГПХ) / трудовой договор\n\nЗаключение договора включает:\n• Подготовку договора\n• Уведомления в госорганы\n• Описи документов\n• Конверты — 2 пакета документов\n\nДля оформления необходимо предоставить:\n\n👤 От заказчика:\n• Паспорт РФ + регистрация (прописка)\n• ИНН\n• Адрес места работы\n• Срок действия договора\n(дата окончания или бессрочно)\n• Размер вознаграждения:\n— почасовая оплата (XXX ₽/час)\n— или ежемесячная оплата (XXXXX ₽/мес)\n\n👷 От исполнителя (работника):\n• Паспорт\n• Патент\n• ИНН (если не указан в патенте)\n• Регистрация\n(прописка или миграционный учёт)\n• Медицинская страховка\n(полис ДМС)")
        elif callback_data == "service_contracts_rent":
            service_text = texts.get("service_contracts_rent", 
                "📌 Договор найма / безвозмездного пользования жилым помещением\n\nДля подготовки договора потребуется:\n• Паспорта обеих сторон\n(или паспортные данные)\n• Выписка из ЕГРН\n• Номера телефонов сторон")
        elif callback_data == "service_contracts_car":
            service_text = texts.get("service_contracts_car", 
                "📌 Договор купли-продажи автомобиля / договор аренды\n\nВ услугу входит:\n• Подготовка договора\n• Заявление в ГИБДД\n(на постановку или снятие с учёта)\n\nДля оформления потребуется:\n• СТС\n• ПТС\n• Паспорта обеих сторон\n(или паспортные данные)\n• Номера телефонов сторон")
        else:
            service_text = "ℹ️ Функционал находится в разработке."
        
        # Создаём кнопки
        buttons = [
            [InlineKeyboardButton(text="💬 Чат с оператором", callback_data="chat_operator")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_contracts")]
        ]
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        # Пытаемся отредактировать сообщение, если не получается - отправляем новое
        try:
            await callback.message.edit_text(service_text, reply_markup=keyboard)
        except:
            await callback.message.answer(service_text, reply_markup=keyboard)
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            await callback.answer("❌ Произошла ошибка. Попробуйте позже.", show_alert=True)
        except:
            pass


# Обработка кнопки "Назад" (возврат к меню "Договоры") - ДОЛЖЕН БЫТЬ ПЕРЕД back_to_menu
@dp.callback_query(F.data == "back_to_contracts")
async def handle_back_to_contracts(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        
        # Удаляем последние кнопки из пути до "Договоры"
        data = await state.get_data()
        button_path = data.get("button_path", [])
        if "Договоры" in button_path:
            idx = button_path.index("Договоры")
            button_path = button_path[:idx+1]
        await state.update_data(button_path=button_path)
        
        texts = await load_texts()
        service_text = texts.get("service_contracts", 
            "📋 Ниже представлен полный перечень услуг, которые мы предоставляем:\n\n📌 Гражданско-правовой договор (ГПХ) / трудовой договор\n📌 Договор найма / безвозмездного пользования жилым помещением\n📌 Договор купли-продажи автомобиля / договор аренды\n\n💼 Для получения подробной информации выберите интересующую услугу из меню ниже.")
        
        btn1_text = texts.get("button_text_contracts_sub_1", "Гражданско-правовой договор (ГПХ) / трудовой договор")
        btn2_text = texts.get("button_text_contracts_sub_2", "Договор найма / безвозмездного пользования жилым помещением")
        btn3_text = texts.get("button_text_contracts_sub_3", "Договор купли-продажи автомобиля / договор аренды")
        buttons = [
            [InlineKeyboardButton(text=btn1_text, callback_data="service_contracts_gph")],
            [InlineKeyboardButton(text=btn2_text, callback_data="service_contracts_rent")],
            [InlineKeyboardButton(text=btn3_text, callback_data="service_contracts_car")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
        ]
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        # Пытаемся отредактировать текущее сообщение
        try:
            await callback.message.edit_text(service_text, reply_markup=keyboard)
        except Exception as edit_error:
            # Если не получается отредактировать, отправляем новое сообщение
            try:
                await callback.message.delete()
            except:
                pass
            await callback.message.answer(service_text, reply_markup=keyboard)
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            await callback.answer("❌ Произошла ошибка. Попробуйте позже.", show_alert=True)
        except:
            pass


# Обработка подуслуг "Миграционный учёт" - ДОЛЖЕН БЫТЬ ПЕРЕД общим обработчиком service_
@dp.callback_query(F.data.in_(["service_migration_account_main", "service_migration_account_marriage", "service_migration_account_parents"]))
async def handle_migration_account_subservices(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        
        # Обновляем путь кнопок
        data = await state.get_data()
        button_path = data.get("button_path", [])
        if "Миграционный учёт" not in button_path:
            button_path.append("Миграционный учёт")
        button_name = get_button_text_from_callback(callback.data)
        button_path.append(button_name)
        await state.update_data(button_path=button_path)
        
        texts = await load_texts()
        callback_data = callback.data
        
        # Определяем текст в зависимости от выбранной подуслуги
        if callback_data == "service_migration_account_main":
            service_text = texts.get("service_migration_account_main", 
                "📌 Миграционный учёт\n\nДля постановки на миграционный учёт потребуется:\n\n🧑‍💼 От собственника жилья (принимающей стороны):\n• Паспорт с регистрацией\n(паспортные данные: ФИО, серия и номер, кем и когда выдан, адрес прописки)\n• Документ на недвижимость\n(выписка из ЕГРН)\n• Номер телефона\n\n🌍 От иностранного гражданина:\n• Паспорт — все страницы с отметками\n• Место рождения\n(страна, населённый пункт)\n• Номер телефона\n• Миграционная карта — с двух сторон\n• Патент — с двух сторон\n(или трудовой договор)\n• Все чеки по патенту\n• Карточка дактилоскопии\n(отпечатки пальцев — для всех старше 6 лет)")
        elif callback_data == "service_migration_account_marriage":
            service_text = texts.get("service_migration_account_marriage", 
                "📌 Продление миграционного учёта по браку\n\nДля оформления потребуется:\n\n🌍 От иностранного гражданина:\n• Паспорт\n• Место рождения\n(страна, населённый пункт)\n• Номер телефона\n• Миграционная карта — с двух сторон\n• Свидетельство о браке\n• Медицинские справки и сопутствующие документы\n(для всех старше 6 лет)\n• Карточка дактилоскопии\n(отпечатки пальцев — для всех старше 6 лет)\n\n👫 От супруга / супруги:\n• Паспорт РФ или ВНЖ\n• Регистрация по месту жительства")
        elif callback_data == "service_migration_account_parents":
            service_text = texts.get("service_migration_account_parents", 
                "📌 Оформление на основании отца / матери\nдля ребёнка (сына или дочери)\n\nДля оформления потребуется:\n\n👶 От ребёнка:\n• Паспорт\n• Номер телефона\n• Миграционная карта\n• Свидетельство о рождении\n• Медицинские справки и сопутствующие документы\n• Карточка дактилоскопии\n(отпечатки пальцев — для всех старше 6 лет)\n\n👨‍👩‍👧 От отца / матери:\n• Паспорт РФ или ВНЖ\n• Регистрация по месту жительства\n• Номер телефона\n• Миграционная карта\n\nЕсли у отца / матери есть патент, дополнительно:\n• Патент\n• Все чеки по патенту\n\nТакже потребуется:\n• Место рождения\n(страна, населённый пункт)\n• Медицинские справки и сопутствующие документы\n• Карточка дактилоскопии\n(отпечатки пальцев — для всех старше 6 лет)")
        else:
            service_text = "ℹ️ Функционал находится в разработке."
        
        # Создаём кнопки
        buttons = [
            [InlineKeyboardButton(text="💬 Чат с оператором", callback_data="chat_operator")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_migration_account")]
        ]
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        # Пытаемся отредактировать сообщение, если не получается - отправляем новое
        try:
            await callback.message.edit_text(service_text, reply_markup=keyboard)
        except:
            await callback.message.answer(service_text, reply_markup=keyboard)
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            await callback.answer("❌ Произошла ошибка. Попробуйте позже.", show_alert=True)
        except:
            pass


# Обработка кнопки "Назад" (возврат к меню "Миграционный учёт") - ДОЛЖЕН БЫТЬ ПЕРЕД back_to_menu
@dp.callback_query(F.data == "back_to_migration_account")
async def handle_back_to_migration_account(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        
        # Удаляем последние кнопки из пути до "Миграционный учёт"
        data = await state.get_data()
        button_path = data.get("button_path", [])
        if "Миграционный учёт" in button_path:
            idx = button_path.index("Миграционный учёт")
            button_path = button_path[:idx+1]
        await state.update_data(button_path=button_path)
        
        texts = await load_texts()
        service_text = texts.get("service_migration_account", 
            "📋 Ниже представлен полный перечень услуг, которые мы предоставляем:\n\n📌 Миграционный учёт\n📌 Продление миграционного учёта по браку\n📌 Оформление на основании отца / матери\n\n💼 Для получения подробной информации выберите интересующую услугу из меню ниже.")
        
        btn1_text = texts.get("button_text_migration_sub_1", "Миграционный учёт")
        btn2_text = texts.get("button_text_migration_sub_2", "Продление миграционного учёта по браку")
        btn3_text = texts.get("button_text_migration_sub_3", "Оформление на основании отца / матери")
        buttons = [
            [InlineKeyboardButton(text=btn1_text, callback_data="service_migration_account_main")],
            [InlineKeyboardButton(text=btn2_text, callback_data="service_migration_account_marriage")],
            [InlineKeyboardButton(text=btn3_text, callback_data="service_migration_account_parents")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
        ]
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        # Пытаемся отредактировать текущее сообщение
        try:
            await callback.message.edit_text(service_text, reply_markup=keyboard)
        except Exception as edit_error:
            # Если не получается отредактировать, отправляем новое сообщение
            try:
                await callback.message.delete()
            except:
                pass
            await callback.message.answer(service_text, reply_markup=keyboard)
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            await callback.answer("❌ Произошла ошибка. Попробуйте позже.", show_alert=True)
        except:
            pass


# Обработка инлайн-кнопок услуг
@dp.callback_query(F.data.startswith("service_"))
async def handle_service(callback: CallbackQuery, state: FSMContext):
    try:
        # Пропускаем обработку подуслуг "Миграционный учёт", "Договоры" и "Уведомления" - они обрабатываются отдельными обработчиками
        if callback.data in ["service_migration_account_main", "service_migration_account_marriage", "service_migration_account_parents",
                             "service_contracts_gph", "service_contracts_rent", "service_contracts_car",
                             "service_notifications_residence", "service_notifications_gph_conclusion", "service_notifications_gph_termination"]:
            return
        
        callback_data = callback.data.replace("service_", "")
        service_name = CALLBACK_TO_BUTTON.get(callback_data, callback_data.replace("_", " ").title())
        
        # Обновляем путь кнопок
        data = await state.get_data()
        button_path = data.get("button_path", [])
        button_path.append(service_name)
        await state.update_data(button_path=button_path)
        
        await callback.answer()
        
        # Загружаем тексты услуг
        texts = await load_texts()
        service_key = f"service_{callback_data}"
        
        # Если есть специальный текст для услуги, используем его
        service_text = texts.get(service_key, f"ℹ️ Вы выбрали: {service_name}\n\nФункционал находится в разработке.")
        
        # Создаём кнопки
        buttons = []
        
        # Специальная обработка для "Миграционный учёт" - показываем подуслуги
        if callback_data == "migration_account":
            # Используем сохраненные тексты кнопок, если они есть
            btn1_text = texts.get("button_text_migration_sub_1", "Миграционный учёт")
            btn2_text = texts.get("button_text_migration_sub_2", "Продление миграционного учёта по браку")
            btn3_text = texts.get("button_text_migration_sub_3", "Оформление на основании отца / матери")
            buttons.append([InlineKeyboardButton(text=btn1_text, callback_data="service_migration_account_main")])
            buttons.append([InlineKeyboardButton(text=btn2_text, callback_data="service_migration_account_marriage")])
            buttons.append([InlineKeyboardButton(text=btn3_text, callback_data="service_migration_account_parents")])
            buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])
        elif callback_data == "contracts":
            # Специальная обработка для "Договоры" - показываем подуслуги
            btn1_text = texts.get("button_text_contracts_sub_1", "Гражданско-правовой договор (ГПХ) / трудовой договор")
            btn2_text = texts.get("button_text_contracts_sub_2", "Договор найма / безвозмездного пользования жилым помещением")
            btn3_text = texts.get("button_text_contracts_sub_3", "Договор купли-продажи автомобиля / договор аренды")
            buttons.append([InlineKeyboardButton(text=btn1_text, callback_data="service_contracts_gph")])
            buttons.append([InlineKeyboardButton(text=btn2_text, callback_data="service_contracts_rent")])
            buttons.append([InlineKeyboardButton(text=btn3_text, callback_data="service_contracts_car")])
            buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])
        elif callback_data == "notifications":
            # Специальная обработка для "Уведомления" - показываем подуслуги
            btn1_text = texts.get("button_text_notifications_sub_1", "Уведомление о проживании")
            btn2_text = texts.get("button_text_notifications_sub_2", "Уведомление о заключении договора ГПХ")
            btn3_text = texts.get("button_text_notifications_sub_3", "Уведомление о расторжении договора ГПХ")
            buttons.append([InlineKeyboardButton(text=btn1_text, callback_data="service_notifications_residence")])
            buttons.append([InlineKeyboardButton(text=btn2_text, callback_data="service_notifications_gph_conclusion")])
            buttons.append([InlineKeyboardButton(text=btn3_text, callback_data="service_notifications_gph_termination")])
            buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])
        elif callback_data == "contacts":
            # Специальная обработка для "Контакты" - кнопка "Чат с оператором" и "Назад"
            buttons.append([InlineKeyboardButton(text="💬 Чат с оператором", callback_data="chat_operator")])
            buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])
        else:
            # Для остальных услуг - стандартные кнопки
            buttons.append([InlineKeyboardButton(text="💬 Чат с оператором", callback_data="chat_operator")])
            buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.answer(service_text, reply_markup=keyboard)
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            await callback.answer("❌ Произошла ошибка. Попробуйте позже.", show_alert=True)
        except:
            pass


# Обработка кнопки "Чат с оператором"
@dp.callback_query(F.data == "chat_operator")
async def handle_chat_operator(callback: CallbackQuery, state: FSMContext):
    print(f"[CHAT_OPERATOR] Обработчик вызван для пользователя {callback.from_user.id}")
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        
        # Проверяем, есть ли уже активный диалог
        active_dialog_id = await get_user_active_dialog(user_id)
        if active_dialog_id:
            dialogs_data = await load_dialogs()
            dialog = dialogs_data["dialogs"].get(active_dialog_id)
            status_text = "активен" if dialog and dialog.get("status") == "active" else "ожидает ответа"
            
            await callback.message.answer(
                f"У вас уже есть диалог с оператором ({status_text}).\n\n"
                f"💬 Просто напишите ваше сообщение в чат - оно будет отправлено оператору.\n\n"
                f"Или отмените диалог, если хотите создать новый.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💬 Продолжить диалог", callback_data="continue_dialog")],
                    [InlineKeyboardButton(text="❌ Отменить диалог", callback_data=f"cancel_user_dialog_{active_dialog_id}")],
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
                ])
            )
            return
        
        # Получаем данные пользователя
        user_name = callback.from_user.first_name or "Не указано"
        username = callback.from_user.username or None
        
        # Загружаем сохраненный номер телефона
        phones = await load_phones()
        phone = phones.get(str(user_id), {}).get("phone", "Не указан")
        
        # Получаем путь нажатых кнопок
        data = await state.get_data()
        button_path = data.get("button_path", [])
        button_path.append("💬 Чат с оператором")
        
        # Создаем диалог
        dialog_id = await create_dialog(user_id, user_name, phone, username, button_path)
        print(f"[CHAT_OPERATOR] Создан диалог {dialog_id}")
        
        # Формируем информацию о пользователе
        user_info = {
            "name": user_name,
            "phone": phone,
            "user_id": user_id,
            "username": username
        }
        
        # Отправляем уведомления админу и оператору
        await send_dialog_notification(dialog_id, user_info, button_path)
        
        # Переводим пользователя в состояние диалога
        await state.set_state(UserStates.in_dialog)
        await state.update_data(dialog_id=dialog_id)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить диалог", callback_data=f"cancel_user_dialog_{dialog_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
        ])
        
        await callback.message.answer(
            "💬 Напишите ваш вопрос:",
            reply_markup=keyboard
        )
    except Exception as e:
        import traceback
        print(f"[CHAT_OPERATOR ERROR] Ошибка в обработчике:")
        traceback.print_exc()
        try:
            await callback.message.answer("❌ Произошла ошибка. Попробуйте позже.")
        except Exception as send_error:
            print(f"[CHAT_OPERATOR ERROR] Не удалось отправить сообщение об ошибке: {send_error}")


# Обработка кнопки "Назад" (возврат в главное меню)
@dp.callback_query(F.data == "back_to_menu")
async def handle_back_to_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    # Проверяем, есть ли активный диалог
    user_id = callback.from_user.id
    active_dialog_id = await get_user_active_dialog(user_id)
    
    if active_dialog_id:
        # Если есть активный диалог, очищаем состояние диалога
        await state.set_state(None)
        await state.update_data(dialog_id=None)
    
    # Очищаем путь кнопок (возврат в главное меню)
    await state.update_data(button_path=[])
    
    user_name = callback.from_user.first_name or "Пользователь"
    texts = await load_texts()
    
    welcome_text = texts.get("welcome_message", 
        "👋 Добро пожаловать, {name}!\n\n✨ Мы рады приветствовать вас в нашем сервисе!")
    
    welcome_text = welcome_text.format(name=user_name)
    
    keyboard = await get_main_menu_keyboard()
    
    # Пытаемся отредактировать сообщение, если не получается - отправляем новое
    try:
        await callback.message.edit_text(welcome_text, reply_markup=keyboard)
    except:
        await callback.message.answer(welcome_text, reply_markup=keyboard)


# Обработка принятия диалога
@dp.callback_query(F.data.startswith("accept_dialog_"))
async def handle_accept_dialog(callback: CallbackQuery, state: FSMContext):
    if not is_admin_or_operator(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    dialog_id = callback.data.replace("accept_dialog_", "")
    operator_id = callback.from_user.id
    
    success = await accept_dialog(dialog_id, operator_id)
    
    if success:
        dialogs_data = await load_dialogs()
        dialog = dialogs_data["dialogs"][dialog_id]
        
        # Просто обновляем сообщение без лишних уведомлений
        username_text = f"@{dialog['username']}" if dialog.get("username") else "Нет username"
        
        await callback.message.edit_text(
            f"👤 <b>{dialog['user_name']}</b>\n"
            f"📱 {dialog['user_phone']}\n"
            f"🔗 {username_text}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💬 Ответить", callback_data=f"reply_dialog_{dialog_id}")],
                [InlineKeyboardButton(text="❌ Закрыть", callback_data=f"close_dialog_{dialog_id}")]
            ])
        )
        await callback.answer()
    else:
        await callback.answer("❌ Не удалось принять диалог", show_alert=True)


# Обработка ответа в диалог
@dp.callback_query(F.data.startswith("reply_dialog_"))
async def handle_reply_dialog(callback: CallbackQuery, state: FSMContext):
    if not is_admin_or_operator(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    dialog_id = callback.data.replace("reply_dialog_", "")
    
    # Проверяем, не отвечает ли оператор уже в этом диалоге
    current_state = await state.get_state()
    if current_state == OperatorStates.replying_to_dialog:
        data = await state.get_data()
        current_dialog_id = data.get("dialog_id")
        if current_dialog_id == dialog_id:
            await callback.answer("💬 Вы уже отвечаете в этом диалоге. Просто напишите сообщение.", show_alert=True)
            return
    
    # Проверяем диалог
    dialogs_data = await load_dialogs()
    dialog = dialogs_data["dialogs"].get(dialog_id)
    
    if not dialog or dialog["status"] not in ["active", "pending"]:
        await callback.answer("❌ Диалог не найден", show_alert=True)
        return
    
    # Если диалог pending, автоматически принимаем его за этого оператора
    if dialog["status"] == "pending":
        await accept_dialog(dialog_id, callback.from_user.id)
        dialogs_data = await load_dialogs()
        dialog = dialogs_data["dialogs"].get(dialog_id)
    
    # Проверяем права доступа
    if dialog["operator_id"] != callback.from_user.id and not is_admin(callback.from_user.id):
        await callback.answer("❌ Это не ваш диалог", show_alert=True)
        return
    
    # Проверяем, не отвечает ли оператор уже в этом диалоге
    current_state = await state.get_state()
    if current_state == OperatorStates.replying_to_dialog:
        data = await state.get_data()
        current_dialog_id = data.get("dialog_id")
        if current_dialog_id == dialog_id:
            await callback.answer("💬 Вы уже отвечаете в этом диалоге. Просто напишите сообщение.", show_alert=True)
            return
    
    await state.set_state(OperatorStates.replying_to_dialog)
    await state.update_data(dialog_id=dialog_id)
    
    username_text = f"@{dialog['username']}" if dialog.get("username") else "нет"
    
    await callback.message.answer(
        f"💬 Отправьте ответ для диалога с <b>{dialog['user_name']}</b> ({username_text}):",
        parse_mode="HTML"
    )
    await callback.answer()


# Обработка кнопки "Список диалогов" для оператора
@dp.callback_query(F.data == "operator_dialogs")
async def handle_operator_dialogs(callback: CallbackQuery, state: FSMContext):
    if not is_admin_or_operator(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    await callback.answer()
    
    operator_id = callback.from_user.id
    await state.clear()
    
    # Получаем активные диалоги оператора
    active_dialogs = await get_active_dialogs_for_operator(operator_id)
    
    # Получаем ожидающие диалоги (если есть)
    pending_dialogs = await get_pending_dialogs()
    
    if not active_dialogs and not pending_dialogs:
        await callback.message.answer("📭 Активных диалогов нет.")
        return
    
    response_text = "💬 <b>Список диалогов</b>\n\n"
    
    if pending_dialogs:
        response_text += "⏳ <b>Ожидающие диалоги:</b>\n"
        for dialog_id, dialog in pending_dialogs:
            username_text = f"@{dialog['username']}" if dialog.get("username") else "нет"
            response_text += f"\n🔔 <b>{dialog['user_name']}</b>\n"
            response_text += f"📱 {dialog['user_phone']}\n"
            response_text += f"🔗 {username_text}\n"
            response_text += f"⏰ {dialog['created_at']}\n"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Принять диалог", callback_data=f"accept_dialog_{dialog_id}")]
            ])
            await callback.message.answer(response_text, parse_mode="HTML", reply_markup=keyboard)
            response_text = ""  # Очищаем для следующего диалога
    
    if active_dialogs:
        response_text += "\n📞 <b>Активные диалоги:</b>\n"
        for dialog_id, dialog in active_dialogs:
            username_text = f"@{dialog['username']}" if dialog.get("username") else "нет"
            response_text += f"\n👤 <b>{dialog['user_name']}</b>\n"
            response_text += f"📱 {dialog['user_phone']}\n"
            response_text += f"🔗 {username_text}\n"
            response_text += f"⏰ Принят: {dialog.get('accepted_at', 'N/A')}\n"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💬 Ответить", callback_data=f"reply_dialog_{dialog_id}")],
                [InlineKeyboardButton(text="❌ Закрыть", callback_data=f"close_dialog_{dialog_id}")]
            ])
            await callback.message.answer(response_text, parse_mode="HTML", reply_markup=keyboard)
            response_text = ""  # Очищаем для следующего диалога


# Обработка закрытия диалога
@dp.callback_query(F.data.startswith("close_dialog_"))
async def handle_close_dialog(callback: CallbackQuery, state: FSMContext):
    if not is_admin_or_operator(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    dialog_id = callback.data.replace("close_dialog_", "")
    
    # Проверяем, что диалог активен
    dialogs_data = await load_dialogs()
    dialog = dialogs_data["dialogs"].get(dialog_id)
    
    if not dialog or dialog["status"] != "active":
        await callback.answer("❌ Диалог не найден или не активен", show_alert=True)
        return
    
    if dialog["operator_id"] != callback.from_user.id and not is_admin(callback.from_user.id):
        await callback.answer("❌ Это не ваш диалог", show_alert=True)
        return
    
    success = await close_dialog(dialog_id)
    
    if success:
        user_id = dialog["user_id"]
        
        # Уведомляем пользователя
        await bot.send_message(
            chat_id=user_id,
            text="ℹ️ Диалог с оператором завершён. Если у вас возникнут дополнительные вопросы, вы можете создать новый диалог."
        )
        
        await callback.message.edit_text(
            f"❌ Диалог закрыт\n\n"
            f"👤 Пользователь: {dialog['user_name']}\n"
            f"📱 Телефон: {dialog['user_phone']}"
        )
        await callback.answer("✅ Диалог закрыт")
    else:
        await callback.answer("❌ Не удалось закрыть диалог", show_alert=True)


# Команда /reply для ответа оператора
@dp.message(Command("reply"))
async def cmd_reply(message: Message, state: FSMContext):
    if not is_admin_or_operator(message.from_user.id):
        await message.answer("❌ У вас нет доступа к этой команде.")
        return
    
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("❌ Использование: /reply <dialog_id> <текст ответа>")
        return
    
    dialog_id = args[1]
    reply_text = args[2]
    
    # Проверяем диалог
    dialogs_data = await load_dialogs()
    dialog = dialogs_data["dialogs"].get(dialog_id)
    
    if not dialog or dialog["status"] != "active":
        await message.answer("❌ Диалог не найден или не активен.")
        return
    
    if dialog["operator_id"] != message.from_user.id and not is_admin(message.from_user.id):
        await message.answer("❌ Это не ваш диалог.")
        return
    
    # Отправляем ответ пользователю
    user_id = dialog["user_id"]
    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"💬 <b>Ответ от оператора:</b>\n\n{reply_text}",
            parse_mode="HTML"
        )
        
        # Добавляем сообщение в диалог
        await add_message_to_dialog(dialog_id, "operator", reply_text)
        
        await message.answer(f"✅ Ответ отправлен пользователю {dialog['user_name']}")
    except Exception as e:
        await message.answer(f"❌ Ошибка при отправке: {e}")


# Команда /close для закрытия диалога
@dp.message(Command("close"))
async def cmd_close(message: Message, state: FSMContext):
    if not is_admin_or_operator(message.from_user.id):
        await message.answer("❌ У вас нет доступа к этой команде.")
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❌ Использование: /close <dialog_id>")
        return
    
    dialog_id = args[1]
    
    dialogs_data = await load_dialogs()
    dialog = dialogs_data["dialogs"].get(dialog_id)
    
    if not dialog or dialog["status"] != "active":
        await message.answer("❌ Диалог не найден или не активен.")
        return
    
    if dialog["operator_id"] != message.from_user.id and not is_admin(message.from_user.id):
        await message.answer("❌ Это не ваш диалог.")
        return
    
    success = await close_dialog(dialog_id)
    
    if success:
        user_id = dialog["user_id"]
        await bot.send_message(
            chat_id=user_id,
            text="ℹ️ Диалог с оператором завершён. Если у вас возникнут дополнительные вопросы, вы можете создать новый диалог."
        )
        await message.answer(f"✅ Диалог с {dialog['user_name']} закрыт.")
    else:
        await message.answer("❌ Не удалось закрыть диалог.")


# Обработка ответа оператора в состоянии replying_to_dialog
@dp.message(OperatorStates.replying_to_dialog)
async def handle_operator_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    dialog_id = data.get("dialog_id")
    
    if not dialog_id:
        await message.answer("❌ Ошибка: не найден ID диалога.")
        await state.clear()
        return
    
    # Проверяем диалог
    dialogs_data = await load_dialogs()
    dialog = dialogs_data["dialogs"].get(dialog_id)
    
    if not dialog or dialog["status"] not in ["active", "pending"]:
        await message.answer("❌ Диалог не найден.")
        await state.clear()
        return
    
    # Если диалог pending, автоматически принимаем его за этого оператора
    if dialog["status"] == "pending":
        await accept_dialog(dialog_id, message.from_user.id)
        dialogs_data = await load_dialogs()
        dialog = dialogs_data["dialogs"].get(dialog_id)
    
    # Проверяем права доступа
    if dialog["operator_id"] != message.from_user.id and not is_admin(message.from_user.id):
        await message.answer("❌ Это не ваш диалог.")
        await state.clear()
        return
    
    # Отправляем ответ пользователю
    user_id = dialog["user_id"]
    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"💬 <b>Ответ от оператора:</b>\n\n{message.text}",
            parse_mode="HTML"
        )
        
        # Добавляем сообщение в диалог
        await add_message_to_dialog(dialog_id, "operator", message.text)
        
        # Добавляем кнопки для продолжения диалога
        try:
            await message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💬 Ответить снова", callback_data=f"reply_dialog_{dialog_id}")],
                    [InlineKeyboardButton(text="📋 Список диалогов", callback_data="operator_dialogs")]
                ])
            )
        except:
            # Если не удалось отредактировать, отправляем новое сообщение с кнопками
            await message.answer(
                "💬",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💬 Ответить снова", callback_data=f"reply_dialog_{dialog_id}")],
                    [InlineKeyboardButton(text="📋 Список диалогов", callback_data="operator_dialogs")]
                ])
            )
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка при отправке: {e}")
        await state.clear()


# Обработка сообщений пользователя - пересылка оператору при активном или ожидающем диалоге
@dp.message(UserStates.in_dialog)
async def handle_user_message_in_dialog(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    dialog_id = data.get("dialog_id")
    
    # Получаем диалог (активный или ожидающий)
    if not dialog_id:
        active_dialog_id = await get_user_active_dialog(user_id)
        if active_dialog_id:
            dialog_id = active_dialog_id
            await state.update_data(dialog_id=dialog_id)
        else:
            await state.set_state(None)
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💬 Чат с оператором", callback_data="chat_operator")],
                [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_menu")]
            ])
            await message.answer("❌ Диалог не найден.", reply_markup=keyboard)
            return
    
    dialogs_data = await load_dialogs()
    dialog = dialogs_data["dialogs"].get(dialog_id)
    
    if not dialog or dialog["status"] not in ["active", "pending"]:
        await state.set_state(None)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💬 Чат с оператором", callback_data="chat_operator")],
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_menu")]
        ])
        await message.answer("❌ Диалог не найден.", reply_markup=keyboard)
        return
    
    # Добавляем сообщение в диалог
    await add_message_to_dialog(dialog_id, "user", message.text)
    
    # Если диалог pending, отправляем оператору
    if dialog["status"] == "pending":
        username_text = f"@{dialog['username']}" if dialog.get("username") else "нет"
        message_text = f"💬 <b>Сообщение от {dialog['user_name']}</b> ({username_text})\n\n"
        message_text += f"📱 {dialog['user_phone']}\n\n"
        message_text += f"{message.text}"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💬 Ответить", callback_data=f"reply_dialog_{dialog_id}")]
        ])
        
        # Отправляем всем операторам
        for operator_id in OPERATOR_IDS:
            try:
                await bot.send_message(
                    chat_id=operator_id,
                    text=message_text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            except Exception as e:
                print(f"[DIALOG ERROR] Ошибка отправки оператору {operator_id}: {e}")
    else:
        # Диалог активен, отправляем назначенному оператору
        operator_id = dialog["operator_id"]
        try:
            username_text = f"@{dialog['username']}" if dialog.get("username") else "нет"
            message_text = f"💬 <b>Сообщение от {dialog['user_name']}</b> ({username_text})\n\n"
            message_text += f"📱 {dialog['user_phone']}\n\n"
            message_text += f"{message.text}"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💬 Ответить", callback_data=f"reply_dialog_{dialog_id}")],
                [InlineKeyboardButton(text="❌ Закрыть", callback_data=f"close_dialog_{dialog_id}")]
            ])
            
            await bot.send_message(
                chat_id=operator_id,
                text=message_text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        except Exception as e:
            print(f"[DIALOG ERROR] Ошибка при отправке сообщения оператору: {e}")


# Обработка кнопки "Продолжить диалог"
@dp.callback_query(F.data == "continue_dialog")
async def handle_continue_dialog(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    active_dialog_id = await get_user_active_dialog(user_id)
    
    if not active_dialog_id:
        await callback.message.answer("❌ Диалог не найден.")
        return
    
    # Переводим пользователя в состояние диалога
    await state.set_state(UserStates.in_dialog)
    await state.update_data(dialog_id=active_dialog_id)
    
    dialogs_data = await load_dialogs()
    dialog = dialogs_data["dialogs"].get(active_dialog_id)
    status_text = "активен" if dialog and dialog.get("status") == "active" else "ожидает ответа"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить диалог", callback_data=f"cancel_user_dialog_{active_dialog_id}")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_menu")]
    ])
    
    await callback.message.answer(
        f"💬 Диалог с оператором ({status_text}).\n\n"
        f"Напишите ваше сообщение:",
        reply_markup=keyboard
    )


# Обработка отмены диалога пользователем
@dp.callback_query(F.data.startswith("cancel_user_dialog_"))
async def handle_cancel_user_dialog(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    dialog_id = callback.data.replace("cancel_user_dialog_", "")
    
    dialogs_data = await load_dialogs()
    dialog = dialogs_data["dialogs"].get(dialog_id)
    
    if not dialog:
        await callback.message.answer("❌ Диалог не найден.")
        return
    
    if dialog["user_id"] != callback.from_user.id:
        await callback.message.answer("❌ Это не ваш диалог.")
        return
    
    # Закрываем диалог
    success = await close_dialog(dialog_id)
    
    if success:
        await state.set_state(None)
        await state.update_data(dialog_id=None)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_menu")]
        ])
        
        await callback.message.answer("✅ Диалог отменён.", reply_markup=keyboard)
    else:
        await callback.message.answer("❌ Не удалось отменить диалог.")


# Обработка сообщений пользователя вне диалога (обычные сообщения, не команды и не в состоянии диалога)
async def is_not_command(message: Message) -> bool:
    """Проверяет, что сообщение не является командой"""
    return message.text is not None and not message.text.startswith("/")

@dp.message(is_not_command)
async def handle_regular_message(message: Message, state: FSMContext):
    # Пропускаем обработку для операторов и админов
    if is_admin_or_operator(message.from_user.id):
        return
    
    # Пропускаем обработку, если пользователь в диалоге (обрабатывается выше)
    current_state = await state.get_state()
    if current_state == UserStates.in_dialog:
        return
    
    # Проверяем, есть ли активный диалог
    user_id = message.from_user.id
    active_dialog_id = await get_user_active_dialog(user_id)
    
    if active_dialog_id:
        # Если есть активный диалог, переводим пользователя в состояние диалога
        await state.set_state(UserStates.in_dialog)
        await state.update_data(dialog_id=active_dialog_id)
        # Передаем обработку в handle_user_message_in_dialog
        await handle_user_message_in_dialog(message, state)
        return
    
    # Иначе просто игнорируем сообщение
    pass




async def main():
    # Инициализация файлов, если их нет
    texts = await load_texts()
    if not texts:
        await save_texts({
            "welcome_message": 
                "👋 Добро пожаловать, {name}!\n\n✨ Мы рады приветствовать вас в нашем сервисе!\n\n🏢 Наша организация специализируется на оказании профессиональных услуг в сфере миграционного права и документооборота.\n\n📋 Ниже представлен полный перечень услуг, которые мы предоставляем:\n\n📌 РВП — разрешение на временное проживание\n📌 ВНЖ — Вид на жительство\n📌 Гражданство Российской Федерации\n📌 Временная или постоянная регистрация\n📌 Миграционный учёт\n📌 Гражданско-правовой договор (ГПХ) / трудовой договор\n📌 Декларация физического лица (3-НДФЛ)\n📌 Перевод документов\n📌 Договор найма / безвозмездного пользования жилым помещением\n📌 Договор купли-продажи автомобиля / договор аренды\n📌 Уведомление о проживании\n📌 Уведомление о заключении договора ГПХ\n📌 Уведомление о расторжении договора ГПХ\n\n💼 Для получения подробной информации выберите интересующую услугу из меню ниже.",
            "service_rvp": 
                "📌 РВП — разрешение на временное проживание\n(мужчины — только через контракт)\n\nДля заполнения заявления потребуется:\n• Паспорт + перевод всех страниц\n• Свидетельство о рождении (своё)\n• Свидетельство о рождении\nсына / дочери / матери / отца — по основанию подачи\n• Свидетельство о браке\n• Регистрация и миграционный учёт\n• Миграционная карта\n• Медицинские справки\n• ИНН\n• Фото 3,5 × 4,5 см\n• Паспорт родственника\n(отца / матери / сына / дочери / супруга — по основанию)\n• Госпошлина",
            "service_vnzh": 
                "📌 ВНЖ — Вид на жительство\n(мужчины — только через контракт)\n\nДля заполнения заявления потребуется:\n• Паспорт + перевод всех страниц\n• Свидетельство о рождении (своё)\n• Свидетельство о рождении\nсына / дочери / матери / отца — по основанию подачи\n• Свидетельство о браке\n• Регистрация и миграционный учёт\n• Миграционная карта\n• Медицинские справки\n• ИНН\n• Фото 3,5 × 4,5 см\n• Паспорт родственника\n(отца / матери / сына / дочери / супруга — по основанию)\n• Госпошлина\n\nДополнительно необходимо предоставить:\n• Сведения об учёбе и работе / доходах за последние 3 года\n• Где проживали, чем занимались, куда переезжали\n• Информацию о родственниках\n(образец / бланк предоставляем)\n• Данные о родственниках:\nФИО, дата и место рождения, гражданство,\nадрес регистрации / проживания, род занятий\n(работает, учится, пенсионер, не работает)\n\nДля работающих:\n• Трудовой договор\n• При работе по патенту — патент + чеки",
            "service_citizenship": 
                "📌 Гражданство Российской Федерации\n(мужчины — только через контракт)\n\nДля заполнения заявления потребуется:\n• Паспорт + перевод всех страниц\n• Свидетельство о рождении (своё)\n• Свидетельство о рождении\nсына / дочери / матери / отца — по основанию подачи\n• Свидетельство о браке\n(о разводе / о смерти — при наличии)\n• Регистрация и миграционный учёт\n• ИНН\n• Фото 3 × 4 см\n• Паспорт родственника\n(отца / матери / сына / дочери / супруга — по основанию)\n• Госпошлина\n\nДополнительно необходимо предоставить:\n• Сведения об учёбе и работе / доходах за последние 5 лет\n• Где проживали, чем занимались, куда переезжали\n• Информацию о родственниках\n(образец / бланк предоставляем)\n• Данные о родственниках:\nФИО, дата и место рождения, гражданство,\nадрес регистрации / проживания, род занятий\n(работает, учится, пенсионер, не работает)\n\nДля работающих:\n• Трудовой договор",
            "service_registration": 
                "📌 Временная или постоянная регистрация\nпо ВНЖ или РВП\n\nРегистрация оформляется:\n• с печатью в ВНЖ\n• или в паспорт — при наличии РВП\n\nДля оформления потребуется:\n\n1️⃣ Документы заявителя:\n• Паспорт + ВНЖ или РВП\n\n2️⃣ Сведения о регистрации:\n• Информация о предыдущих регистрациях\n(миграционный учёт не учитывается)\n• При первой регистрации в РФ —\nадрес регистрации по месту жительства в другой стране\n\n3️⃣ Документы на жилое помещение:\n• Собственное жильё — выписка из ЕГРН\n• Жильё в найме — договор найма\n\n✍️ При необходимости можем оформить договор найма.\nДля этого потребуется:\n• Паспортные данные всех собственников\n• Выписка из ЕГРН или свидетельство\n(достаточно реквизитов для заполнения)",
            "service_migration_account": 
                "📋 Ниже представлен полный перечень услуг, которые мы предоставляем:\n\n📌 Миграционный учёт\n📌 Продление миграционного учёта по браку\n📌 Оформление на основании отца / матери\n\n💼 Для получения подробной информации выберите интересующую услугу из меню ниже.",
            "service_migration_account_main": 
                "📌 Миграционный учёт\n\nДля постановки на миграционный учёт потребуется:\n\n🧑‍💼 От собственника жилья (принимающей стороны):\n• Паспорт с регистрацией\n(паспортные данные: ФИО, серия и номер, кем и когда выдан, адрес прописки)\n• Документ на недвижимость\n(выписка из ЕГРН)\n• Номер телефона\n\n🌍 От иностранного гражданина:\n• Паспорт — все страницы с отметками\n• Место рождения\n(страна, населённый пункт)\n• Номер телефона\n• Миграционная карта — с двух сторон\n• Патент — с двух сторон\n(или трудовой договор)\n• Все чеки по патенту\n• Карточка дактилоскопии\n(отпечатки пальцев — для всех старше 6 лет)",
            "service_migration_account_marriage": 
                "📌 Продление миграционного учёта по браку\n\nДля оформления потребуется:\n\n🌍 От иностранного гражданина:\n• Паспорт\n• Место рождения\n(страна, населённый пункт)\n• Номер телефона\n• Миграционная карта — с двух сторон\n• Свидетельство о браке\n• Медицинские справки и сопутствующие документы\n(для всех старше 6 лет)\n• Карточка дактилоскопии\n(отпечатки пальцев — для всех старше 6 лет)\n\n👫 От супруга / супруги:\n• Паспорт РФ или ВНЖ\n• Регистрация по месту жительства",
            "service_migration_account_parents": 
                "📌 Оформление на основании отца / матери\nдля ребёнка (сына или дочери)\n\nДля оформления потребуется:\n\n👶 От ребёнка:\n• Паспорт\n• Номер телефона\n• Миграционная карта\n• Свидетельство о рождении\n• Медицинские справки и сопутствующие документы\n• Карточка дактилоскопии\n(отпечатки пальцев — для всех старше 6 лет)\n\n👨‍👩‍👧 От отца / матери:\n• Паспорт РФ или ВНЖ\n• Регистрация по месту жительства\n• Номер телефона\n• Миграционная карта\n\nЕсли у отца / матери есть патент, дополнительно:\n• Патент\n• Все чеки по патенту\n\nТакже потребуется:\n• Место рождения\n(страна, населённый пункт)\n• Медицинские справки и сопутствующие документы\n• Карточка дактилоскопии\n(отпечатки пальцев — для всех старше 6 лет)",
            "service_declaration_3ndfl": 
                "📌 Декларация физического лица (3-НДФЛ)\n\nДля подготовки декларации потребуется:\n• Паспорт\n• ИНН\n• Номер телефона\n• Размер дохода\n\nЕсли требуется налоговый вычет на детей:\n• Даты рождения всех детей\n• Копии свидетельств о рождении\n(предоставляются в налоговую)",
            "service_translation": 
                "📌 Перевод документов\n\nДля выполнения перевода потребуется:\n• Фото или скан документа\n\nПри необходимости нотариального заверения:\n• Оригинал документа",
            "service_contracts": 
                "📋 Ниже представлен полный перечень услуг, которые мы предоставляем:\n\n📌 Гражданско-правовой договор (ГПХ) / трудовой договор\n📌 Договор найма / безвозмездного пользования жилым помещением\n📌 Договор купли-продажи автомобиля / договор аренды\n\n💼 Для получения подробной информации выберите интересующую услугу из меню ниже.",
            "service_contracts_gph": 
                "📌 Гражданско-правовой договор (ГПХ) / трудовой договор\n\nЗаключение договора включает:\n• Подготовку договора\n• Уведомления в госорганы\n• Описи документов\n• Конверты — 2 пакета документов\n\nДля оформления необходимо предоставить:\n\n👤 От заказчика:\n• Паспорт РФ + регистрация (прописка)\n• ИНН\n• Адрес места работы\n• Срок действия договора\n(дата окончания или бессрочно)\n• Размер вознаграждения:\n— почасовая оплата (XXX ₽/час)\n— или ежемесячная оплата (XXXXX ₽/мес)\n\n👷 От исполнителя (работника):\n• Паспорт\n• Патент\n• ИНН (если не указан в патенте)\n• Регистрация\n(прописка или миграционный учёт)\n• Медицинская страховка\n(полис ДМС)",
            "service_contracts_rent": 
                "📌 Договор найма / безвозмездного пользования жилым помещением\n\nДля подготовки договора потребуется:\n• Паспорта обеих сторон\n(или паспортные данные)\n• Выписка из ЕГРН\n• Номера телефонов сторон",
            "service_contracts_car": 
                "📌 Договор купли-продажи автомобиля / договор аренды\n\nВ услугу входит:\n• Подготовка договора\n• Заявление в ГИБДД\n(на постановку или снятие с учёта)\n\nДля оформления потребуется:\n• СТС\n• ПТС\n• Паспорта обеих сторон\n(или паспортные данные)\n• Номера телефонов сторон",
            "service_notifications": 
                "📋 Ниже представлен полный перечень услуг, которые мы предоставляем:\n\n📌 Уведомление о проживании\n📌 Уведомление о заключении договора ГПХ\n📌 Уведомление о расторжении договора ГПХ\n\n💼 Для получения подробной информации выберите интересующую услугу из меню ниже.",
            "service_notifications_residence": 
                "📌 Уведомление о проживании\nежегодная отметка по ВНЖ или РВП\n\nДля оформления потребуется:\n\n1️⃣ Документы:\n• Паспорт + ВНЖ или РВП\n\n2️⃣ Регистрация:\n• Регистрация по месту жительства\nили миграционный учёт\n\n3️⃣ Доход (для ВНЖ):\n• Размер дохода\n• При официальной работе —\nсправка о доходах, должность, адрес организации\n\n4️⃣ Выезды за границу:\n• Информация обо всех периодах выезда и въезда\nза отчётный год",
            "service_notifications_gph_conclusion": 
                "📌 Уведомление о заключении договора ГПХ\n\nДля оформления потребуется:\n\n👤 От заказчика:\n• Паспорта обеих сторон\n(или паспортные данные)\n• ИНН заказчика\n• Номер телефона заказчика\n• Профессия исполнителя\n• Адрес места работы\n• Патент исполнителя\n\n👷 От исполнителя (с патентом):\n• Паспорт (паспортные данные)\n• Патент\n• Медицинский полис\n(страховка)\n• ИНН (если не указан в патенте)\n• Номер телефона\n• Адрес места работы",
            "service_notifications_gph_termination": 
                "📌 Уведомление о расторжении договора ГПХ\n\nДля оформления потребуется:\n• Паспорта обеих сторон\n(или паспортные данные)\n• ИНН заказчика\n• Номер телефона заказчика\n• Профессия исполнителя\n• Адрес места работы\n• Патент исполнителя\n• Дата расторжения договора",
            "service_contacts": 
                "📞 Контакты\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n📞 Помощь в заполнении бланков:\n\n📱 +7-950-415-8179\n👤 Олег\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n💬 Мы всегда готовы помочь вам с любыми вопросами!"
        })
    else:
        # Проверяем и добавляем тексты для услуг, если их нет
        updated = False
        if "service_rvp" not in texts:
            texts["service_rvp"] = "📌 РВП — разрешение на временное проживание\n(мужчины — только через контракт)\n\nДля заполнения заявления потребуется:\n• Паспорт + перевод всех страниц\n• Свидетельство о рождении (своё)\n• Свидетельство о рождении\nсына / дочери / матери / отца — по основанию подачи\n• Свидетельство о браке\n• Регистрация и миграционный учёт\n• Миграционная карта\n• Медицинские справки\n• ИНН\n• Фото 3,5 × 4,5 см\n• Паспорт родственника\n(отца / матери / сына / дочери / супруга — по основанию)\n• Госпошлина"
            updated = True
        
        if "service_vnzh" not in texts:
            texts["service_vnzh"] = "📌 ВНЖ — Вид на жительство\n(мужчины — только через контракт)\n\nДля заполнения заявления потребуется:\n• Паспорт + перевод всех страниц\n• Свидетельство о рождении (своё)\n• Свидетельство о рождении\nсына / дочери / матери / отца — по основанию подачи\n• Свидетельство о браке\n• Регистрация и миграционный учёт\n• Миграционная карта\n• Медицинские справки\n• ИНН\n• Фото 3,5 × 4,5 см\n• Паспорт родственника\n(отца / матери / сына / дочери / супруга — по основанию)\n• Госпошлина\n\nДополнительно необходимо предоставить:\n• Сведения об учёбе и работе / доходах за последние 3 года\n• Где проживали, чем занимались, куда переезжали\n• Информацию о родственниках\n(образец / бланк предоставляем)\n• Данные о родственниках:\nФИО, дата и место рождения, гражданство,\nадрес регистрации / проживания, род занятий\n(работает, учится, пенсионер, не работает)\n\nДля работающих:\n• Трудовой договор\n• При работе по патенту — патент + чеки"
            updated = True
        
        if "service_citizenship" not in texts:
            texts["service_citizenship"] = "📌 Гражданство Российской Федерации\n(мужчины — только через контракт)\n\nДля заполнения заявления потребуется:\n• Паспорт + перевод всех страниц\n• Свидетельство о рождении (своё)\n• Свидетельство о рождении\nсына / дочери / матери / отца — по основанию подачи\n• Свидетельство о браке\n(о разводе / о смерти — при наличии)\n• Регистрация и миграционный учёт\n• ИНН\n• Фото 3 × 4 см\n• Паспорт родственника\n(отца / матери / сына / дочери / супруга — по основанию)\n• Госпошлина\n\nДополнительно необходимо предоставить:\n• Сведения об учёбе и работе / доходах за последние 5 лет\n• Где проживали, чем занимались, куда переезжали\n• Информацию о родственниках\n(образец / бланк предоставляем)\n• Данные о родственниках:\nФИО, дата и место рождения, гражданство,\nадрес регистрации / проживания, род занятий\n(работает, учится, пенсионер, не работает)\n\nДля работающих:\n• Трудовой договор"
            updated = True
        
        if "service_registration" not in texts:
            texts["service_registration"] = "📌 Временная или постоянная регистрация\nпо ВНЖ или РВП\n\nРегистрация оформляется:\n• с печатью в ВНЖ\n• или в паспорт — при наличии РВП\n\nДля оформления потребуется:\n\n1️⃣ Документы заявителя:\n• Паспорт + ВНЖ или РВП\n\n2️⃣ Сведения о регистрации:\n• Информация о предыдущих регистрациях\n(миграционный учёт не учитывается)\n• При первой регистрации в РФ —\nадрес регистрации по месту жительства в другой стране\n\n3️⃣ Документы на жилое помещение:\n• Собственное жильё — выписка из ЕГРН\n• Жильё в найме — договор найма\n\n✍️ При необходимости можем оформить договор найма.\nДля этого потребуется:\n• Паспортные данные всех собственников\n• Выписка из ЕГРН или свидетельство\n(достаточно реквизитов для заполнения)"
            updated = True
        
        if "service_migration_account" not in texts:
            texts["service_migration_account"] = "📋 Ниже представлен полный перечень услуг, которые мы предоставляем:\n\n📌 Миграционный учёт\n📌 Продление миграционного учёта по браку\n📌 Оформление на основании отца / матери\n\n💼 Для получения подробной информации выберите интересующую услугу из меню ниже."
            updated = True
        
        if "service_migration_account_main" not in texts:
            texts["service_migration_account_main"] = "📌 Миграционный учёт\n\nДля постановки на миграционный учёт потребуется:\n\n🧑‍💼 От собственника жилья (принимающей стороны):\n• Паспорт с регистрацией\n(паспортные данные: ФИО, серия и номер, кем и когда выдан, адрес прописки)\n• Документ на недвижимость\n(выписка из ЕГРН)\n• Номер телефона\n\n🌍 От иностранного гражданина:\n• Паспорт — все страницы с отметками\n• Место рождения\n(страна, населённый пункт)\n• Номер телефона\n• Миграционная карта — с двух сторон\n• Патент — с двух сторон\n(или трудовой договор)\n• Все чеки по патенту\n• Карточка дактилоскопии\n(отпечатки пальцев — для всех старше 6 лет)"
            updated = True
        
        if "service_migration_account_marriage" not in texts:
            texts["service_migration_account_marriage"] = "📌 Продление миграционного учёта по браку\n\nДля оформления потребуется:\n\n🌍 От иностранного гражданина:\n• Паспорт\n• Место рождения\n(страна, населённый пункт)\n• Номер телефона\n• Миграционная карта — с двух сторон\n• Свидетельство о браке\n• Медицинские справки и сопутствующие документы\n(для всех старше 6 лет)\n• Карточка дактилоскопии\n(отпечатки пальцев — для всех старше 6 лет)\n\n👫 От супруга / супруги:\n• Паспорт РФ или ВНЖ\n• Регистрация по месту жительства"
            updated = True
        
        if "service_migration_account_parents" not in texts:
            texts["service_migration_account_parents"] = "📌 Оформление на основании отца / матери\nдля ребёнка (сына или дочери)\n\nДля оформления потребуется:\n\n👶 От ребёнка:\n• Паспорт\n• Номер телефона\n• Миграционная карта\n• Свидетельство о рождении\n• Медицинские справки и сопутствующие документы\n• Карточка дактилоскопии\n(отпечатки пальцев — для всех старше 6 лет)\n\n👨‍👩‍👧 От отца / матери:\n• Паспорт РФ или ВНЖ\n• Регистрация по месту жительства\n• Номер телефона\n• Миграционная карта\n\nЕсли у отца / матери есть патент, дополнительно:\n• Патент\n• Все чеки по патенту\n\nТакже потребуется:\n• Место рождения\n(страна, населённый пункт)\n• Медицинские справки и сопутствующие документы\n• Карточка дактилоскопии\n(отпечатки пальцев — для всех старше 6 лет)"
            updated = True
        
        if "service_declaration_3ndfl" not in texts:
            texts["service_declaration_3ndfl"] = "📌 Декларация физического лица (3-НДФЛ)\n\nДля подготовки декларации потребуется:\n• Паспорт\n• ИНН\n• Номер телефона\n• Размер дохода\n\nЕсли требуется налоговый вычет на детей:\n• Даты рождения всех детей\n• Копии свидетельств о рождении\n(предоставляются в налоговую)"
            updated = True
        
        if "service_translation" not in texts:
            texts["service_translation"] = "📌 Перевод документов\n\nДля выполнения перевода потребуется:\n• Фото или скан документа\n\nПри необходимости нотариального заверения:\n• Оригинал документа"
            updated = True
        
        if "service_contracts" not in texts:
            texts["service_contracts"] = "📋 Ниже представлен полный перечень услуг, которые мы предоставляем:\n\n📌 Гражданско-правовой договор (ГПХ) / трудовой договор\n📌 Договор найма / безвозмездного пользования жилым помещением\n📌 Договор купли-продажи автомобиля / договор аренды\n\n💼 Для получения подробной информации выберите интересующую услугу из меню ниже."
            updated = True
        
        if "service_contracts_gph" not in texts:
            texts["service_contracts_gph"] = "📌 Гражданско-правовой договор (ГПХ) / трудовой договор\n\nЗаключение договора включает:\n• Подготовку договора\n• Уведомления в госорганы\n• Описи документов\n• Конверты — 2 пакета документов\n\nДля оформления необходимо предоставить:\n\n👤 От заказчика:\n• Паспорт РФ + регистрация (прописка)\n• ИНН\n• Адрес места работы\n• Срок действия договора\n(дата окончания или бессрочно)\n• Размер вознаграждения:\n— почасовая оплата (XXX ₽/час)\n— или ежемесячная оплата (XXXXX ₽/мес)\n\n👷 От исполнителя (работника):\n• Паспорт\n• Патент\n• ИНН (если не указан в патенте)\n• Регистрация\n(прописка или миграционный учёт)\n• Медицинская страховка\n(полис ДМС)"
            updated = True
        
        if "service_contracts_rent" not in texts:
            texts["service_contracts_rent"] = "📌 Договор найма / безвозмездного пользования жилым помещением\n\nДля подготовки договора потребуется:\n• Паспорта обеих сторон\n(или паспортные данные)\n• Выписка из ЕГРН\n• Номера телефонов сторон"
            updated = True
        
        if "service_contracts_car" not in texts:
            texts["service_contracts_car"] = "📌 Договор купли-продажи автомобиля / договор аренды\n\nВ услугу входит:\n• Подготовка договора\n• Заявление в ГИБДД\n(на постановку или снятие с учёта)\n\nДля оформления потребуется:\n• СТС\n• ПТС\n• Паспорта обеих сторон\n(или паспортные данные)\n• Номера телефонов сторон"
            updated = True
        
        if "service_notifications" not in texts:
            texts["service_notifications"] = "📋 Ниже представлен полный перечень услуг, которые мы предоставляем:\n\n📌 Уведомление о проживании\n📌 Уведомление о заключении договора ГПХ\n📌 Уведомление о расторжении договора ГПХ\n\n💼 Для получения подробной информации выберите интересующую услугу из меню ниже."
            updated = True
        
        if "service_notifications_residence" not in texts:
            texts["service_notifications_residence"] = "📌 Уведомление о проживании\nежегодная отметка по ВНЖ или РВП\n\nДля оформления потребуется:\n\n1️⃣ Документы:\n• Паспорт + ВНЖ или РВП\n\n2️⃣ Регистрация:\n• Регистрация по месту жительства\nили миграционный учёт\n\n3️⃣ Доход (для ВНЖ):\n• Размер дохода\n• При официальной работе —\nсправка о доходах, должность, адрес организации\n\n4️⃣ Выезды за границу:\n• Информация обо всех периодах выезда и въезда\nза отчётный год"
            updated = True
        
        if "service_notifications_gph_conclusion" not in texts:
            texts["service_notifications_gph_conclusion"] = "📌 Уведомление о заключении договора ГПХ\n\nДля оформления потребуется:\n\n👤 От заказчика:\n• Паспорта обеих сторон\n(или паспортные данные)\n• ИНН заказчика\n• Номер телефона заказчика\n• Профессия исполнителя\n• Адрес места работы\n• Патент исполнителя\n\n👷 От исполнителя (с патентом):\n• Паспорт (паспортные данные)\n• Патент\n• Медицинский полис\n(страховка)\n• ИНН (если не указан в патенте)\n• Номер телефона\n• Адрес места работы"
            updated = True
        
        if "service_notifications_gph_termination" not in texts:
            texts["service_notifications_gph_termination"] = "📌 Уведомление о расторжении договора ГПХ\n\nДля оформления потребуется:\n• Паспорта обеих сторон\n(или паспортные данные)\n• ИНН заказчика\n• Номер телефона заказчика\n• Профессия исполнителя\n• Адрес места работы\n• Патент исполнителя\n• Дата расторжения договора"
            updated = True
        
        if "service_contacts" not in texts:
            texts["service_contacts"] = "📞 Контакты\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n📞 Помощь в заполнении бланков:\n\n📱 +7-950-415-8179\n👤 Олег\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n💬 Мы всегда готовы помочь вам с любыми вопросами!"
            updated = True
        
        if updated:
            await save_texts(texts)
    
    buttons = await load_buttons()
    if not buttons:
        await save_buttons({"main_menu": [
            ["РВП", "ВНЖ", "Гражданство"],
            ["Регистрация", "Миграционный учёт"],
            ["Декларация (3-НДФЛ)", "Перевод документов"],
            ["Договоры", "Уведомления"],
            ["Контакты"]
        ]})
    
    print("Бот запущен!")
    try:
        await dp.start_polling(bot, skip_updates=True)
    except KeyboardInterrupt:
        print("Бот остановлен пользователем")
    except Exception as e:
        print(f"Ошибка при запуске бота: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            await bot.session.close()
        except:
            pass


if __name__ == "__main__":
    asyncio.run(main())
