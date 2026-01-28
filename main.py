"""
Полный цикл генерации метатегов из Google Sheets

Выполняет шесть последовательных шагов:
1. Чтение данных из Google Sheets
2. Получение ссылок через Arsenkin API
3. Получение метатегов страниц
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
sys.path.insert(0, str(project_root / "arsenkin"))
sys.path.insert(0, str(project_root / "lemmatizers"))
sys.path.insert(0, str(project_root / "metagenerators"))

from sheets_reader import process_all_spreadsheets  # type: ignore
from search_batch_processor import process_sheets_data  # type: ignore
from h_parser import process_batch_results_with_metatags  # type: ignore
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
    
    logger.info("="*80)
    logger.info("ЗАПУСК ПОЛНОГО ЦИКЛА ГЕНЕРАЦИИ МЕТАТЕГОВ")
    logger.info("="*80)
    
    # Шаг 1: Чтение Google Sheets
    logger.info("ШАГ 1/6: Чтение данных из Google Sheets")
    data = process_all_spreadsheets()
    # save_step_results(data, "step1_sheets_data.json")
    
    # Шаг 2: Получение ссылок
    logger.info("ШАГ 2/6: Получение ссылок через Arsenkin API")
    data = await process_sheets_data(
        sheets_data=data,
        se_type=3,
        region=213,
        max_wait_time=600,
        wait_per_query=15,  # Увеличено с 10 до 15 для более редких проверок статуса
        is_snippet=False,
        urls_per_query=5,
        max_concurrent=2  # Уменьшено с 3 до 2 для соблюдения лимита 30 запросов/мин
    )
    # save_step_results(data, "step2_search_results.json")
    
    # Пауза между шагами для соблюдения rate limit Arsenkin API (30 запросов/мин)
    # Увеличенная пауза гарантирует, что запросы с шага 2 вышли из скользящего окна
    logger.info("⏳ Пауза 120 сек для соблюдения rate limit API (30 запросов/мин)...")
    await asyncio.sleep(120)
    
    # Шаг 3: Получение метатегов
    logger.info("ШАГ 3/6: Получение метатегов страниц")
    # Проверка данных перед шагом 3
    total_filtered = sum(
        len(url_data.get('filtered_urls', []))
        for sheet_info in data.values()
        for url_data in sheet_info.get('urls', {}).values()
    )
    logger.info(f"  Всего filtered_urls для обработки: {total_filtered}")
    
    data = await process_batch_results_with_metatags(
        batch_data=data,
        foreign=False,
        max_wait_time=300,
        wait_per_url=3  # Увеличено с 2 до 3 для более редких проверок статуса
    )
    # save_step_results(data, "step3_parsed_metatags.json")
    
    # Шаг 4: Лемматизация
    logger.info("ШАГ 4/6: Лемматизация текстов")
    data = process_urls_with_lemmatization(
        data=data,
        title_min_words=4,
        title_max_words=6,
        description_min_words=6,
        description_max_words=10
    )
    # save_step_results(data, "step4_lemmatized.json")
    
    # Шаг 5: Генерация метатегов
    logger.info("ШАГ 5/6: Генерация метатегов через LLM")
    data = await generate_metatags_batch(
        data=data,
        model="claude-sonnet-4-5-20250929",
        max_concurrent=2,
        max_retries=3
    )
    # save_step_results(data, "step5_generated_metatags.json")
    
    # Шаг 6: Загрузка в Google Sheets
    logger.info("ШАГ 6/6: Загрузка результатов в Google Sheets")
    stats = update_all_spreadsheets(
        data=data,
        sheet_name="Meta",
        delay=1.0
    )
    # save_step_results(stats, "step6_update_stats.json")
    
    logger.info("="*80)
    logger.info("ЦИКЛ ЗАВЕРШЕН УСПЕШНО")
    logger.info("="*80)


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
