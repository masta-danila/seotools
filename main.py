"""
Полный цикл генерации метатегов из Google Sheets

Выполняет шесть последовательных шагов:
1. Чтение данных из Google Sheets
2. Получение ссылок через XMLRiver API (Яндекс поиск)
3. Парсинг метатегов сайтов (title, description, h1)
4. Лемматизация текстов
5. Генерация метатегов через LLM
6. Загрузка результатов обратно в Google Sheets
"""

import asyncio
import time
import sys
import json
from pathlib import Path

# Добавляем пути к модулям
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "gsheets"))
sys.path.insert(0, str(project_root / "xmlriver"))
sys.path.insert(0, str(project_root / "site_parser"))
sys.path.insert(0, str(project_root / "lemmatizers"))
sys.path.insert(0, str(project_root / "metagenerators"))

from sheets_reader import process_all_spreadsheets  # type: ignore
from yandex_parser import process_sheets_data as xmlriver_process_sheets_data  # type: ignore
from batch_meta_processor import process_batch_urls  # type: ignore
from lemmatizer_processor import process_urls_with_lemmatization  # type: ignore
from metagenerator_batch import generate_metatags_batch  # type: ignore
from sheets_updater import update_all_spreadsheets  # type: ignore
from logger_config import get_pipeline_logger

logger = get_pipeline_logger()


def save_step_results(data, filename: str):
    """Сохраняет результаты шага в JSON файл"""
    output_file = project_root / "jsontests" / filename
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"  → Сохранено в {filename}")


async def run_full_pipeline():
    """Запускает полный цикл генерации метатегов"""
    
    logger.info("ЗАПУСК ПОЛНОГО ЦИКЛА ГЕНЕРАЦИИ МЕТАТЕГОВ")
    
    # Шаг 1: Чтение Google Sheets
    logger.info("ШАГ 1/6: Чтение данных из Google Sheets")
    data = process_all_spreadsheets()
    save_step_results(data, "step1_sheets_data.json")
    
    # Шаг 2: Получение ссылок через XMLRiver (Яндекс)
    logger.info("ШАГ 2/6: Получение ссылок через XMLRiver API (Яндекс)")
    data = await xmlriver_process_sheets_data(
        sheets_data=data,
        default_region=213,  # Регион по умолчанию, если не указан в данных URL
        urls_per_query=10,  # Количество URL от каждого запроса
        device="mobile",  # desktop, tablet, mobile
        domain="ru",  # ru, com, ua...
        lang="ru",  # ru, uk, en...
        max_concurrent=10,  # XMLRiver: до 10 одновременных запросов
        task_start_delay=0.0  # XMLRiver: прямые запросы, задержка не нужна
    )
    save_step_results(data, "step2_search_results.json")
    
    # Шаг 3: Парсинг метатегов сайтов
    logger.info("ШАГ 3/6: Парсинг метатегов сайтов (title, description, h1)")
    # Проверка данных перед шагом 3
    total_filtered = sum(
        len(url_data.get('filtered_urls', []))
        for sheet_info in data.values()
        for url_data in sheet_info.get('urls', {}).values()
    )
    logger.info(f"  Всего filtered_urls для обработки: {total_filtered}")
    
    data = await process_batch_urls(
        batch_data=data,
        max_concurrent=100,  # Количество одновременных запросов к сайтам
        domain_delay=2.0  # Пауза между запросами к одному домену (в секундах)
    )
    save_step_results(data, "step3_parsed_metatags.json")
    
    # Шаг 4: Лемматизация
    logger.info("ШАГ 4/6: Лемматизация текстов")
    data = process_urls_with_lemmatization(
        data=data,
        title_min_words=4,
        title_max_words=6,
        description_min_words=6,
        description_max_words=10
    )
    save_step_results(data, "step4_lemmatized.json")
    
    # Шаг 5: Генерация метатегов
    logger.info("ШАГ 5/6: Генерация метатегов через LLM")
    data = await generate_metatags_batch(
        data=data,
        model="claude-sonnet-4-5-20250929",
        max_concurrent=2,
        max_retries=3
    )
    save_step_results(data, "step5_generated_metatags.json")
    
    # Шаг 6: Загрузка в Google Sheets
    logger.info("ШАГ 6/6: Загрузка результатов в Google Sheets")
    stats = update_all_spreadsheets(
        data=data,
        sheet_name="Meta"
    )
    save_step_results(stats, "step6_update_stats.json")
    
    logger.info("ЦИКЛ ЗАВЕРШЕН УСПЕШНО")


if __name__ == "__main__":
    SLEEP_MINUTES = 10  # Интервал между циклами в минутах
    
    logger.info("Запуск бесконечного цикла обработки")
    logger.info(f"Интервал между циклами: {SLEEP_MINUTES} минут")
    
    while True:
        try:
            asyncio.run(run_full_pipeline())
            logger.info(f"Следующий запуск через {SLEEP_MINUTES} минут")
            
        except KeyboardInterrupt:
            logger.info("ОСТАНОВЛЕНО ПОЛЬЗОВАТЕЛЕМ")
            break
            
        except Exception as e:
            logger.error(f"ОШИБКА: {e}", exc_info=True)
            logger.info(f"Следующая попытка через {SLEEP_MINUTES} минут")
        
        # Ожидание перед следующим циклом
        sleep_seconds = SLEEP_MINUTES * 60
        time.sleep(sleep_seconds)
