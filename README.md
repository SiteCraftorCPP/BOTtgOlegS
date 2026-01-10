# Telegram Bot - BOTtgOlegS

Telegram бот с админ-панелью для редактирования текстов и кнопок, системой диалогов с операторами.

## Установка на локальной машине

1. Клонируйте репозиторий:
```bash
git clone <repository_url>
cd BOTtgOlegS
```

2. Создайте виртуальное окружение (рекомендуется):
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Создайте файл `.env` на основе `.env.example`:
```bash
cp .env.example .env
```

5. Отредактируйте `.env` и укажите ваши данные:
```
BOT_TOKEN=your_bot_token_here
ADMIN_ID=6933111964
OPERATOR_ID=7600749840
NOTIFICATION_CHAT_ID=-1003591909192
```

6. Запустите бота:
```bash
python bot.py
```

## Установка на VPS (Linux)

### Способ 1: Systemd Service (рекомендуется)

1. Загрузите проект на VPS:
```bash
git clone <repository_url>
cd BOTtgOlegS
```

2. Установите зависимости:
```bash
pip3 install -r requirements.txt
```

3. Создайте файл `.env`:
```bash
cp .env.example .env
nano .env  # Отредактируйте файл
```

4. Скопируйте service файл:
```bash
sudo cp bot.service /etc/systemd/system/
```

5. Отредактируйте пути в `bot.service`:
```bash
sudo nano /etc/systemd/system/bot.service
# Измените WorkingDirectory и ExecStart на ваши пути
```

6. Запустите сервис:
```bash
sudo systemctl daemon-reload
sudo systemctl enable bot.service
sudo systemctl start bot.service
```

7. Проверьте статус:
```bash
sudo systemctl status bot.service
```

8. Просмотр логов:
```bash
sudo journalctl -u bot.service -f
```

### Способ 2: Screen/Tmux

1. Установите screen:
```bash
sudo apt install screen
```

2. Запустите бота в screen:
```bash
screen -S bot
cd /path/to/BOTtgOlegS
python3 bot.py
# Нажмите Ctrl+A, затем D для отсоединения
```

3. Вернуться к сессии:
```bash
screen -r bot
```

### Способ 3: Скрипт запуска

1. Сделайте скрипт исполняемым:
```bash
chmod +x start.sh
```

2. Запустите:
```bash
./start.sh
```

## Админка

Используйте команду `/admin` для доступа к панели управления.

**ID пользователей:**
- Админ ID: 6933111964
- Оператор ID: 7600749840

## Возможности

- Приветственное сообщение при старте бота
- Запрос номера телефона при первом запуске
- Админ-панель для редактирования текстов
- Админ-панель для редактирования кнопок меню
- Система диалогов с операторами
- Уведомления в канал о новых обращениях
- История диалогов
- Данные хранятся в JSON файлах в папке `data/`

## Структура проекта

```
BOTtgOlegS/
├── bot.py              # Основной файл бота
├── config.py           # Конфигурация
├── requirements.txt    # Зависимости
├── .env.example        # Пример файла с переменными окружения
├── .env                # Файл с переменными окружения (не в git)
├── .gitignore          # Игнорируемые файлы
├── start.sh            # Скрипт запуска
├── bot.service         # Systemd service файл
├── data/               # Данные бота
│   ├── texts.json      # Тексты услуг
│   ├── buttons.json    # Структура кнопок
│   ├── phones.json     # Номера телефонов пользователей
│   └── dialogs.json    # История диалогов
└── README.md           # Документация
```

## Команды для операторов

- `/dialogs` - Список активных и ожидающих диалогов
- `/reply <dialog_id> <текст>` - Ответить в диалог
- `/close <dialog_id>` - Закрыть диалог

## Безопасность

⚠️ **Важно:** Не коммитьте файл `.env` в репозиторий! Он уже добавлен в `.gitignore`.
