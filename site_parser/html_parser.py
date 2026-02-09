"""
Парсер статей с использованием BeautifulSoup и httpx (асинхронный)
"""
import json
import os
import sys
import asyncio
import warnings
import httpx
from pathlib import Path
from bs4 import BeautifulSoup

# Добавляем корень проекта в путь для импорта
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from logger_config import get_html_parser_logger
    logger = get_html_parser_logger()
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# Подавляем предупреждения SSL
warnings.filterwarnings('ignore', message='Unverified HTTPS request')


def save_to_json(data, filename=None, output_dir="jsontests"):
    """
    Сохраняет результаты парсинга в JSON файл
    
    Args:
        data: Словарь с данными для сохранения
        filename: Имя файла (по умолчанию parse_result.json)
        output_dir: Директория для сохранения (по умолчанию jsontests)
        
    Returns:
        Путь к сохранённому файлу
    """
    # Создаём директорию, если не существует
    os.makedirs(output_dir, exist_ok=True)
    
    # Используем фиксированное имя файла
    if not filename:
        filename = "parse_result.json"
    
    filepath = os.path.join(output_dir, filename)
    
    # Сохраняем
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Результаты сохранены в файл: {filepath}")
    return filepath


async def parse_for_ml(url, client=None):
    """
    Асинхронный парсинг для ML-классификации типа страницы
    
    Извлекает упрощённую HTML-структуру (без атрибутов class/id)
    
    Args:
        url: URL страницы для парсинга
        client: httpx.AsyncClient (опционально, для переиспользования)
        
    Returns:
        Словарь с данными для ML-модели или None при ошибке
    """
    # Если клиент не передан, создаём временный
    if client is None:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        async with httpx.AsyncClient(
            timeout=30.0, 
            follow_redirects=True,
            verify=False,
            headers=headers
        ) as temp_client:
            return await _parse_with_client(url, temp_client)
    else:
        return await _parse_with_client(url, client)


async def _parse_with_client(url, client):
    """Внутренняя функция парсинга с переданным клиентом"""
    try:
        response = await client.get(url)
        response.raise_for_status()
        html = response.text
    except Exception as e:
        logger.error(f"Ошибка при запросе к {url}: {type(e).__name__}: {e}")
        return None
    
    if not html:
        return None
    
    soup = BeautifulSoup(html, 'lxml')
    
    # Удаляем шум (скрипты, стили, SVG, iframe)
    for tag in soup(['script', 'style', 'noscript', 'svg', 'iframe']):
        tag.decompose()
    
    # Упрощаем HTML: удаляем атрибуты, но оставляем важные
    for tag in soup.find_all(True):
        if tag.name == 'img' and tag.get('src'):
            # Для img оставляем только src
            tag.attrs = {'src': tag['src']}
        elif tag.name == 'meta':
            # Для meta оставляем name/property и content
            new_attrs = {}
            if tag.get('name'):
                new_attrs['name'] = tag['name']
            if tag.get('property'):
                new_attrs['property'] = tag['property']
            if tag.get('content'):
                new_attrs['content'] = tag['content']
            tag.attrs = new_attrs
        elif tag.name in ['title', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            # Для заголовков и title оставляем все как есть (без атрибутов)
            tag.attrs = {}
        else:
            # Для остальных тегов удаляем все атрибуты
            tag.attrs = {}
    
    # Получаем полный HTML с head и body
    html_structure = str(soup)
    
    # Возвращаем результат
    return {
        'url': url,
        'html_structure': html_structure,  # HTML структура с метатегами
    }


if __name__ == "__main__":
    test_url = "https://teploobmennic.ru/catalog/plastinchatye_teploobmenniki/"
    
    logger.info("Парсинг HTML структуры страницы...")
    logger.info(f"URL: {test_url}")
    
    result = asyncio.run(parse_for_ml(test_url))
    
    if result:
        logger.info("Успешно распарсено")
        logger.info(f"HTML структура: {len(result['html_structure'])} символов")
        logger.info(f"Первые 500 символов:")
        logger.info(result['html_structure'][:500] + "...")
        
        # Сохраняем результат в JSON
        save_to_json(result)
    else:
        logger.error("Ошибка при парсинге")
