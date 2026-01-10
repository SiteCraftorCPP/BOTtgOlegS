# Чеклист для деплоя на VPS

## Перед пушем в репозиторий

- [x] Обновлен `config.py` для использования переменных окружения
- [x] Создан `.env.example` с примерами переменных
- [x] Обновлен `.gitignore` (исключены `.env`, `data/`, логи)
- [x] Создан `start.sh` для запуска
- [x] Создан `bot.service` для systemd
- [x] Обновлен `README.md` с инструкциями
- [x] Создан `DEPLOY.md` с подробными инструкциями

## На VPS нужно выполнить

1. **Клонировать репозиторий:**
   ```bash
   git clone <your_repo_url> BOTtgOlegS
   cd BOTtgOlegS
   ```

2. **Создать `.env` файл:**
   ```bash
   cp .env.example .env
   nano .env
   ```
   Заполнить реальными значениями:
   - BOT_TOKEN
   - ADMIN_ID
   - OPERATOR_ID
   - NOTIFICATION_CHAT_ID

3. **Установить зависимости:**
   ```bash
   pip3 install -r requirements.txt
   ```

4. **Настроить systemd (опционально):**
   ```bash
   sudo cp bot.service /etc/systemd/system/
   sudo nano /etc/systemd/system/bot.service  # Изменить пути
   sudo systemctl daemon-reload
   sudo systemctl enable bot.service
   sudo systemctl start bot.service
   ```

5. **Или запустить через screen:**
   ```bash
   screen -S bot
   python3 bot.py
   # Ctrl+A, затем D для отсоединения
   ```

## Важные файлы

- ✅ `bot.py` - основной файл бота
- ✅ `config.py` - конфигурация (использует .env)
- ✅ `requirements.txt` - зависимости
- ✅ `.env.example` - пример переменных окружения
- ✅ `.gitignore` - исключения для git
- ✅ `start.sh` - скрипт запуска
- ✅ `bot.service` - systemd service
- ✅ `README.md` - документация
- ✅ `DEPLOY.md` - инструкция по деплою

## Файлы, которые НЕ должны быть в репозитории

- ❌ `.env` - файл с реальными токенами
- ❌ `data/` - данные бота (создастся автоматически)
- ❌ `*.log` - логи
- ❌ `__pycache__/` - кэш Python
- ❌ `buttons.json` в корне (если есть)