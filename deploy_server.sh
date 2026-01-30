#!/bin/bash

# Скрипт для автоматического развертывания проекта на сервере
# Использование: ./deploy_server.sh

set -e  # Останавливаем выполнение при любой ошибке

echo "Начинаю развертывание проекта SEO Tools..."

# Проверяем что мы в правильной директории
if [ ! -f "requirements.txt" ]; then
    echo "Ошибка: файл requirements.txt не найден. Убедитесь что вы в корневой директории проекта."
    exit 1
fi

# 1. Активируем виртуальное окружение
echo "Активирую виртуальное окружение..."
if [ ! -d "venv" ]; then
    echo "Создаю виртуальное окружение..."
    python3 -m venv venv
fi
source venv/bin/activate

# 2. Устанавливаем зависимости
echo "Устанавливаю зависимости..."
pip install --upgrade pip
pip install -r requirements.txt

# 3. Проверяем наличие .env файла
if [ ! -f ".env" ]; then
    echo "ОШИБКА: Файл .env не найден!"
    echo "Создайте файл .env с API ключами (ANTHROPIC_API_KEY, ARSENKIN_API_KEY и др.)"
    exit 1
else
    echo "Файл .env найден"
fi

# 4. Проверяем Google Sheets credentials
if [ ! -f "gsheets/credentials.json" ]; then
    echo "ОШИБКА: Файл gsheets/credentials.json не найден!"
    echo "Скопируйте credentials.json из Google Cloud Console"
    exit 1
else
    echo "Google Sheets credentials найдены"
fi

# 5. Проверяем spreadsheets.json
if [ ! -f "gsheets/spreadsheets.json" ]; then
    echo "ОШИБКА: Файл gsheets/spreadsheets.json не найден!"
    echo "Создайте файл с ID Google таблиц"
    exit 1
else
    echo "Конфигурация Google Sheets найдена"
fi

# 6. Проверяем Google Sheets подключение
echo "Проверяю Google Sheets подключение..."
python -c "
import gspread
from google.oauth2.service_account import Credentials
try:
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    credentials = Credentials.from_service_account_file('gsheets/credentials.json', scopes=scopes)
    client = gspread.authorize(credentials)
    print('Google Sheets подключение успешно!')
except Exception as e:
    print(f'Ошибка Google Sheets: {e}')
    exit(1)
"

# 7. Проверяем arsenkin/blacklist_domains.json
if [ ! -f "arsenkin/blacklist_domains.json" ]; then
    echo "Создаю blacklist_domains.json..."
    echo "[]" > arsenkin/blacklist_domains.json
fi

# 8. Создаем необходимые директории
echo "Создаю директории для логов и тестовых данных..."
mkdir -p logs
mkdir -p jsontests

echo ""
echo "Развертывание завершено успешно!"
echo ""
echo "Доступные команды для запуска:"
echo "   python main.py                             # Основной цикл генерации метатегов"
echo "   python gsheets/sheets_reader.py            # Чтение данных из Google Sheets"
echo "   python arsenkin/search_batch_processor.py  # Поиск конкурентов"
echo "   python arsenkin/h_parser.py                # Парсинг метатегов"
echo ""
echo "Управление systemd сервисом:"
echo "   sudo systemctl status seotools             # Статус сервиса"
echo "   sudo systemctl restart seotools            # Перезапуск сервиса"
echo "   sudo systemctl stop seotools               # Остановка сервиса"
echo "   sudo journalctl -u seotools -f             # Логи сервиса"
echo ""
echo "Мониторинг:"
echo "   tail -f logs/*.log                         # Просмотр логов"
echo "   ps aux | grep main.py                      # Запущенный процесс"
echo ""
echo "🎯 Развертывание завершено!"
echo ""
