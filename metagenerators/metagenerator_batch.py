"""
Модуль для пакетной генерации метатегов через LLM
"""
import json
import asyncio
import sys
import os
from typing import Dict, List
from pathlib import Path

# Добавляем путь к текущей папке
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, str(Path(__file__).parent.parent))

from metagenerator import generate_seo_texts
from logger_config import get_metagenerator_logger

logger = get_metagenerator_logger()


async def generate_for_single_url(
    url: str,
    url_data: Dict,
    semaphore: asyncio.Semaphore,
    model: str = "claude-sonnet-4-5-20250929",
    max_retries: int = 3
) -> Dict:
    """
    Генерирует метатеги для одного URL с повторными попытками при ошибках
    
    Args:
        url: URL для генерации
        url_data: Данные URL (lemmatized_title_words, queries, company_name и т.д.)
        semaphore: Семафор для ограничения одновременных запросов
        model: Модель LLM
        max_retries: Максимальное количество попыток при ошибках
        
    Returns:
        Словарь с результатами генерации или ошибкой
    """
    async with semaphore:
        for attempt in range(max_retries):
            try:
                logger.info(f"[{attempt + 1}/{max_retries}] Генерация для: {url}")
                
                # Извлекаем данные
                title_words = url_data.get("lemmatized_title_words", [])
                description_words = url_data.get("lemmatized_description_words", [])
                company_name = url_data.get("company_name", "")
                queries = url_data.get("queries", [])
                main_query = queries[0] if queries else ""
                
                # Переменные Битрикса
                h1_variables = url_data.get("variables_h1", [])
                title_variables = url_data.get("variables_title", [])
                description_variables = url_data.get("variables_description", [])
                
                # Генерируем SEO-тексты
                result = await generate_seo_texts(
                    title_words=title_words,
                    description_words=description_words,
                    company_name=company_name,
                    main_query=main_query,
                    h1_variables=h1_variables,
                    title_variables=title_variables,
                    description_variables=description_variables,
                    model=model
                )
                
                # Добавляем метаданные
                result["url"] = url
                result["metadata"] = {
                    "title_words": title_words,
                    "description_words": description_words,
                    "company_name": company_name,
                    "main_query": main_query,
                    "h1_variables": h1_variables,
                    "title_variables": title_variables,
                    "description_variables": description_variables
                }
                
                logger.info(f"[OK] {url}")
                return result
                
            except Exception as e:
                logger.error(f"[ОШИБКА] Попытка {attempt + 1} для {url}: {str(e)}")
                
                if attempt == max_retries - 1:
                    # Последняя попытка - возвращаем ошибку
                    return {
                        "url": url,
                        "error": str(e),
                        "h1": None,
                        "title": None,
                        "description": None,
                        "cost": 0
                    }
                
                # Ждем перед следующей попыткой
                await asyncio.sleep(2 * (attempt + 1))
        
        # На случай непредвиденной ситуации
        return {
            "url": url,
            "error": "Unknown error - no result returned",
            "h1": None,
            "title": None,
            "description": None,
            "cost": 0
        }


async def generate_metatags_batch(
    data: Dict,
    model: str = "claude-sonnet-4-5-20250929",
    max_concurrent: int = 3,
    max_retries: int = 3
) -> Dict:
    """
    Генерирует метатеги для всех URL из словаря и добавляет их в исходную структуру
    
    Args:
        data: Словарь структуры {spreadsheet_id: {urls: {url: {...}}}}
        model: Модель LLM для генерации
        max_concurrent: Максимальное количество одновременных запросов
        max_retries: Максимальное количество попыток при ошибках
        
    Returns:
        Обновленный словарь с добавленными сгенерированными метатегами
    """
    logger.info("Начало пакетной генерации метатегов:")
    logger.info(f"- Модель: {model}")
    logger.info(f"- Одновременных запросов: {max_concurrent}")
    logger.info(f"- Попыток на URL: {max_retries}")
    
    # Создаем семафор для ограничения одновременных запросов
    semaphore = asyncio.Semaphore(max_concurrent)
    
    # Создаем задачи для всех URL
    tasks = []
    url_mapping = []  # Список кортежей (spreadsheet_id, url)
    
    for spreadsheet_id, spreadsheet_info in data.items():
        urls_dict = spreadsheet_info.get('urls', {})
        for url, url_data in urls_dict.items():
            tasks.append(
                generate_for_single_url(
                    url=url,
                    url_data=url_data,
                    semaphore=semaphore,
                    model=model,
                    max_retries=max_retries
                )
            )
            url_mapping.append((spreadsheet_id, url))
    
    logger.info(f"Всего URL для обработки: {len(tasks)}\n")
    
    # Ждем выполнения всех задач
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Копируем исходные данные
    import copy
    result_data = copy.deepcopy(data)
    
    # Обрабатываем результаты и добавляем их в исходную структуру
    successful = 0
    failed = 0
    total_cost = 0.0
    
    for i, result in enumerate(results):
        spreadsheet_id, url = url_mapping[i]
        
        if isinstance(result, Exception):
            # Исключение
            result_data[spreadsheet_id]["urls"][url]["generated_metatags"] = {
                "error": str(result),
                "h1": None,
                "title": None,
                "description": None,
                "cost": 0
            }
            failed += 1
        elif result.get("error"):
            # Ошибка в результате
            result_data[spreadsheet_id]["urls"][url]["generated_metatags"] = {
                "error": result.get("error"),
                "h1": result.get("h1"),
                "title": result.get("title"),
                "description": result.get("description"),
                "cost": result.get("cost", 0)
            }
            failed += 1
        else:
            # Успешный результат - добавляем в исходную структуру
            result_data[spreadsheet_id]["urls"][url]["generated_metatags"] = {
                "h1": result.get("h1"),
                "title": result.get("title"),
                "description": result.get("description"),
                "cost": result.get("cost", 0)
            }
            successful += 1
            total_cost += result.get("cost", 0)
    
    logger.info("Результаты пакетной генерации:")
    logger.info(f"- Успешно: {successful}")
    logger.info(f"- Ошибок: {failed}")
    logger.info(f"- Общая стоимость: ${total_cost:.6f}")
    
    if failed > 0:
        logger.warning("Не удалось сгенерировать для:")
        for spreadsheet_id, url in url_mapping:
            generated = result_data[spreadsheet_id]["urls"][url].get("generated_metatags", {})
            if generated.get("error"):
                logger.info(f"  - {url}: {generated.get('error', 'Unknown error')}")
    
    return result_data


def save_batch_results(
    results: Dict,
    output_path: str = "jsontests/metagenerator_batch_results.json"
) -> None:
    """
    Сохраняет результаты пакетной генерации в JSON файл
    
    Args:
        results: Словарь с результатами генерации
        output_path: Путь для сохранения файла
    """
    output_dir = Path(output_path).parent
    output_dir.mkdir(exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Результаты сохранены в {output_path}")


if __name__ == "__main__":
    """
    Тестовый запуск пакетной генерации
    """
    async def test():
        # Определяем пути относительно корня проекта
        project_root = Path(__file__).parent.parent
        input_file = project_root / "jsontests" / "step4_lemmatized.json"
        output_file = project_root / "jsontests" / "metagenerator_batch_results.json"
        
        # Загружаем данные
        with open(input_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Запускаем пакетную генерацию
        results = await generate_metatags_batch(
            data=data,
            model="claude-sonnet-4-5-20250929",
            max_concurrent=2,  # 2 одновременных запроса
            max_retries=3      # 3 попытки на каждый URL
        )
        
        # Сохраняем результаты
        save_batch_results(results, str(output_file))
    
    asyncio.run(test())
