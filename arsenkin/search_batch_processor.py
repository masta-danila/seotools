"""
Асинхронный обработчик для массового поиска конкурентов через Arsenkin API
"""
import os
import sys
import json
import asyncio
from typing import Dict, List, Optional

# Добавляем текущую директорию в путь для импорта
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from search_parser import get_top_results


async def process_url(
    url: str,
    url_data: Dict,
    se_type: int = 3,
    region: int = 213,
    max_wait_time: int = 300,
    wait_per_query: int = 2,
    is_snippet: bool = False,
    urls_per_query: int = 5,
) -> Dict:
    """
    Обрабатывает один URL: делает запрос по queries и добавляет отфильтрованные URL
    
    Args:
        url: URL страницы
        url_data: Данные URL (queries, company_name, и т.д.)
        se_type: Тип поисковой системы
        region: ID региона
        max_wait_time: Максимальное время ожидания
        wait_per_query: Множитель времени ожидания на запрос
        is_snippet: Получать ли сниппеты
        urls_per_query: Количество URL для извлечения от каждого запроса
    
    Returns:
        Словарь с исходными данными + filtered_urls
    """
    queries = url_data.get('queries', [])
    
    if not queries:
        print(f"[SKIP] Пропущен {url}: нет запросов")
        return {**url_data, 'filtered_urls': []}
    
    print(f"[PROCESS] Обработка {url} ({len(queries)} запросов, топ-{urls_per_query} от каждого)...")
    
    try:
        result = await get_top_results(
            queries=queries,
            se_type=se_type,
            region=region,
            max_wait_time=max_wait_time,
            wait_per_query=wait_per_query,
            is_snippet=is_snippet,
            urls_per_query=urls_per_query,
        )
        
        # Результат - список уникальных URL
        if result and isinstance(result, list):
            filtered_urls = result
            print(f"[OK] {url}: найдено {len(filtered_urls)} уникальных конкурентов")
        else:
            filtered_urls = []
            print(f"[WARN] {url}: конкуренты не найдены")
        
        return {**url_data, 'filtered_urls': filtered_urls}
    
    except Exception as e:
        print(f"[ERROR] Ошибка при обработке {url}: {e}")
        return {**url_data, 'filtered_urls': []}


async def process_sheets_data(
    sheets_data: Dict,
    se_type: int = 3,
    region: int = 213,
    max_wait_time: int = 300,
    wait_per_query: int = 5,
    is_snippet: bool = False,
    urls_per_query: int = 5,
    max_concurrent: int = 3,
) -> Dict:
    """
    Обрабатывает все URL из sheets_data асинхронно
    
    Args:
        sheets_data: Словарь с данными из Google Sheets
        se_type: Тип поисковой системы
        region: ID региона
        max_wait_time: Максимальное время ожидания
        wait_per_query: Множитель времени ожидания на запрос
        is_snippet: Получать ли сниппеты
        urls_per_query: Количество URL для извлечения от каждого запроса
        max_concurrent: Максимальное количество одновременных запросов
    
    Returns:
        Обновлённый словарь с добавленными filtered_urls для каждого URL
    """
    result_data = {}
    
    # Создаём семафор для ограничения одновременных запросов
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_with_semaphore(spreadsheet_id: str, url: str, url_data: Dict):
        async with semaphore:
            processed_url_data = await process_url(
                url=url,
                url_data=url_data,
                se_type=se_type,
                region=region,
                max_wait_time=max_wait_time,
                wait_per_query=wait_per_query,
                is_snippet=is_snippet,
                urls_per_query=urls_per_query,
            )
            return spreadsheet_id, url, processed_url_data
    
    # Собираем все задачи
    tasks = []
    for spreadsheet_id, spreadsheet_info in sheets_data.items():
        urls_dict = spreadsheet_info.get('urls', {})
        for url, url_data in urls_dict.items():
            tasks.append(process_with_semaphore(spreadsheet_id, url, url_data))
    
    print(f"\n{'='*80}")
    print(f"Запуск обработки {len(tasks)} URL (макс. {max_concurrent} одновременно)")
    print(f"{'='*80}\n")
    
    # Выполняем все задачи
    results = await asyncio.gather(*tasks)
    
    # Собираем результаты обратно в структуру
    for spreadsheet_id, url, processed_url_data in results:
        if spreadsheet_id not in result_data:
            result_data[spreadsheet_id] = {'urls': {}}
        result_data[spreadsheet_id]['urls'][url] = processed_url_data
    
    print(f"\n{'='*80}")
    print(f"Обработка завершена!")
    print(f"{'='*80}\n")
    
    return result_data


def save_results_to_json(results: Dict, filename: str = "jsontests/search_batch_results.json") -> None:
    """
    Сохраняет результаты в JSON файл
    
    Args:
        results: Результаты обработки
        filename: Имя файла для сохранения
    """
    os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else ".", exist_ok=True)
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\nРезультаты сохранены в файл: {filename}")
    except Exception as e:
        print(f"Ошибка при сохранении файла: {e}")


if __name__ == "__main__":
    """
    Тестовый запуск
    """
    # Загружаем данные
    with open("jsontests/sheets_data.json", 'r', encoding='utf-8') as f:
        sheets_data = json.load(f)
    
    # Обрабатываем
    results = asyncio.run(process_sheets_data(
        sheets_data=sheets_data,
        se_type=3,
        region=213,
        max_wait_time=300,
        wait_per_query=10,
        is_snippet=False,
        urls_per_query=5,  # Берем топ-5 URL от каждого запроса
        max_concurrent=3
    ))
    
    # Сохраняем
    if results:
        save_results_to_json(results, "jsontests/search_batch_results.json")
