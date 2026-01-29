# Инструкция по развертыванию SEO Tools на сервере

## Предварительные требования

- Ubuntu/Debian сервер
- Python 3.11+
- Доступ по SSH
- Права sudo

## Структура на сервере

Проект будет развернут в директории:
```
/home/callchecker/seotools/
```

Рядом с существующими проектами:
```
/home/callchecker/callchecker/
/home/callchecker/revchecker/
/home/callchecker/seotools/  ← новый проект
```

## Шаг 1: Клонирование проекта на сервер

### 1.1. Подключитесь к серверу:
```bash
ssh callchecker@YOUR_SERVER_IP
```

### 1.2. Клонируйте проект из GitHub:
```bash
cd /home/callchecker
git clone https://github.com/masta-danila/seotools.git
cd seotools
```

## Шаг 2: Копирование конфигурационных файлов

**ВАЖНО:** Эти файлы содержат секретные данные и не хранятся в Git!

### 2.1. На локальной машине убедитесь, что у вас есть:
- `.env` - API ключи (ANTHROPIC_API_KEY, OPENAI_API_KEY, ARSENKIN_API_KEY и др.)
- `gsheets/credentials.json` - credentials из Google Cloud Console
- `gsheets/sheets_config.json` - ID Google таблиц

### 2.2. Скопируйте файлы на сервер:
```bash
# На локальной машине
cd /Users/daniladzhiev/PycharmProjects/seotools

# Копируем .env
scp .env callchecker@YOUR_SERVER_IP:/home/callchecker/seotools/

# Копируем Google Sheets credentials
scp gsheets/credentials.json callchecker@YOUR_SERVER_IP:/home/callchecker/seotools/gsheets/

# Копируем конфигурацию таблиц
scp gsheets/sheets_config.json callchecker@YOUR_SERVER_IP:/home/callchecker/seotools/gsheets/
```

## Шаг 3: Установка зависимостей и проверка

### 3.1. Сделайте скрипты исполняемыми:
```bash
chmod +x deploy_server.sh
chmod +x setup_systemd_service.sh
```

### 3.2. Запустите скрипт развертывания:
```bash
./deploy_server.sh
```

Этот скрипт:
- Создаст виртуальное окружение
- Установит зависимости из requirements.txt
- Проверит наличие .env и credentials.json
- Проверит подключение к Google Sheets
- Создаст необходимые директории (logs/, jsontests/)
- Создаст arsenkin/blacklist_domains.json если его нет

## Шаг 4: Настройка systemd службы

### 4.1. Установите службу:
```bash
./setup_systemd_service.sh
```

Этот скрипт:
- Скопирует `seotools.service` в `/etc/systemd/system/`
- Включит автозапуск при перезагрузке сервера
- Запустит службу

### 4.2. Проверьте статус:
```bash
sudo systemctl status seotools
```

## Управление службой

### Основные команды:
```bash
# Статус
sudo systemctl status seotools

# Перезапуск
sudo systemctl restart seotools

# Остановка
sudo systemctl stop seotools

# Запуск
sudo systemctl start seotools

# Отключить автозапуск
sudo systemctl disable seotools

# Включить автозапуск
sudo systemctl enable seotools
```

### Просмотр логов:
```bash
# Логи systemd в реальном времени
sudo journalctl -u seotools -f

# Логи за сегодня
sudo journalctl -u seotools --since today

# Последние 100 строк
sudo journalctl -u seotools -n 100

# Логи приложения (из папки logs/)
tail -f /home/callchecker/seotools/logs/pipeline.log
tail -f /home/callchecker/seotools/logs/search.log
tail -f /home/callchecker/seotools/logs/parser.log
tail -f /home/callchecker/seotools/logs/metagenerator.log
```

## Обновление проекта

На сервере выполните:
```bash
cd /home/callchecker/seotools

# Остановите службу
sudo systemctl stop seotools

# Получите последние изменения из GitHub
git pull origin main

# Обновите зависимости (если нужно)
source venv/bin/activate
pip install -r requirements.txt

# Запустите службу
sudo systemctl start seotools
```

**Примечание:** Если вы обновили `.env` или файлы в `gsheets/`, скопируйте их заново с локальной машины (см. Шаг 2).

## Мониторинг

### Проверка работы всех служб:
```bash
# Все службы (callchecker + revchecker + seotools)
sudo systemctl status callchecker-* revchecker seotools

# Проверка процессов
ps aux | grep -E 'callchecker|revchecker|seotools'
```

### Логи всех систем:
```bash
# Все логи systemd
sudo journalctl -u "callchecker-*" -u revchecker -u seotools -f

# Логи приложений
tail -f /home/callchecker/*/logs/*.log
```

## Настройка параметров

Параметры работы настраиваются в `main.py`:

```python
SLEEP_MINUTES = 10  # Интервал между циклами в минутах

# В функции run_full_pipeline() параметры для каждого шага:
# - max_concurrent=2          # Одновременных запросов к API
# - wait_per_query=15         # Интервал проверки статуса
# - title_min_words=4         # Мин. слов для title
# - title_max_words=6         # Макс. слов для title
# - model="claude-sonnet-4-5-20250929"  # Модель LLM
```

После изменения параметров:
```bash
sudo systemctl restart seotools
```

## Troubleshooting

### Служба не запускается
```bash
# Проверьте логи
sudo journalctl -u seotools -n 50

# Проверьте конфигурацию
sudo systemctl cat seotools

# Попробуйте запустить вручную
cd /home/callchecker/seotools
source venv/bin/activate
python main.py
```

### Ошибки с Google Sheets
```bash
# Проверьте credentials
ls -la gsheets/credentials.json

# Проверьте подключение
cd /home/callchecker/seotools
source venv/bin/activate
python -c "import gspread; from google.oauth2.service_account import Credentials; \
    creds = Credentials.from_service_account_file('gsheets/credentials.json'); \
    client = gspread.authorize(creds); print('OK')"
```

### Ошибки с Arsenkin API
```bash
# Проверьте .env
cat .env | grep ARSENKIN_API_KEY

# Проверьте rate limiting
# API позволяет не более 30 запросов/мин и 5 задач одновременно
```

### Ошибки с LLM API
```bash
# Проверьте .env
cat .env | grep -E 'API_KEY'

# Проверьте подключение
cd /home/callchecker/seotools
source venv/bin/activate
python -c "from dotenv import load_dotenv; import os; load_dotenv(); \
    print('Anthropic:', 'OK' if os.getenv('ANTHROPIC_API_KEY') else 'MISSING'); \
    print('OpenAI:', 'OK' if os.getenv('OPENAI_API_KEY') else 'MISSING')"
```

## Структура файлов на сервере

```
/home/callchecker/
├── callchecker/                    # Существующий проект
│   ├── venv/
│   ├── bitrix24/
│   ├── logs/
│   └── ...
├── revchecker/                     # Существующий проект
│   ├── venv/
│   ├── llm/
│   ├── gsheets/
│   └── ...
└── seotools/                       # Новый проект
    ├── venv/
    ├── arsenkin/
    │   ├── search_parser.py
    │   ├── h_parser.py
    │   └── blacklist_domains.json
    ├── gsheets/
    │   ├── credentials.json        ← Важно!
    │   ├── sheets_config.json      ← Важно!
    │   ├── sheets_reader.py
    │   └── sheets_updater.py
    ├── lemmatizers/
    │   ├── lemmatizer.py
    │   └── lemmatizer_processor.py
    ├── metagenerators/
    │   ├── metagenerator.py
    │   └── metagenerator_batch.py
    ├── parsers/
    ├── llm/
    ├── logs/
    ├── jsontests/
    ├── .env                        ← Важно!
    ├── main.py
    ├── logger_config.py
    └── ...
```

## Безопасность

1. **Файлы с секретами не должны попадать в Git:**
   - `.env`
   - `gsheets/credentials.json`
   - `jsontests/*.json` (могут содержать URL клиентов)

2. **Права на файлы:**
```bash
chmod 600 .env
chmod 600 gsheets/credentials.json
chmod 755 *.sh
```

3. **Логи могут содержать чувствительные данные:**
```bash
# Регулярно чистите старые логи
find logs/ -name "*.log.*" -mtime +30 -delete
```

## Архитектура пайплайна

Проект работает в бесконечном цикле с интервалом 10 минут:

1. **Шаг 1/6**: Чтение данных из Google Sheets (лист Meta и Data)
2. **Шаг 2/6**: Получение ссылок конкурентов через Arsenkin API (check-top)
3. **Шаг 3/6**: Получение метатегов страниц через Arsenkin API (check-h)
4. **Шаг 4/6**: Лемматизация текстов (извлечение ключевых слов)
5. **Шаг 5/6**: Генерация метатегов через LLM (Claude/OpenAI/Gemini)
6. **Шаг 6/6**: Загрузка результатов обратно в Google Sheets

### Rate Limits Arsenkin API:
- Максимум 30 запросов в минуту
- Максимум 5 задач одновременно
- Пауза 120 секунд между шагами 2 и 3 для соблюдения лимитов

## Дополнительные ресурсы

- **Arsenkin API**: https://help.arsenkin.ru/api
- **Google Sheets API**: https://developers.google.com/sheets/api
- **Anthropic Claude API**: https://docs.anthropic.com/claude/reference
- **OpenAI API**: https://platform.openai.com/docs/api-reference
