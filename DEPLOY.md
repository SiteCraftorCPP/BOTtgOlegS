# Инструкция по деплою на VPS

## Быстрый старт

### 1. Подготовка сервера

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Python и pip
sudo apt install python3 python3-pip python3-venv -y

# Установка git (если нужно)
sudo apt install git -y
```

### 2. Клонирование проекта

```bash
cd /root  # или в другую директорию
git clone <your_repo_url> BOTtgOlegS
cd BOTtgOlegS
```

### 3. Настройка окружения

```bash
# Создание виртуального окружения (опционально)
python3 -m venv venv
source venv/bin/activate

# Установка зависимостей
pip3 install -r requirements.txt

# Создание .env файла
cp .env.example .env
nano .env
```

В файле `.env` укажите:
```
BOT_TOKEN=ваш_токен_бота
ADMIN_ID=6933111964
OPERATOR_ID=7600749840
NOTIFICATION_CHAT_ID=-1003591909192
```

### 4. Запуск через Systemd (рекомендуется)

```bash
# Редактируем service файл
sudo nano bot.service
# Измените пути WorkingDirectory и ExecStart на ваши

# Копируем service файл
sudo cp bot.service /etc/systemd/system/

# Перезагружаем systemd
sudo systemctl daemon-reload

# Включаем автозапуск
sudo systemctl enable bot.service

# Запускаем бота
sudo systemctl start bot.service

# Проверяем статус
sudo systemctl status bot.service
```

### 5. Управление ботом

```bash
# Запуск
sudo systemctl start bot.service

# Остановка
sudo systemctl stop bot.service

# Перезапуск
sudo systemctl restart bot.service

# Статус
sudo systemctl status bot.service

# Просмотр логов
sudo journalctl -u bot.service -f
```

### 6. Альтернативный способ - Screen

```bash
# Установка screen
sudo apt install screen -y

# Запуск бота в screen
screen -S bot
cd /root/BOTtgOlegS
python3 bot.py

# Отсоединение: Ctrl+A, затем D
# Возврат: screen -r bot
```

## Обновление бота

```bash
cd /root/BOTtgOlegS
git pull
sudo systemctl restart bot.service
```

## Проверка работы

1. Отправьте `/start` боту в Telegram
2. Проверьте логи: `sudo journalctl -u bot.service -n 50`
3. Проверьте, что бот отвечает на команды

## Решение проблем

### Бот не запускается
```bash
# Проверьте логи
sudo journalctl -u bot.service -n 100

# Проверьте .env файл
cat .env

# Проверьте права доступа
ls -la /root/BOTtgOlegS
```

### Ошибки с правами
```bash
sudo chown -R $USER:$USER /root/BOTtgOlegS
chmod +x start.sh
```

### Порт занят
```bash
# Проверьте процессы
ps aux | grep python

# Убейте старый процесс
sudo pkill -f bot.py
```