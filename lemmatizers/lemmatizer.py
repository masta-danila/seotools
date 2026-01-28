"""
Модуль для лемматизации (приведения слов к начальной форме) с использованием Yandex Mystem.
"""
from pymystem3 import Mystem
from typing import List, Dict
from pathlib import Path


# Глобальный экземпляр Mystem (создается один раз при импорте модуля)
_mystem = None


def _get_mystem() -> Mystem:
    """Получает или создает глобальный экземпляр Mystem"""
    global _mystem
    if _mystem is None:
        _mystem = Mystem()
    return _mystem


def lemmatize_text(text: str) -> str:
    """
    Приводит все слова в тексте к начальной форме
    
    Args:
        text: Текст для лемматизации
    
    Returns:
        Текст с леммами (через пробел)
    """
    mystem = _get_mystem()
    lemmas = mystem.lemmatize(text)
    # Убираем лишние пробелы и переносы строк
    lemmas = [lemma.strip() for lemma in lemmas if lemma.strip()]
    return ' '.join(lemmas)


def lemmatize_list(texts: List[str]) -> List[str]:
    """
    Лемматизирует список текстов
    
    Args:
        texts: Список текстов для лемматизации
    
    Returns:
        Список лемматизированных текстов
    """
    return [lemmatize_text(text) for text in texts]


def get_lemmas(text: str) -> List[str]:
    """
    Возвращает список лемм для текста
    
    Args:
        text: Текст для лемматизации
    
    Returns:
        Список лемм
    """
    mystem = _get_mystem()
    lemmas = mystem.lemmatize(text)
    return [lemma.strip() for lemma in lemmas if lemma.strip()]


def analyze(text: str) -> List[Dict]:
    """
    Получает подробный морфологический анализ текста
    
    Args:
        text: Текст для анализа
    
    Returns:
        Список словарей с информацией о каждом слове
    """
    mystem = _get_mystem()
    analysis = mystem.analyze(text)
    results = []
    
    for item in analysis:
        if 'analysis' in item and item['analysis']:
            word_info = item['analysis'][0]
            results.append({
                'text': item.get('text', ''),
                'lemma': word_info.get('lex', ''),
                'pos': word_info.get('gr', '').split(',')[0] if word_info.get('gr') else '',
                'grammar': word_info.get('gr', ''),
            })
    
    return results


def lemmatize_queries(queries: List[str]) -> Dict[str, str]:
    """
    Лемматизирует список поисковых запросов
    
    Args:
        queries: Список поисковых запросов
    
    Returns:
        Словарь {оригинальный_запрос: лемматизированный_запрос}
    """
    result = {}
    for query in queries:
        lemmatized = lemmatize_text(query)
        result[query] = lemmatized
    return result


def save_results_to_json(results: Dict, filename: str = "jsontests/lemmatizer_results.json") -> None:
    """
    Сохраняет результаты лемматизации в JSON файл
    
    Args:
        results: Словарь с результатами анализа
        filename: Путь к файлу для сохранения
    """
    import os
    import json
    
    os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else ".", exist_ok=True)
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"Результаты сохранены в файл: {filename}")


def find_common_words(queries: List[str], min_words: int = 4, max_words: int = 6) -> List[str]:
    """
    Находит самые частотные слова (леммы) и возвращает случайное количество из них
    
    Args:
        queries: Список поисковых запросов/фраз
        min_words: Минимальное количество слов для возврата (по умолчанию 4)
        max_words: Максимальное количество слов для возврата (по умолчанию 6)
    
    Returns:
        Список самых частотных слов (случайное количество от min_words до max_words включительно)
        Исключаются предлоги, союзы, частицы (на основе морфологического анализа)
    """
    if not queries:
        return []
    
    import random
    
    # Части речи, которые НЕ нужны (служебные части речи)
    # PR = предлог, CONJ = союз, PART = частица, INTJ = междометие
    exclude_pos = {'PR', 'CONJ', 'PART', 'INTJ'}
    
    mystem = _get_mystem()
    
    # Словарь для подсчета вхождений каждой леммы в фразы
    word_phrase_count = {}
    
    # Обрабатываем каждую фразу
    for query in queries:
        # Получаем морфологический анализ
        analysis = mystem.analyze(query)
        
        # Собираем леммы для текущей фразы с проверкой части речи
        lemmas_in_phrase = set()
        
        for item in analysis:
            if 'analysis' in item and item['analysis']:
                word_info = item['analysis'][0]
                lemma = word_info.get('lex', '').strip()
                grammar = word_info.get('gr', '')
                
                # Определяем часть речи (первая часть до запятой)
                pos = grammar.split(',')[0].split('=')[0] if grammar else ''
                
                # Фильтруем:
                # 1. Исключаем служебные части речи
                # 2. Короткие слова (меньше 3 символов)
                # 3. Только слова с буквами
                if (pos not in exclude_pos and 
                    lemma and 
                    len(lemma) >= 3 and 
                    any(c.isalpha() for c in lemma)):
                    lemmas_in_phrase.add(lemma)
        
        # Увеличиваем счетчик для каждой уникальной леммы в этой фразе
        for lemma in lemmas_in_phrase:
            if lemma not in word_phrase_count:
                word_phrase_count[lemma] = 0
            word_phrase_count[lemma] += 1
    
    # Если слов нет, возвращаем пустой список
    if not word_phrase_count:
        return []
    
    # Сортируем все слова по убыванию частоты
    sorted_words = sorted(word_phrase_count.items(), key=lambda x: x[1], reverse=True)
    
    # Определяем случайное количество слов для возврата
    num_words = random.randint(min_words, max_words)
    
    # Берем топ N самых частотных слов
    # Если слов меньше чем num_words, берем все доступные
    num_words = min(num_words, len(sorted_words))
    
    # Возвращаем только слова (без счетчиков)
    return [word for word, count in sorted_words[:num_words]]


if __name__ == "__main__":
    """
    Тестовый запуск - извлекает title из filtered_urls и находит частотные слова
    """
    import json
    
    # Определяем пути относительно корня проекта
    project_root = Path(__file__).parent.parent
    input_file = project_root / "jsontests" / "arsenkin_h_results.json"
    output_file = project_root / "jsontests" / "lemmatizer_results.json"
    
    # Читаем JSON файл
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Извлекаем все title из filtered_urls
    texts = []
    
    for spreadsheet_id, spreadsheet_info in data.items():
        urls_dict = spreadsheet_info.get('urls', {})
        for url, url_data in urls_dict.items():
            filtered_urls = url_data.get('filtered_urls', [])
            for item in filtered_urls:
                if 'title' in item and item['title']:
                    texts.append(item['title'])
    
    print(f"Найдено текстов: {len(texts)}")
    
    # Находим частотные слова (случайное количество от 4 до 6)
    min_words = 4
    max_words = 6
    common_words = find_common_words(texts, min_words=min_words, max_words=max_words)
    
    print(f"\nВыбрано слов: {len(common_words)}")
    print(f"Частотные слова: {common_words}")
    
    # Сохраняем список слов
    save_results_to_json(common_words, str(output_file))
