"""
Парсер статей с использованием BeautifulSoup и httpx (асинхронный)
"""
import json
import os
import asyncio
import httpx
from bs4 import BeautifulSoup


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
    
    print(f"\nРезультаты сохранены в файл: {filepath}")
    return filepath


async def parse_for_ml(url):
    """
    Асинхронный парсинг для ML-классификации типа страницы
    
    Извлекает упрощённую HTML-структуру (без атрибутов class/id)
    
    Args:
        url: URL страницы для парсинга
        
    Returns:
        Словарь с данными для ML-модели или None при ошибке
    """
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text
        except Exception:
            return None
    
    if not html:
        return None
    
    soup = BeautifulSoup(html, 'lxml')
    
    # Удаляем шум (скрипты, стили, SVG, iframe)
    for tag in soup(['script', 'style', 'noscript', 'svg', 'iframe']):
        tag.decompose()
    
    # Упрощаем HTML: удаляем атрибуты, но оставляем src у изображений
    for tag in soup.find_all(True):
        if tag.name == 'img' and tag.get('src'):
            # Для img оставляем только src
            tag.attrs = {'src': tag['src']}
        else:
            # Для остальных тегов удаляем все атрибуты
            tag.attrs = {}
    
    # Получаем упрощённый HTML (без атрибутов, кроме src у img)
    body = soup.find('body')
    html_structure = str(body) if body else str(soup)
    
    # Возвращаем результат
    return {
        'url': url,
        'html_structure': html_structure,  # HTML структура с src у изображений
    }


if __name__ == "__main__":
    test_url = "https://serpstat.com/ru/blog/chto-takoe-seo-prodvizhenie-sajta/"
    
    print("Парсинг HTML структуры страницы...")
    print(f"URL: {test_url}\n")
    
    result = asyncio.run(parse_for_ml(test_url))
    
    if result:
        print("Успешно распарсено")
        print(f"\nHTML структура (первые 500 символов):")
        print(result['html_structure'][:500] + "...")
        
        # Сохраняем результат в JSON
        save_to_json(result)
        print("\nРезультаты сохранены: jsontests/parse_result.json")
    else:
        print("Ошибка при парсинге")

