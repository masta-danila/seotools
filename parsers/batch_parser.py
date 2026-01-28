import json
import asyncio
from pathlib import Path
from typing import List, Dict
import sys

# Импортируем парсер статей
sys.path.append(str(Path(__file__).parent))
from article_parser import parse_for_ml


def extract_urls_from_arsenkin(arsenkin_data: dict) -> List[str]:
    """
    Извлекает список URL из результатов Arsenkin API
    
    Args:
        arsenkin_data: Словарь с результатами из arsenkin/jsontests/arsenkin_top_results.json
        
    Returns:
        Список уникальных URL
    """
    urls = []
    
    # Извлекаем URL из result.collect (массив массивов массивов)
    if 'result' in arsenkin_data and 'collect' in arsenkin_data['result']:
        for query_results in arsenkin_data['result']['collect']:
            for search_engine_results in query_results:
                for url in search_engine_results:
                    if url and isinstance(url, str):
                        urls.append(url)
    
    # Убираем дубликаты, сохраняя порядок
    original_count = len(urls)
    unique_urls = list(dict.fromkeys(urls))
    duplicates_count = original_count - len(unique_urls)
    
    print(f"Извлечено URL из Arsenkin:")
    print(f"- Всего найдено: {original_count}")
    if duplicates_count > 0:
        print(f"- Дубликатов удалено: {duplicates_count}")
    print(f"- Уникальных URL: {len(unique_urls)}")
    
    return unique_urls


async def parse_single_url(
    url: str,
    semaphore: asyncio.Semaphore,
    max_retries: int = 3,
    delay: float = 1.0
) -> Dict:
    """
    Асинхронно парсит один URL с повторными попытками при ошибках
    
    Args:
        url: URL для парсинга
        semaphore: Семафор для ограничения одновременных запросов
        max_retries: Максимальное количество попыток при ошибках
        delay: Задержка между запросами (секунды)
        
    Returns:
        Словарь с url и html_structure или ошибкой
    """
    async with semaphore:
        for attempt in range(max_retries):
            try:
                print(f"Парсинг: {url} (попытка {attempt + 1}/{max_retries})")
                
                # Задержка между запросами (кроме первой попытки)
                if attempt > 0:
                    await asyncio.sleep(delay * 2)  # Увеличенная задержка при повторе
                
                # Парсим URL
                result = await parse_for_ml(url)
                
                # Задержка после успешного запроса
                await asyncio.sleep(delay)
                
                print(f"Успешно: {url}")
                return result
                
            except Exception as e:
                print(f"Ошибка при парсинге {url} (попытка {attempt + 1}): {str(e)}")
                
                if attempt == max_retries - 1:
                    # Последняя попытка - возвращаем ошибку
                    print(f"Не удалось распарсить {url} после {max_retries} попыток")
                    return {
                        'url': url,
                        'error': str(e),
                        'html_structure': None
                    }
                
                # Ждем перед следующей попыткой
                await asyncio.sleep(delay * (attempt + 1))
        
        # На случай непредвиденной ситуации
        return {
            'url': url,
            'error': 'Unknown error - no result returned',
            'html_structure': None
        }


async def parse_urls_batch(
    urls: List[str],
    max_concurrent: int = 3,
    max_retries: int = 3,
    delay: float = 1.0
) -> List[Dict]:
    """
    Асинхронно парсит список URL с ограничением одновременных запросов
    
    Args:
        urls: Список URL для парсинга (дубликаты будут удалены автоматически)
        max_concurrent: Максимальное количество одновременных запросов
        max_retries: Максимальное количество попыток при ошибках для каждого URL
        delay: Задержка между запросами (секунды)
        
    Returns:
        Список словарей с результатами парсинга (без дубликатов)
    """
    # Удаляем дубликаты, сохраняя порядок
    original_count = len(urls)
    unique_urls = list(dict.fromkeys(urls))
    duplicates_removed = original_count - len(unique_urls)
    
    print(f"\nНачало пакетного парсинга:")
    print(f"- Исходных URL: {original_count}")
    if duplicates_removed > 0:
        print(f"- Удалено дубликатов: {duplicates_removed}")
    print(f"- Уникальных URL для парсинга: {len(unique_urls)}")
    print(f"- Одновременных запросов: {max_concurrent}")
    print(f"- Попыток на URL: {max_retries}")
    print(f"- Задержка между запросами: {delay}сек\n")
    
    # Работаем только с уникальными URL
    urls = unique_urls
    
    # Создаем семафор для ограничения одновременных запросов
    semaphore = asyncio.Semaphore(max_concurrent)
    
    # Создаем задачи для всех URL
    tasks = [
        parse_single_url(url, semaphore, max_retries, delay)
        for url in urls
    ]
    
    # Ждем выполнения всех задач (return_exceptions=True чтобы не падать на ошибках)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Обрабатываем результаты и исключения
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            # Исключение - создаем словарь с ошибкой
            processed_results.append({
                'url': urls[i],
                'error': str(result),
                'html_structure': None
            })
        elif result is None:
            # None - создаем словарь с ошибкой
            processed_results.append({
                'url': urls[i],
                'error': 'Function returned None',
                'html_structure': None
            })
        else:
            processed_results.append(result)
    
    # Фильтруем успешные результаты
    successful = [r for r in processed_results if r and isinstance(r, dict) and r.get('html_structure') is not None]
    failed = [r for r in processed_results if r and isinstance(r, dict) and r.get('html_structure') is None]
    
    print(f"\nРезультаты пакетного парсинга:")
    print(f"- Успешно: {len(successful)}")
    print(f"- Ошибок: {len(failed)}")
    
    if failed:
        print("\nНе удалось распарсить:")
        for result in failed:
            print(f"  - {result['url']}: {result.get('error', 'Unknown error')}")
    
    return processed_results


def save_batch_results(results: List[Dict], output_path: str = "jsontests/batch_parse_results.json"):
    """
    Сохраняет результаты пакетного парсинга в JSON файл
    
    Args:
        results: Список результатов парсинга
        output_path: Путь для сохранения файла
    """
    output_dir = Path(output_path).parent
    output_dir.mkdir(exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\nРезультаты сохранены в {output_path}")


async def parse_urls(
    arsenkin_data: dict,
    max_concurrent: int = 3,
    max_retries: int = 3,
    delay: float = 1.0,
    model: str = "gpt-4o-mini"
) -> List[Dict]:
    """
    Парсит URL из результатов Arsenkin API
    
    Args:
        arsenkin_data: Словарь с результатами из Arsenkin API
        max_concurrent: Максимальное количество одновременных запросов
        max_retries: Максимальное количество попыток при ошибках
        delay: Задержка между запросами (секунды)
        model: Модель LLM
        
    Returns:
        Список результатов парсинга с url и html_structure
    """
    # Извлекаем URL (функция сама выведет статистику)
    urls = extract_urls_from_arsenkin(arsenkin_data)
    
    # Парсим URL
    results = await parse_urls_batch(
        urls,
        max_concurrent=max_concurrent,
        max_retries=max_retries,
        delay=delay
    )
    
    return results


if __name__ == "__main__":
    # Загружаем данные из файла
    arsenkin_file = "jsontests/arsenkin_top_results.json"
    print(f"Загрузка данных из {arsenkin_file}...")
    with open(arsenkin_file, 'r', encoding='utf-8') as f:
        arsenkin_data = json.load(f)
    
    # Парсим URL из данных Arsenkin
    results = asyncio.run(parse_urls(
        arsenkin_data=arsenkin_data,
        max_concurrent=500,  # одновременных запроса
        max_retries=3,     # 3 попытки на каждый URL
        delay=1.0,         # 1 секунда задержки между запросами
        model="gpt-4o-mini"  # Модель LLM для последующего анализа
    ))
    
    # Сохраняем результаты (только для тестирования)
    save_batch_results(results, "jsontests/batch_parse_results.json")