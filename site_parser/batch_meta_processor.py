"""
Batch обработка URL для извлечения метатегов
"""
import json
import asyncio
import time
import sys
import warnings
from typing import Dict, List, Set
from urllib.parse import urlparse
from pathlib import Path
import httpx

# Подавляем предупреждения SSL
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

# Добавляем корень проекта в путь для импорта
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from .html_parser import parse_for_ml
    from .meta_extractor import extract_meta
    from logger_config import get_batch_meta_logger
    logger = get_batch_meta_logger()
except ImportError:
    # Если запускаем напрямую, используем абсолютные импорты
    from site_parser.html_parser import parse_for_ml
    from site_parser.meta_extractor import extract_meta
    from logger_config import get_batch_meta_logger
    logger = get_batch_meta_logger()


class DomainRateLimiter:
    """Контролирует паузы между запросами к одному домену"""
    
    def __init__(self, delay_seconds: float = 1.0):
        self.delay_seconds = delay_seconds
        self.last_request_time: Dict[str, float] = {}
        self._lock = asyncio.Lock()
    
    def get_domain(self, url: str) -> str:
        """Извлекает домен из URL"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            # Убираем www.
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except:
            return url
    
    async def wait_if_needed(self, url: str):
        """Ждет, если нужно, перед запросом к домену"""
        domain = self.get_domain(url)
        
        async with self._lock:
            if domain in self.last_request_time:
                elapsed = time.time() - self.last_request_time[domain]
                if elapsed < self.delay_seconds:
                    wait_time = self.delay_seconds - elapsed
                    await asyncio.sleep(wait_time)
            
            self.last_request_time[domain] = time.time()


async def process_single_url(
    url: str,
    rate_limiter: DomainRateLimiter,
    http_client,
    url_index: int,
    total_urls: int
) -> Dict:
    """
    Обрабатывает один URL: парсит HTML и извлекает метатеги
    
    Args:
        url: URL для обработки
        rate_limiter: Контроллер пауз между запросами
        http_client: httpx.AsyncClient для переиспользования соединений
        url_index: Индекс URL (для логирования)
        total_urls: Общее количество URL
        
    Returns:
        Словарь с метатегами или None при ошибке
    """
    # Ждем, если нужно (пауза между запросами к одному домену)
    await rate_limiter.wait_if_needed(url)
    
    logger.info(f"[{url_index}/{total_urls}] Обработка: {url}")
    
    try:
        # Парсим HTML (передаем клиент для переиспользования)
        parsed_data = await parse_for_ml(url, client=http_client)
        
        if not parsed_data:
            logger.warning(f"[{url_index}/{total_urls}] Ошибка парсинга: {url}")
            return None
        
        # Извлекаем метатеги
        html_structure = parsed_data.get('html_structure', '')
        meta_tags = extract_meta(html_structure)
        
        logger.info(f"[{url_index}/{total_urls}] Успешно: {url}")
        logger.debug(f"    Title: {meta_tags['title'][:50] if meta_tags['title'] else 'N/A'}...")
        logger.debug(f"    H1: {meta_tags['h1'][:50] if meta_tags['h1'] else 'N/A'}...")
        
        return meta_tags
        
    except Exception as e:
        logger.error(f"[{url_index}/{total_urls}] Ошибка: {url} - {e}")
        return None


async def process_batch_urls(
    batch_data: Dict,
    max_concurrent: int = 5,
    domain_delay: float = 1.0
) -> Dict:
    """
    Обрабатывает все уникальные filtered_urls из batch_data
    
    Args:
        batch_data: Словарь из xmlriver_batch_results.json
        max_concurrent: Максимальное количество одновременных запросов
        domain_delay: Пауза между запросами к одному домену (в секундах)
        
    Returns:
        Обновленный словарь с метатегами для каждого filtered_url
    """
    logger.info("="*60)
    logger.info("Параметры обработки:")
    logger.info(f"  - Максимум потоков: {max_concurrent}")
    logger.info(f"  - Пауза между запросами к домену: {domain_delay}s")
    logger.info("="*60)
    
    # Шаг 1: Собираем все уникальные filtered_urls
    all_filtered_urls: Set[str] = set()
    
    for spreadsheet_id, spreadsheet_info in batch_data.items():
        urls_dict = spreadsheet_info.get('urls', {})
        for main_url, url_data in urls_dict.items():
            filtered_urls = url_data.get('filtered_urls', [])
            for item in filtered_urls:
                # Поддерживаем два формата: строки и словари
                if isinstance(item, str):
                    all_filtered_urls.add(item)
                elif isinstance(item, dict):
                    url = item.get('url')
                    if url:
                        all_filtered_urls.add(url)
    
    unique_urls = list(all_filtered_urls)
    logger.info(f"[STEP 1] Собрано {len(unique_urls)} уникальных URL для обработки")
    
    if not unique_urls:
        logger.warning("Нет URL для обработки")
        return batch_data
    
    # Шаг 2: Обрабатываем все URL параллельно
    logger.info(f"[STEP 2] Запуск обработки (макс. {max_concurrent} одновременно)...")
    
    semaphore = asyncio.Semaphore(max_concurrent)
    rate_limiter = DomainRateLimiter(delay_seconds=domain_delay)
    
    # Создаем один общий HTTP клиент с увеличенным лимитом соединений
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    # Увеличиваем лимиты соединений для поддержки большого числа потоков
    limits = httpx.Limits(
        max_connections=max_concurrent * 2,  # Общее количество соединений
        max_keepalive_connections=max_concurrent,  # Keep-alive соединения
    )
    
    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        verify=False,  # Отключаем проверку SSL
        headers=headers,
        limits=limits
    ) as http_client:
        
        async def process_with_semaphore(url: str, url_index: int):
            async with semaphore:
                return await process_single_url(url, rate_limiter, http_client, url_index, len(unique_urls))
        
        # Создаем задачи для всех URL
        tasks = []
        for url_index, url in enumerate(unique_urls, 1):
            task = process_with_semaphore(url, url_index)
            tasks.append(task)
        
        # Выполняем все задачи параллельно
        results = await asyncio.gather(*tasks)
    
    # Создаем маппинг: URL -> метатеги
    url_to_meta = {}
    successful_count = 0
    for url, meta_tags in zip(unique_urls, results):
        if meta_tags:
            url_to_meta[url] = meta_tags
            successful_count += 1
    
    logger.info("[STEP 2] Обработка завершена!")
    logger.info(f"  - Успешно: {successful_count}/{len(unique_urls)}")
    logger.info(f"  - Ошибок: {len(unique_urls) - successful_count}")
    
    # Шаг 3: Добавляем метатеги обратно в batch_data
    logger.info("[STEP 3] Добавление метатегов в результат...")
    
    result_data = {}
    
    for spreadsheet_id, spreadsheet_info in batch_data.items():
        urls_dict = spreadsheet_info.get('urls', {})
        
        result_urls = {}
        for main_url, url_data in urls_dict.items():
            filtered_urls = url_data.get('filtered_urls', [])
            
            # Обновляем каждый filtered_url метатегами
            updated_filtered_urls = []
            for item in filtered_urls:
                if isinstance(item, str):
                    # Формат: простая строка URL
                    if item in url_to_meta:
                        # Преобразуем в словарь с метатегами
                        updated_data = {
                            'url': item,
                            'meta': url_to_meta[item]
                        }
                        updated_filtered_urls.append(updated_data)
                    else:
                        # Оставляем как строку (если не удалось спарсить)
                        updated_filtered_urls.append(item)
                elif isinstance(item, dict):
                    # Формат: словарь с ключом 'url'
                    url = item.get('url')
                    if url and url in url_to_meta:
                        # Добавляем метатеги
                        updated_data = {
                            **item,
                            'meta': url_to_meta[url]
                        }
                        updated_filtered_urls.append(updated_data)
                    else:
                        # Оставляем без изменений
                        updated_filtered_urls.append(item)
                else:
                    updated_filtered_urls.append(item)
            
            result_urls[main_url] = {
                **url_data,
                'filtered_urls': updated_filtered_urls
            }
        
        result_data[spreadsheet_id] = {
            **spreadsheet_info,
            'urls': result_urls
        }
    
    logger.info("[STEP 3] Метатеги добавлены!")
    
    return result_data


def save_results_to_json(results: Dict, filename: str = "jsontests/xmlriver_batch_results_with_meta.json"):
    """
    Сохраняет результаты в JSON файл
    
    Args:
        results: Результаты обработки
        filename: Имя файла для сохранения
    """
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
    Тестовый запуск - обрабатывает URL из xmlriver_batch_results.json
    """
    # Загружаем данные
    input_file = "jsontests/xmlriver_batch_results.json"
    logger.info(f"Загрузка данных из {input_file}...")
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            batch_data = json.load(f)
        
        logger.info("Данные загружены")
        
        # Обрабатываем
        results = asyncio.run(process_batch_urls(
            batch_data=batch_data,
            max_concurrent=100,      # До 5 URL одновременно
            domain_delay=2,      # 2 секунды между запросами к одному домену
        ))
        
        # Сохраняем результат
        output_file = "jsontests/xmlriver_batch_results_with_meta.json"
        save_results_to_json(results, output_file)
        
        # Статистика
        logger.info("="*60)
        logger.info("Готово! Результаты сохранены в:")
        logger.info(f"  {output_file}")
        logger.info("="*60)
        
    except FileNotFoundError:
        logger.error(f"Файл не найден: {input_file}")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
