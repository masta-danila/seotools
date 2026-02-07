"""
Асинхронный клиент для API Arsenkin (инструмент check-h - парсинг Title и Description).
Документация: https://help.arsenkin.ru/api/api-check-h
"""
import os
import sys
import json
import asyncio
from typing import List, Dict, Optional
from pathlib import Path
from dotenv import load_dotenv
import httpx

# Добавляем корень проекта в путь для импорта
sys.path.insert(0, str(Path(__file__).parent.parent))

from logger_config import get_parser_logger
from rate_limiter import get_rate_limiter

logger = get_parser_logger()

# Получаем глобальный rate limiter
_rate_limiter = get_rate_limiter()

# Загружаем переменные окружения из корня проекта
load_dotenv()

# API endpoints (согласно документации https://help.arsenkin.ru/api)
API_SET_URL = "https://arsenkin.ru/api/tools/set"
API_CHECK_URL = "https://arsenkin.ru/api/tools/check"
API_GET_URL = "https://arsenkin.ru/api/tools/get"


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


async def create_task_by_urls(
    urls: List[str],
    foreign: bool = False,
    max_retries: int = 3,
) -> Optional[int]:
    """
    Создаёт задачу на парсинг мета-тегов по списку URL (инструмент check-h).
    
    Args:
        urls: Список URL для парсинга
        foreign: Флаг для иностранных сайтов (по умолчанию False)
        max_retries: Максимальное количество повторных попыток при 429 ошибке
    
    Returns:
        ID задачи или None в случае ошибки
    """
    payload = {
        "tools_name": "check-h",
        "data": {
            "pause": 1,  # Минимальная пауза, т.к. ограничение по количеству запросов, а не по времени
            "foreign": foreign,
            "mode": "url",
            "queries": urls,
        },
    }
    
    logger.debug(f"[DEBUG] create_task_by_urls: отправка {len(urls)} URL")
    logger.debug(f"[DEBUG] create_task_by_urls: первые 2 URL: {urls[:2]}")

    for attempt in range(max_retries):
        try:
            # Ждём разрешения от rate limiter
            await _rate_limiter.acquire()
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(API_SET_URL, headers=get_headers(), json=payload)
            
            logger.debug(f"[DEBUG] create_task_by_urls: status_code={response.status_code}")
            
            # Обработка 429 (Too Many Requests)
            if response.status_code == 429:
                wait_time = 60 * (attempt + 1)  # 60, 120, 180 секунд
                logger.warning(f"[WARN] Rate limit (429). Попытка {attempt + 1}/{max_retries}. Ожидание {wait_time} сек...")
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f"[ERROR] Превышено максимальное количество попыток при rate limit")
                    return None
            
            response.raise_for_status()

            data = response.json()
            logger.debug(f"[DEBUG] create_task_by_urls: response data={data}")
            task_id = data.get("task_id")
            if task_id:
                logger.debug(f"[DEBUG] create_task_by_urls: успешно создана задача task_id={task_id}")
                return task_id
            else:
                logger.error(f"[ERROR] create_task_by_urls: в ответе нет task_id")
                return None

        except httpx.RequestError as e:
            logger.error(f"[ERROR] create_task_by_urls: RequestError - {e}")
            return None
        except Exception as e:
            logger.error(f"[ERROR] create_task_by_urls: Exception - {type(e).__name__}: {e}")
            return None
    
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


def parse_h_results(result_data: Dict) -> Dict[str, Dict[str, str]]:
    """
    Парсит результаты API check-h в словарь {url: {title, description}}
    
    Args:
        result_data: Данные результата от API (ожидается структура {"result": [...]})
    
    Returns:
        Словарь где ключ - URL, значение - словарь с title и description
    """
    if not result_data:
        return {}
    
    # API возвращает {"result": [...]} - извлекаем список
    items = result_data.get('result', [])
    if not isinstance(items, list):
        return {}
    
    parsed_results = {}
    
    for item in items:
        if not isinstance(item, dict):
            continue
        
        url = item.get('url', '')
        if url:
            parsed_results[url] = {
                'title': item.get('title', ''),
                'description': item.get('description', ''),
            }
    
    return parsed_results


async def get_h_tags_by_urls(
    urls: List[str],
    foreign: bool = False,
    max_wait_time: int = 300,
    wait_per_url: int = 5,
) -> Dict[str, Dict[str, str]]:
    """
    Возвращает мета-теги (Title и description) для списка URL через API Arsenkin.
    
    Args:
        urls: Список URL для парсинга
        foreign: Флаг для иностранных сайтов
        max_wait_time: Максимальное время ожидания выполнения задачи
        wait_per_url: Время ожидания на каждый URL в секундах (по умолчанию 5)
    
    Returns:
        Словарь {url: {title, description}}
    """
    task_id = await create_task_by_urls(
        urls=urls,
        foreign=foreign,
    )

    if not task_id:
        logger.error(f"[ERROR] Не удалось создать задачу в Arsenkin API")
        return {}

    # Интервал опроса зависит от числа URL'ов, чтобы реже дергать API
    interval = wait_per_url * max(1, len(urls))
    result_data = await wait_for_task(
        task_id,
        max_wait_time=max_wait_time,
        check_interval=interval,
    )
    
    if not result_data:
        logger.error(f"[ERROR] Не получены данные от Arsenkin API (task_id: {task_id})")
        return {}
    
    # Парсируем результат в словарь {url: {title, description}}
    parsed = parse_h_results(result_data)
    logger.debug(f"[DEBUG] parse_h_results вернул {len(parsed)} записей")
    return parsed


def save_results_to_json(results: Dict, filename: str = "jsontests/arsenkin_h_results.json") -> None:
    """
    Сохраняет результаты в JSON файл
    
    Args:
        results: Результаты парсинга (словарь {url: {title, description}})
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


async def process_batch_results_with_metatags(
    batch_data: Dict,
    foreign: bool = False,
    max_wait_time: int = 300,
    wait_per_url: int = 2,
) -> Dict:
    """
    Обрабатывает словарь из search_batch_results.json, извлекает все filtered_urls,
    получает для них метатеги и добавляет в структуру
    
    Args:
        batch_data: Словарь из search_batch_results.json
        foreign: Флаг для иностранных сайтов
        max_wait_time: Максимальное время ожидания
        wait_per_url: Время ожидания на каждый URL
    
    Returns:
        Обновленный словарь с метатегами для каждого filtered_url
    """
    # Собираем все уникальные URL из filtered_urls
    all_urls = set()
    for spreadsheet_id, spreadsheet_info in batch_data.items():
        urls_dict = spreadsheet_info.get('urls', {})
        for url, url_data in urls_dict.items():
            filtered_urls = url_data.get('filtered_urls', [])
            all_urls.update(filtered_urls)
    
    all_urls = list(all_urls)
    
    if not all_urls:
        logger.warning("[WARN] Не найдено filtered_urls для обработки")
        return batch_data
    
    logger.info(f"[PROCESS] Получение метатегов для {len(all_urls)} URL...")
    logger.debug(f"[DEBUG] Первые 3 URL: {all_urls[:3]}")
    
    # Получаем метатеги для всех URL
    metatags = await get_h_tags_by_urls(
        urls=all_urls,
        foreign=foreign,
        max_wait_time=max_wait_time,
        wait_per_url=wait_per_url,
    )
    
    logger.info(f"[OK] Получено метатегов: {len(metatags)}")
    if metatags:
        first_url = list(metatags.keys())[0]
        logger.debug(f"[DEBUG] Пример метатегов для {first_url}: {metatags[first_url]}")
    else:
        logger.warning(f"[WARN] Словарь metatags пустой!")
    
    # Обновляем batch_data: заменяем filtered_urls на список словарей с метатегами
    for spreadsheet_id, spreadsheet_info in batch_data.items():
        urls_dict = spreadsheet_info.get('urls', {})
        for url, url_data in urls_dict.items():
            filtered_urls = url_data.get('filtered_urls', [])
            
            # Преобразуем список URL в список словарей с метатегами
            filtered_with_meta = []
            for filtered_url in filtered_urls:
                meta = metatags.get(filtered_url, {})
                filtered_with_meta.append({
                    'url': filtered_url,
                    'title': meta.get('title', ''),
                    'description': meta.get('description', ''),
                })
            
            url_data['filtered_urls'] = filtered_with_meta
    
    return batch_data


if __name__ == "__main__":
    """
    Тестовый запуск
    """
    # Загружаем данные
    with open("jsontests/step2_search_results.json", 'r', encoding='utf-8') as f:
        batch_data = json.load(f)
    
    # Обрабатываем
    results = asyncio.run(process_batch_results_with_metatags(
        batch_data=batch_data,
        foreign=False,
        max_wait_time=300,
        wait_per_url=2,
    ))
    
    # Сохраняем
    if results:
        save_results_to_json(results, "jsontests/arsenkin_h_results.json")
