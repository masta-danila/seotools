"""
Асинхронный клиент для XMLRiver API (Яндекс поиск).
Документация: https://xmlriver.com/apiydoc/apiy-about/
Способы сбора: https://xmlriver.com/api/api-alt/

ВАЖНО - Как работает XMLRiver API:
========================================
XMLRiver API работает в РЕЖИМЕ РЕАЛЬНОГО ВРЕМЕНИ:

1. Отправляем GET запрос с параметрами (query, region, device...)
2. Ждем ответ (обычно 3-6 секунд, максимум 1 минута)
3. Сразу получаем XML ответ с результатами поиска
4. Парсим XML и извлекаем URL

Ограничения XMLRiver (стандартный аккаунт):
- 10 потоков одновременно (max_concurrent=10)
- ~150 тысяч запросов в сутки по Яндексу
- НЕТ ограничения requests/minute (как у Arsenkin 30 req/min)
- Только ограничение по количеству одновременных потоков

Параллелизм:
- Контролируется через семафор (max_concurrent=10 для стандартного аккаунта)
- НЕТ rate_limiter - XMLRiver не имеет ограничений по requests/minute
"""
import os
import sys
import json
import asyncio
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Set
from urllib.parse import urlparse, quote
from pathlib import Path
from dotenv import load_dotenv
import httpx

# Добавляем корень проекта в путь для импорта
sys.path.insert(0, str(Path(__file__).parent.parent))

from logger_config import get_search_logger
from xmlriver.single_search import search_yandex

logger = get_search_logger()

# Загружаем переменные окружения из корня проекта
load_dotenv()

# Кэш для черного списка доменов
_blacklist_cache: Optional[Set[str]] = None


def load_blacklist_domains() -> Set[str]:
    """Загружает черный список доменов из JSON файла"""
    global _blacklist_cache
    
    if _blacklist_cache is not None:
        return _blacklist_cache
    
    # Ищем файл в папке xmlriver
    blacklist_file = Path(__file__).parent / "blacklist_domains.json"
    
    if not blacklist_file.exists():
        logger.warning(f"[WARN] Файл черного списка не найден: {blacklist_file}")
        _blacklist_cache = set()
        return _blacklist_cache
    
    try:
        with open(blacklist_file, 'r', encoding='utf-8') as f:
            domains_list = json.load(f)
        
        # Конвертируем в set и приводим к нижнему регистру
        domains = {domain.strip().lower() for domain in domains_list if domain.strip()}
        _blacklist_cache = domains
        logger.info(f"[OK] Загружено {len(domains)} доменов в черный список из {blacklist_file.name}")
        return domains
    except Exception as e:
        logger.error(f"[ERROR] Ошибка при загрузке черного списка: {e}")
        _blacklist_cache = set()
        return _blacklist_cache


def is_domain_blacklisted(url: str) -> bool:
    """
    Проверяет, находится ли домен URL в черном списке.
    Учитывает поддомены: m.avito.ru → avito.ru
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        blacklist = load_blacklist_domains()
        
        # Проверяем полный домен (с поддоменом)
        if domain in blacklist:
            return True
        
        # Извлекаем основной домен (второго уровня)
        # Примеры: m.avito.ru → avito.ru, www.ozon.ru → ozon.ru
        parts = domain.split('.')
        if len(parts) >= 2:
            # Берем последние 2 части (домен + зона)
            main_domain = '.'.join(parts[-2:])
            if main_domain in blacklist:
                return True
        
        return False
    except Exception:
        return False


def parse_yandex_xml(xml_data: str, urls_per_query: int = 10, debug: bool = False) -> List[str]:
    """
    Парсит XML ответ от XMLRiver и извлекает URL из результатов поиска.
    
    Args:
        xml_data: XML строка с результатами
        urls_per_query: Количество URL для извлечения
        debug: Включить детальное логирование для отладки
    
    Returns:
        Список URL из органической выдачи
    """
    if not xml_data:
        logger.warning("[WARN] parse_yandex_xml: пустой xml_data")
        return []
    
    try:
        root = ET.fromstring(xml_data)
        
        if debug:
            logger.debug(f"[DEBUG] XML root tag: {root.tag}")
            logger.debug(f"[DEBUG] XML root attrib: {root.attrib}")
        
        # Проверяем на ошибки в ответе
        error_elem = root.find('.//error')
        if error_elem is not None:
            error_code = error_elem.get('code', 'UNKNOWN')
            error_text = error_elem.text or 'No error message'
            logger.error(f"[ERROR] XMLRiver API вернул ошибку: {error_code} - {error_text}")
            return []
        
        # XMLRiver возвращает результаты в <response><results><grouping><group><doc>
        urls = []
        blacklisted_count = 0
        
        # Ищем все элементы doc
        docs = root.findall('.//doc')
        
        if debug:
            logger.debug(f"[DEBUG] Найдено элементов <doc>: {len(docs)}")
        
        if len(docs) == 0:
            logger.warning("[WARN] Не найдено элементов <doc> в XML")
            
            if debug:
                # Детальное логирование только в debug режиме
                logger.warning(f"[WARN] XML начало: {xml_data[:500]}")
                all_elements = [elem.tag for elem in root.iter()]
                logger.warning(f"[WARN] Найдены XML элементы: {set(all_elements)}")
        
        for doc in docs:
            # URL находится в <url>
            url_elem = doc.find('url')
            if url_elem is not None and url_elem.text:
                url = url_elem.text.strip()
                
                # Пропускаем blacklisted домены
                if is_domain_blacklisted(url):
                    blacklisted_count += 1
                    if debug:
                        logger.debug(f"[DEBUG] Пропущен blacklisted: {url}")
                    continue
                
                urls.append(url)
                
                if len(urls) >= urls_per_query:
                    break
        
        if blacklisted_count > 0:
            logger.debug(f"[DEBUG] Отфильтровано {blacklisted_count} URL из blacklist")
        
        logger.debug(f"[DEBUG] Извлечено {len(urls)} URL из XML")
        return urls
    
    except ET.ParseError as e:
        logger.error(f"[ERROR] parse_yandex_xml: ошибка парсинга XML - {e}")
        logger.error(f"[ERROR] XML начало: {xml_data[:300]}")
        return []
    except Exception as e:
        logger.error(f"[ERROR] parse_yandex_xml: неожиданная ошибка - {e}")
        return []


async def process_url(
    url: str,
    url_data: Dict,
    default_region: int = 213,
    urls_per_query: int = 10,
    device: str = "mobile",
    domain: str = "ru",
    lang: str = "ru",
    max_concurrent: int = 10,
) -> Dict:
    """
    Обрабатывает один URL: делает запрос по queries и добавляет отфильтрованные URL
    
    Args:
        url: URL страницы
        url_data: Данные URL (queries, company_name, region и т.д.)
        default_region: ID региона по умолчанию (если не указан в url_data)
        urls_per_query: Количество URL для извлечения от каждого запроса
        device: Устройство (desktop, tablet, mobile)
        domain: Домен Яндекса (ru, com, ua...)
        lang: Язык (ru, uk, en...)
        max_concurrent: Максимальное количество одновременных запросов
    
    Returns:
        Словарь с исходными данными + filtered_urls
    """
    queries = url_data.get('queries', [])
    
    if not queries:
        logger.info(f"[SKIP] Пропущен {url}: нет запросов")
        return {**url_data, 'filtered_urls': []}
    
    # Берём region из данных URL, если есть, иначе используем дефолтный
    region = url_data.get('region', default_region)
    
    logger.info(f"[PROCESS] Обработка {url} ({len(queries)} запросов, топ-{urls_per_query} от каждого, регион: {region})...")
    
    try:
        result = await get_top_results(
            queries=queries,
            region=region,
            urls_per_query=urls_per_query,
            device=device,
            domain=domain,
            lang=lang,
            max_concurrent=max_concurrent,
        )
        
        # Результат - список уникальных URL
        if result and isinstance(result, list):
            filtered_urls = result
            logger.info(f"[OK] {url}: найдено {len(filtered_urls)} уникальных конкурентов")
        else:
            filtered_urls = []
            logger.warning(f"[WARN] {url}: конкуренты не найдены")
        
        return {**url_data, 'filtered_urls': filtered_urls}
    
    except Exception as e:
        logger.error(f"[ERROR] Ошибка при обработке {url}: {e}")
        return {**url_data, 'filtered_urls': []}


async def process_sheets_data(
    sheets_data: Dict,
    default_region: int = 213,
    urls_per_query: int = 10,
    device: str = "mobile",
    domain: str = "ru",
    lang: str = "ru",
    max_concurrent: int = 10,
    task_start_delay: float = 0.0,
) -> Dict:
    """
    Обрабатывает все URL из sheets_data асинхронно через XMLRiver API.
    
    ОПТИМИЗИРОВАННАЯ ВЕРСИЯ:
    1. Собирает ВСЕ запросы из всех URL
    2. Обрабатывает их параллельно (до max_concurrent одновременно)
    3. Распределяет результаты обратно по URL
    
    Принимает структуру sheets_data.json и возвращает структуру search_batch_results.json.
    
    Args:
        sheets_data: Словарь с данными из Google Sheets (каждый URL может иметь свой region)
        default_region: ID региона по умолчанию (если не указан в данных URL)
        urls_per_query: Количество URL для извлечения от каждого запроса
        device: Устройство (desktop, tablet, mobile)
        domain: Домен Яндекса (ru, com, ua...)
        lang: Язык (ru, uk, en...)
        max_concurrent: Максимальное количество одновременных запросов XMLRiver (10 для стандартного аккаунта)
        task_start_delay: Задержка между стартами задач (в секундах)
    
    Returns:
        Обновлённый словарь с добавленными filtered_urls для каждого URL
    """
    # Шаг 1: Собираем ВСЕ запросы из всех URL
    all_queries = []
    query_to_urls = {}  # Маппинг: запрос → список URL, которым он нужен
    url_regions = {}  # Маппинг: URL → region
    
    for spreadsheet_id, spreadsheet_info in sheets_data.items():
        urls_dict = spreadsheet_info.get('urls', {})
        for url, url_data in urls_dict.items():
            queries = url_data.get('queries', [])
            region = url_data.get('region', default_region)
            url_regions[url] = region
            
            for query in queries:
                if query not in all_queries:
                    all_queries.append(query)
                
                if query not in query_to_urls:
                    query_to_urls[query] = []
                query_to_urls[query].append(url)
    
    logger.info(f"[STEP 1] Собрано {len(all_queries)} уникальных запросов из {sum(len(si.get('urls', {})) for si in sheets_data.values())} URL")
    
    # Шаг 2: Обрабатываем все запросы параллельно (до max_concurrent одновременно)
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_query_with_semaphore(query: str, query_index: int, total_queries: int) -> tuple:
        """Обрабатывает один запрос с контролем через семафор"""
        if task_start_delay > 0 and query_index > 0:
            await asyncio.sleep(task_start_delay * query_index)
        
        async with semaphore:
            logger.info(f"[QUERY {query_index}/{total_queries}] Запрос: '{query}'")
            
            # Определяем region (берем из первого URL, которому нужен этот запрос)
            first_url = query_to_urls[query][0]
            region = url_regions.get(first_url, default_region)
            
            # Получаем результаты для запроса
            xml_data = await search_yandex(
                query=query,
                region=region,
                groupby=urls_per_query,
                page=0,
                device=device,
                domain=domain,
                lang=lang,
            )
            
            if xml_data:
                # Парсим XML и извлекаем URL
                urls = parse_yandex_xml(xml_data, urls_per_query)
                logger.info(f"[QUERY {query_index}/{total_queries}] Найдено {len(urls)} URL")
                return query, urls
            else:
                logger.warning(f"[QUERY {query_index}/{total_queries}] Не получены данные")
                return query, []
    
    # Создаём задачи для всех запросов
    tasks = []
    for query_index, query in enumerate(all_queries, 1):
        task = process_query_with_semaphore(query, query_index, len(all_queries))
        tasks.append(task)
    
    logger.info(f"[STEP 2] Запуск обработки {len(tasks)} запросов (макс. {max_concurrent} одновременно)")
    
    # Выполняем все задачи параллельно
    results = await asyncio.gather(*tasks)
    
    # Создаём маппинг: запрос → список URL из результатов
    query_results = {}
    for query, urls in results:
        query_results[query] = urls
    
    logger.info(f"[STEP 2] Обработка запросов завершена!")
    
    # Шаг 3: Распределяем результаты обратно по URL
    result_data = {}
    
    for spreadsheet_id, spreadsheet_info in sheets_data.items():
        urls_dict = spreadsheet_info.get('urls', {})
        
        for url, url_data in urls_dict.items():
            # Собираем все конкурентов для этого URL
            filtered_urls_set = set()
            
            for query in url_data.get('queries', []):
                if query in query_results:
                    filtered_urls_set.update(query_results[query])
            
            # Добавляем filtered_urls в результат
            if spreadsheet_id not in result_data:
                result_data[spreadsheet_id] = {'urls': {}}
            
            result_data[spreadsheet_id]['urls'][url] = {
                **url_data,
                'filtered_urls': list(filtered_urls_set)
            }
            
            logger.debug(f"[URL] {url}: {len(filtered_urls_set)} уникальных конкурентов")
    
    logger.info(f"[STEP 3] Результаты распределены по {sum(len(si.get('urls', {})) for si in result_data.values())} URL")
    logger.info("Обработка завершена!")
    
    return result_data


async def get_top_results(
    queries: List[str],
    region: int = 213,
    urls_per_query: int = 10,
    device: str = "mobile",
    domain: str = "ru",
    lang: str = "ru",
    max_concurrent: int = 10,
) -> List[str]:
    """
    Получает топ результатов для списка запросов через XMLRiver API параллельно.
    
    Это основная публичная функция для получения конкурентов по запросам.
    
    ВАЖНО: XMLRiver API работает в режиме реального времени:
    - Отправляем GET запрос → ждем ответ (3-6 сек, макс. 1 мин)
    - НЕТ очереди задач (в отличие от Arsenkin API)
    - НЕТ опроса статуса - просто ждем ответ на HTTP запрос
    
    Ограничения XMLRiver:
    - 10 потоков одновременно (стандартный аккаунт)
    - ~150 тысяч запросов в сутки
    - НЕТ ограничения requests/minute (только количество потоков)
    
    Параллелизм контролируется только через семафор (max_concurrent).
    НЕТ rate_limiter - XMLRiver не имеет лимита запросов в минуту.
    
    Args:
        queries: Список поисковых запросов
        region: ID региона Яндекса (213 = Москва)
        urls_per_query: Количество URL для извлечения от каждого запроса
        device: Устройство (desktop, tablet, mobile)
        domain: Домен Яндекса (ru, com, ua...)
        lang: Язык (ru, uk, en...)
        max_concurrent: Максимальное количество одновременных запросов (по умолчанию 10)
    
    Returns:
        Список уникальных URL из всех запросов
        
    Example:
        queries = ["купить телефон", "смартфон недорого"]
        result = await get_top_results(
            queries=queries,
            region=213,
            urls_per_query=10,
            max_concurrent=10
        )
        # result = ["https://example.com", "https://test.com", ...]
    """
    if not queries:
        logger.warning("[WARN] Пустой список запросов")
        return []
    
    logger.info(f"[START] Обработка {len(queries)} запросов через XMLRiver API (макс. {max_concurrent} одновременно)")
    
    # Создаём семафор для ограничения одновременных запросов
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_query_with_semaphore(query: str, query_index: int, total_queries: int) -> List[str]:
        """Обрабатывает один запрос с контролем через семафор"""
        async with semaphore:
            logger.info(f"[QUERY {query_index}/{total_queries}] Запрос: '{query}'")
            
            # Получаем результаты для запроса (синхронно - один GET запрос → один XML ответ)
            xml_data = await search_yandex(
                query=query,
                region=region,
                groupby=urls_per_query,
                page=0,
                device=device,
                domain=domain,
                lang=lang,
            )
            
            if xml_data:
                # Сохраняем примеры XML для отладки (первые 3 запроса)
                if query_index <= 3:
                    try:
                        debug_dir = Path(__file__).parent.parent / "jsontests" / "xml_debug"
                        debug_dir.mkdir(exist_ok=True)
                        
                        # Безопасное имя файла из запроса
                        safe_query = query.replace(' ', '_').replace('/', '_')[:50]
                        filename = f"query_{query_index:02d}_{safe_query}.xml"
                        
                        with open(debug_dir / filename, 'w', encoding='utf-8') as f:
                            f.write(xml_data)
                        logger.debug(f"[DEBUG] Сохранен XML: xml_debug/{filename}")
                    except Exception as e:
                        logger.debug(f"[DEBUG] Не удалось сохранить XML: {e}")
                
                # Парсим XML и извлекаем URL (с debug режимом для первых 3 запросов)
                urls = parse_yandex_xml(xml_data, urls_per_query, debug=(query_index <= 3))
                logger.info(f"[QUERY {query_index}/{total_queries}] Найдено {len(urls)} URL")
                return urls
            else:
                logger.warning(f"[QUERY {query_index}/{total_queries}] Не получены данные")
                return []
    
    # Создаём задачи для всех запросов
    tasks = []
    for query_index, query in enumerate(queries, 1):
        task = process_query_with_semaphore(query, query_index, len(queries))
        tasks.append(task)
    
    # Выполняем все задачи параллельно
    results = await asyncio.gather(*tasks)
    
    # Собираем все уникальные URL
    all_urls: Set[str] = set()
    for urls_list in results:
        all_urls.update(urls_list)
    
    result = list(all_urls)
    logger.info(f"[OK] Всего найдено {len(result)} уникальных URL из {len(queries)} запросов")
    
    return result


def save_results_to_json(results: Dict, filename: str = "jsontests/xmlriver_batch_results.json") -> None:
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
        logger.info(f"Результаты сохранены в файл: {filename}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении файла: {e}")


if __name__ == "__main__":
    """
    Тестовый запуск - обрабатывает ВСЕ URL из sheets_data.json
    и создает структуру как в search_batch_results.json
    """
    # Загружаем данные из sheets_data.json
    logger.info("[TEST] Загрузка данных из jsontests/sheets_data.json...")
    with open("jsontests/sheets_data.json", 'r', encoding='utf-8') as f:
        sheets_data = json.load(f)
    
    # Подсчитываем статистику
    total_urls = 0
    total_queries = 0
    
    for spreadsheet_id, spreadsheet_info in sheets_data.items():
        urls_dict = spreadsheet_info.get('urls', {})
        total_urls += len(urls_dict)
        
        for url, url_data in urls_dict.items():
            queries = url_data.get('queries', [])
            total_queries += len(queries)
    
    logger.info(f"[TEST] Найдено {total_urls} URL с {total_queries} запросами")
    
    if total_urls == 0:
        logger.error("[TEST] Не найдено URL для обработки!")
    else:
        # Обрабатываем все URL через XMLRiver API
        results = asyncio.run(process_sheets_data(
            sheets_data=sheets_data,
            default_region=213,
            urls_per_query=5,  # Топ-10 от каждого запроса
            device="mobile",
            domain="ru",
            lang="ru",
            max_concurrent=10,  # До 10 запросов одновременно (стандартный аккаунт)
            task_start_delay=0.0,  # Нет задержки, т.к. нет rate limiter
        ))
        
        # Сохраняем результаты
        if results:
            save_results_to_json(results, "jsontests/xmlriver_batch_results.json")
            
            # Выводим статистику
            total_competitors = 0
            for spreadsheet_id, spreadsheet_info in results.items():
                urls_dict = spreadsheet_info.get('urls', {})
                for url, url_data in urls_dict.items():
                    filtered_urls = url_data.get('filtered_urls', [])
                    total_competitors += len(filtered_urls)
                    logger.info(f"[TEST] {url}: {len(filtered_urls)} конкурентов")
            
            logger.info(f"[TEST] Итого найдено {total_competitors} конкурентов для {total_urls} URL")
        else:
            logger.error("[TEST] Не получено результатов!")
