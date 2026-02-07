"""
Асинхронный клиент для API Arsenkin (инструмент check-top).
Документация: https://help.arsenkin.ru/api/api-top
"""
import os
import sys
import json
import asyncio
from typing import List, Dict, Optional, Union, Set
from urllib.parse import urlparse
from pathlib import Path
from dotenv import load_dotenv
import httpx

# Добавляем корень проекта в путь для импорта
sys.path.insert(0, str(Path(__file__).parent.parent))

from logger_config import get_search_logger
from rate_limiter import get_rate_limiter

logger = get_search_logger()

# Получаем глобальный rate limiter
_rate_limiter = get_rate_limiter()

# Загружаем переменные окружения из корня проекта
load_dotenv()

# API endpoints (согласно документации https://help.arsenkin.ru/api)
API_SET_URL = "https://arsenkin.ru/api/tools/set"
API_CHECK_URL = "https://arsenkin.ru/api/tools/check"
API_GET_URL = "https://arsenkin.ru/api/tools/get"

# Кэш для черного списка доменов
_blacklist_cache: Optional[Set[str]] = None


def get_api_token() -> str:
    """Получает API токен из переменных окружения"""
    api_token = os.getenv("ARSENKIN_API_TOKEN")
    if not api_token:
        raise ValueError("Установите переменную окружения ARSENKIN_API_TOKEN")
    return api_token.strip()


def get_headers() -> Dict[str, str]:
    """Возвращает заголовки для API запросов (только Bearer, как в доке)"""
    token = get_api_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


async def create_task(
    queries: List[str],
    se_type: int = 3,
    region: int = 213,
    depth: int = 10,
    is_snippet: bool = False,
    noreask: bool = False,
) -> Optional[int]:
    """
    Создаёт задачу на получение выдачи (инструмент check-top).

    se_type:
      1  = Яндекс XML
      2  = Яндекс Desktop
      3  = Яндекс Mobile
      11 = Google Desktop
      12 = Google Mobile
      20 = YouTube Desktop
      21 = YouTube Mobile
    """
    payload = {
        "tools_name": "check-top",
        "data": {
            "queries": queries,
            "is_snippet": is_snippet,
            "noreask": noreask,
            "se": [
                {"type": se_type, "region": region},
            ],
            "depth": depth,
        },
    }

    try:
        # Ждём разрешения от rate limiter
        await _rate_limiter.acquire()
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(API_SET_URL, headers=get_headers(), json=payload)
        response.raise_for_status()

        data = response.json()
        task_id = data.get("task_id")
        if task_id:
            return task_id
        return None

    except httpx.RequestError:
        return None
    except Exception:
        return None


async def check_task_status(task_id: int) -> Optional[str]:
    """
    Проверяет статус задачи
    
    Args:
        task_id: ID задачи
    
    Returns:
        Статус задачи ('Ok', 'Processing', 'Error') или None
    """
    payload = {"task_id": task_id}
    
    try:
        # Ждём разрешения от rate limiter
        await _rate_limiter.acquire()
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(API_CHECK_URL, headers=get_headers(), json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("status")

    except httpx.RequestError:
        return None
    except Exception:
        return None


async def get_task_result(task_id: int) -> Optional[Dict]:
    """
    Получает результат выполненной задачи
    
    Args:
        task_id: ID задачи
    
    Returns:
        Результат задачи в формате JSON или None
    """
    payload = {"task_id": task_id}
    
    try:
        # Ждём разрешения от rate limiter
        await _rate_limiter.acquire()
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(API_GET_URL, headers=get_headers(), json=payload)
        response.raise_for_status()

        data = response.json()
        if data.get("code") == "TASK_RESULT":
            return data.get("result")
        return None

    except httpx.RequestError:
        return None
    except Exception:
        return None


async def wait_for_task(task_id: int, max_wait_time: int = 300, check_interval: int = 5) -> Optional[Dict]:
    """
    Ожидает завершения задачи и возвращает результат
    
    Args:
        task_id: ID задачи
        max_wait_time: Максимальное время ожидания в секундах (по умолчанию 300)
        check_interval: Интервал проверки статуса в секундах (по умолчанию 5)
    
    Returns:
        Результат задачи или None
    """
    elapsed_time = 0

    while elapsed_time < max_wait_time:
        # Сначала ждём интервал (экономим API запрос на нулевой проверке)
        await asyncio.sleep(check_interval)
        elapsed_time += check_interval
        
        status = await check_task_status(task_id)
        logger.info(f"[check] t={elapsed_time}s status={status}")

        if status == "finish":
            return await get_task_result(task_id)
        elif status == "error":
            return None

    logger.warning(f"Превышено время ожидания ({max_wait_time}s)")
    return None


def load_blacklist_domains() -> Set[str]:
    """
    Загружает черный список доменов из JSON файла
    
    Returns:
        Множество доменов для фильтрации
    """
    global _blacklist_cache
    
    if _blacklist_cache is not None:
        return _blacklist_cache
    
    blacklist_path = os.path.join(os.path.dirname(__file__), 'blacklist_domains.json')
    
    try:
        with open(blacklist_path, 'r', encoding='utf-8') as f:
            domains = json.load(f)
        _blacklist_cache = set(domains)
        return _blacklist_cache
    except FileNotFoundError:
        logger.warning(f"[WARN] Файл черного списка не найден: {blacklist_path}")
        _blacklist_cache = set()
        return _blacklist_cache
    except Exception as e:
        logger.error(f"[ERROR] Ошибка при загрузке черного списка: {e}")
        _blacklist_cache = set()
        return _blacklist_cache


def is_url_blacklisted(url: str, blacklist: Set[str]) -> bool:
    """
    Проверяет, находится ли URL в черном списке
    
    Args:
        url: URL для проверки
        blacklist: Множество доменов из черного списка
    
    Returns:
        True если URL в черном списке, False иначе
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Убираем www. если есть
        domain_without_www = domain.replace('www.', '')
        
        # Проверяем точное совпадение и с www
        if domain in blacklist or domain_without_www in blacklist:
            return True
        
        # Проверяем поддомены (например, market.yandex.ru)
        for blacklist_domain in blacklist:
            if domain.endswith('.' + blacklist_domain) or domain == blacklist_domain:
                return True
        
        return False
    except Exception:
        return False


def parse_top_results(result_data: Dict, query: str) -> List[Dict[str, str]]:
    """
    Парсит результаты API в удобный формат
    
    Args:
        result_data: Данные результата от API
        query: Поисковый запрос
    
    Returns:
        Список ссылок с метаданными
    """
    if not result_data or query not in result_data:
        return []
    
    query_results = result_data[query]
    parsed_results = []
    
    for position, item in enumerate(query_results, 1):
        parsed_results.append({
            'position': position,
            'title': item.get('title', ''),
            'link': item.get('url', ''),
            'snippet': item.get('snippet', ''),
            'domain': item.get('domain', ''),
            'visible_url': item.get('visibleUrl', '')
        })
    
    return parsed_results


def extract_top_urls_from_queries(
    result_data: Dict,
    urls_per_query: int = 5
) -> List[str]:
    """
    Извлекает топ N URL от каждого запроса, убирает дубликаты и фильтрует по черному списку
    
    Args:
        result_data: Данные результата от API (должны содержать result.collect)
        urls_per_query: Количество URL для извлечения от каждого запроса (по умолчанию 5)
    
    Returns:
        Список уникальных URL (отфильтрованных по черному списку)
    """
    if not result_data or 'result' not in result_data:
        return []
    
    result = result_data.get('result', {})
    collect = result.get('collect', [])
    
    if not collect:
        return []
    
    # Загружаем черный список
    blacklist = load_blacklist_domains()
    
    # Собираем URL от каждого запроса
    all_urls = set()
    filtered_count = 0
    
    for query_results in collect:
        # collect содержит вложенные списки [[urls], [urls], ...]
        if isinstance(query_results, list) and len(query_results) > 0:
            urls_list = query_results[0] if isinstance(query_results[0], list) else query_results
            
            # Берем топ N URL от этого запроса
            for i, url in enumerate(urls_list):
                if i >= urls_per_query:
                    break
                if url:
                    # Проверяем черный список
                    if is_url_blacklisted(url, blacklist):
                        filtered_count += 1
                        continue
                    all_urls.add(url)
    
    if filtered_count > 0:
        logger.info(f"[INFO] Отфильтровано URL из черного списка: {filtered_count}")
    
    # Возвращаем список уникальных URL
    return list(all_urls)


async def get_top_results(
    queries: List[str],
    se_type: int = 1,
    region: int = 213,
    max_wait_time: int = 300,
    wait_per_query: int = 5,
    depth: int = 10,
    is_snippet: bool = False,
    noreask: bool = False,
    urls_per_query: Optional[int] = None,
) -> Union[Dict, List[str]]:
    """
    Возвращает сырые данные выдачи через API Arsenkin (check-top).
    
    Args:
        queries: Список поисковых запросов
        se_type: Тип поисковой системы
        region: ID региона (213 = Москва)
        max_wait_time: Максимальное время ожидания в секундах
        wait_per_query: Множитель времени ожидания на каждый запрос
        depth: Глубина выдачи
        is_snippet: Получать ли сниппеты
        noreask: Не перезапрашивать результаты
        urls_per_query: Если указан, возвращает топ N URL от каждого запроса (уникальные)
    
    Returns:
        Если urls_per_query указан - список уникальных URL
        Иначе - полный словарь с результатами от API

    se_type:
      1  = Яндекс XML
      2  = Яндекс Desktop
      3  = Яндекс Mobile
      11 = Google Desktop
      12 = Google Mobile
      20 = YouTube Desktop
      21 = YouTube Mobile
    """
    task_id = await create_task(
        queries=queries,
        se_type=se_type,
        region=region,
        depth=depth,
        is_snippet=is_snippet,
        noreask=noreask,
    )

    if not task_id:
        return {}

    # Интервал опроса зависит от числа запросов, чтобы реже дергать API
    interval = wait_per_query * max(1, len(queries))
    result_data = await wait_for_task(
        task_id,
        max_wait_time=max_wait_time,
        check_interval=interval,
    )
    
    if not result_data:
        return {}
    
    # Если указан urls_per_query, возвращаем только список уникальных URL
    if urls_per_query is not None:
        unique_urls = extract_top_urls_from_queries(result_data, urls_per_query=urls_per_query)
        return unique_urls
    
    return result_data


def save_results_to_json(results: Dict, filename: str = "jsontests/arsenkin_results.json") -> None:
    """
    Сохраняет результаты в JSON файл
    
    Args:
        results: Результаты поиска
        filename: Имя файла для сохранения (по умолчанию в jsontests/)
    """
    # Создаём директорию, если не существует
    import os
    os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else ".", exist_ok=True)
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info(f"Результаты сохранены в файл: {filename}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении файла: {e}")


if __name__ == "__main__":
    """
    Тестовый запуск
    se_type:
      1  = Яндекс XML
      2  = Яндекс Desktop
      3  = Яндекс Mobile
      11 = Google Desktop
      12 = Google Mobile
      20 = YouTube Desktop
      21 = YouTube Mobile
    """
    queries = [
        "автоматические ворота цена",
        "купить автоматические ворота",
        "автоматические ворота",
        "заказать ворота",
        "купить ворота цены",
        "ворота для дома"
    ]
    
    results = asyncio.run(get_top_results(
        queries=queries,
        se_type=3,
        region=2,
        max_wait_time=300,
        wait_per_query=10,
        is_snippet=False,
        urls_per_query=5
    ))
    
    if results:
        logger.info(f"Найдено уникальных URL: {len(results)}")
        logger.info("Список URL:")
        for i, url in enumerate(results, 1):
            logger.info(f"{i}. {url}")
        
        save_results_to_json(results, "jsontests/arsenkin_top_results.json")
    else:
        logger.warning("Не удалось получить результаты")
