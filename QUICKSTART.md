# Быстрый старт SEO Tools

## Локальный запуск (для разработки)

### 1. Клонирование и установка
```bash
git clone https://github.com/masta-danila/seotools.git
cd seotools

# Создание виртуального окружения
python3 -m venv venv
source venv/bin/activate

# Установка зависимостей
pip install -r requirements.txt
```

### 2. Настройка .env файла

Создайте файл `.env` в корне проекта:
```bash
# API ключи
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
ARSENKIN_API_KEY=...
DEEPSEEK_API_KEY=...
GROK_API_KEY=...
```

### 3. Настройка Google Sheets

#### 3.1. Получение credentials.json
1. Откройте [Google Cloud Console](https://console.cloud.google.com/)
2. Создайте новый проект
3. Включите APIs:
   - Google Sheets API
   - Google Drive API
4. Создайте Service Account:
   - IAM & Admin → Service Accounts → Create Service Account
   - Дайте имя: `seotools-service`
   - Роль: Editor
5. Создайте ключ:
   - Actions → Manage Keys → Add Key → Create New Key
   - Выберите JSON
   - Скачайте файл
6. Сохраните как `gsheets/credentials.json`

#### 3.2. Создание spreadsheets.json
```bash
# В папке gsheets/ создайте файл spreadsheets.json
cat > gsheets/spreadsheets.json <<EOF
[
  "1O5dGWkcrg09dZRXnT2YpXUQsA23VMFhg-_ShM6Z1g5Q"
]
EOF
```

#### 3.3. Настройка доступа
В каждой Google таблице:
1. Откройте "Настройки доступа"
2. Добавьте email Service Account (из credentials.json, поле "client_email")
3. Дайте права "Редактор"

### 4. Структура Google таблицы

Каждая таблица должна содержать 2 листа:

#### Лист "Meta"
Колонки (регистр не важен):
- `URL` - адрес страницы
- `H1` - заголовок H1 (заполняется автоматически)
- `Title` - мета-тег title (заполняется автоматически)
- `Description` - мета-тег description (заполняется автоматически)

#### Лист "Data"
Колонки:
- `URL` - адрес страницы (должен совпадать с URL в листе Meta)
- `Queries` - поисковые запросы (через запятую)
- `Company Name` - название компании
- `Variables H1` - переменные для H1 (через запятую, например: `{price} р.`)
- `Variables Title` - переменные для Title (через запятую)
- `Variables Description` - переменные для Description (через запятую)

### 5. Blacklist доменов (опционально)

Создайте файл `arsenkin/blacklist_domains.json` с доменами, которые нужно исключить из анализа:
```json
[
  "yandex.ru",
  "google.com",
  "wikipedia.org"
]
```

### 6. Первый запуск

```bash
# Активируйте виртуальное окружение
source venv/bin/activate

# Запустите основной пайплайн
python main.py
```

## Тестирование отдельных модулей

### Чтение Google Sheets
```bash
python gsheets/sheets_reader.py
```
Результат: `jsontests/sheets_data.json`

### Поиск конкурентов (Arsenkin API)
```bash
python arsenkin/search_batch_processor.py
```
Входные данные: `jsontests/sheets_data.json`
Результат: `jsontests/search_batch_results.json`

### Парсинг метатегов (Arsenkin API)
```bash
python arsenkin/h_parser.py
```
Входные данные: `jsontests/search_batch_results.json`
Результат: `jsontests/arsenkin_h_results.json`

### Лемматизация текстов
```bash
python lemmatizers/lemmatizer_processor.py
```
Входные данные: `jsontests/arsenkin_h_results.json`
Результат: `jsontests/lemmatizer_processor_results.json`

### Генерация метатегов (LLM)
```bash
python metagenerators/metagenerator_batch.py
```
Входные данные: `jsontests/lemmatizer_processor_results.json`
Результат: `jsontests/metagenerator_batch_results.json`

### Обновление Google Sheets
```bash
python gsheets/sheets_updater.py
```
Входные данные: `jsontests/metagenerator_batch_results.json`

## Просмотр логов

Все логи сохраняются в папке `logs/`:

```bash
# Просмотр в реальном времени
tail -f logs/pipeline.log

# Просмотр конкретного модуля
tail -f logs/search.log
tail -f logs/parser.log
tail -f logs/metagenerator.log
```

## Настройка параметров

Откройте `main.py` и настройте параметры:

```python
# Интервал между циклами
SLEEP_MINUTES = 10  # Минут между запусками

# В функции run_full_pipeline():

# Шаг 2: Поиск конкурентов
process_sheets_data(
    sheets_data=data,
    se_type=3,              # Тип поисковой системы (3 = Яндекс)
    region=213,             # ID региона (213 = Москва)
    max_wait_time=600,      # Макс. время ожидания (сек)
    wait_per_query=15,      # Интервал проверки статуса (сек)
    is_snippet=False,       # Получать сниппеты
    urls_per_query=5,       # Топ-N конкурентов от каждого запроса
    max_concurrent=2        # Одновременных запросов
)

# Шаг 4: Лемматизация
process_urls_with_lemmatization(
    data=data,
    title_min_words=4,      # Мин. слов для Title
    title_max_words=6,      # Макс. слов для Title
    description_min_words=6,  # Мин. слов для Description
    description_max_words=10  # Макс. слов для Description
)

# Шаг 5: Генерация метатегов
generate_metatags_batch(
    data=data,
    model="claude-sonnet-4-5-20250929",  # Модель LLM
    max_concurrent=2,       # Одновременных запросов к LLM
    max_retries=3           # Попыток при ошибке
)
```

## Остановка программы

```bash
# Нажмите Ctrl+C для остановки
# Программа корректно завершит текущий цикл
```

## Troubleshooting

### Ошибка: credentials.json not found
```bash
# Проверьте наличие файла
ls -la gsheets/credentials.json

# Проверьте права
chmod 600 gsheets/credentials.json
```

### Ошибка: 429 Too Many Requests (Arsenkin)
```bash
# API позволяет максимум 30 запросов/мин
# Увеличьте паузы в main.py:
# - await asyncio.sleep(120)  # между шагами 2 и 3
# - wait_per_query=15 (или больше)
# - max_concurrent=2 (или меньше)
```

### Ошибка: Google Sheets permission denied
```bash
# Убедитесь что Service Account добавлен в таблицу:
# 1. Откройте таблицу
# 2. Нажмите "Настройки доступа"
# 3. Добавьте email из credentials.json (поле client_email)
# 4. Дайте права "Редактор"
```

### Ошибка: LLM API rate limit
```bash
# Уменьшите max_concurrent в generate_metatags_batch:
# max_concurrent=1  # или 2
```

## Полезные команды

```bash
# Проверка подключения к Google Sheets
python -c "import gspread; from google.oauth2.service_account import Credentials; \
    creds = Credentials.from_service_account_file('gsheets/credentials.json'); \
    client = gspread.authorize(creds); print('OK')"

# Проверка API ключей
python -c "from dotenv import load_dotenv; import os; load_dotenv(); \
    print('Arsenkin:', 'OK' if os.getenv('ARSENKIN_API_KEY') else 'MISSING'); \
    print('Anthropic:', 'OK' if os.getenv('ANTHROPIC_API_KEY') else 'MISSING')"

# Очистка логов
rm logs/*.log.*

# Очистка тестовых данных
rm jsontests/*.json
```

## Следующие шаги

После успешного тестирования локально:
1. Прочитайте [DEPLOY.md](DEPLOY.md) для деплоя на сервер
2. Настройте systemd службу для автозапуска
3. Настройте мониторинг логов

## Поддержка

При возникновении проблем:
1. Проверьте логи в папке `logs/`
2. Убедитесь что все API ключи корректны
3. Проверьте доступ к Google Sheets
4. Проверьте rate limits API
