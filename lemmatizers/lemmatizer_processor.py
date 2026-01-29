"""
Модуль для обработки URL с лемматизацией метатегов конкурентов
"""
import json
import sys
import os
from typing import Dict
from pathlib import Path

# Добавляем путь к модулю lemmatizer
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, str(Path(__file__).parent.parent))

from lemmatizer import find_common_words
from logger_config import get_lemmatizer_logger

logger = get_lemmatizer_logger()


def process_urls_with_lemmatization(
    data: Dict,
    title_min_words: int = 4,
    title_max_words: int = 6,
    description_min_words: int = 4,
    description_max_words: int = 6
) -> Dict:
    """
    Обрабатывает словарь с URL, извлекает title и description из filtered_urls,
    лемматизирует их и добавляет результаты обратно в словарь
    
    Args:
        data: Словарь структуры {spreadsheet_id: {urls: {url: {...}}}}
        title_min_words: Минимальное количество слов для title
        title_max_words: Максимальное количество слов для title
        description_min_words: Минимальное количество слов для description
        description_max_words: Максимальное количество слов для description
    
    Returns:
        Обновленный словарь с добавленными полями lemmatized_title_words и lemmatized_description_words
    """
    result_data = {}
    
    for spreadsheet_id, spreadsheet_info in data.items():
        result_data[spreadsheet_id] = {"urls": {}}
        urls_dict = spreadsheet_info.get('urls', {})
        
        for url, url_data in urls_dict.items():
            # Копируем исходные данные
            result_data[spreadsheet_id]["urls"][url] = url_data.copy()
            
            # Извлекаем все title и description из filtered_urls
            filtered_urls = url_data.get('filtered_urls', [])
            
            titles = []
            descriptions = []
            
            for item in filtered_urls:
                if 'title' in item and item['title']:
                    titles.append(item['title'])
                if 'description' in item and item['description']:
                    descriptions.append(item['description'])
            
            # Лемматизируем
            lemmatized_title_words = find_common_words(
                titles, 
                min_words=title_min_words, 
                max_words=title_max_words
            ) if titles else []
            
            lemmatized_description_words = find_common_words(
                descriptions, 
                min_words=description_min_words, 
                max_words=description_max_words
            ) if descriptions else []
            
            # Добавляем результаты
            result_data[spreadsheet_id]["urls"][url]["lemmatized_title_words"] = lemmatized_title_words
            result_data[spreadsheet_id]["urls"][url]["lemmatized_description_words"] = lemmatized_description_words
            
            logger.info(f"[OK] {url}: title words={len(lemmatized_title_words)}, desc words={len(lemmatized_description_words)}")
    
    return result_data


def save_results_to_json(results: Dict, filename: str = "jsontests/lemmatizer_processor_results.json") -> None:
    """
    Сохраняет результаты в JSON файл
    
    Args:
        results: Словарь с результатами
        filename: Путь к файлу для сохранения
    """
    import os
    
    os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else ".", exist_ok=True)
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Результаты сохранены в файл: {filename}")


if __name__ == "__main__":
    """
    Тестовый запуск
    """
    # Определяем пути относительно корня проекта
    project_root = Path(__file__).parent.parent
    input_file = project_root / "jsontests" / "arsenkin_h_results.json"
    output_file = project_root / "jsontests" / "lemmatizer_processor_results.json"
    
    # Загружаем данные
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Обрабатываем
    results = process_urls_with_lemmatization(
        data=data,
        title_min_words=4,
        title_max_words=6,
        description_min_words=6,
        description_max_words=10
    )
    
    # Сохраняем
    save_results_to_json(results, str(output_file))
