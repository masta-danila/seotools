import json
from pathlib import Path
from bs4 import BeautifulSoup


def extract_headings_structure(html_structure: str) -> dict:
    """
    Извлекает структуру заголовков из HTML
    
    Args:
        html_structure: HTML структура страницы
        
    Returns:
        dict со структурой заголовков и статистикой
    """
    soup = BeautifulSoup(html_structure, 'html.parser')
    
    # Находим все заголовки в порядке появления
    all_headings = []
    for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        text = tag.get_text(strip=True)
        if text:  # Игнорируем пустые заголовки
            level = int(tag.name[1])  # Извлекаем число из h1, h2 и т.д.
            all_headings.append({
                'level': level,
                'tag': tag.name,
                'text': text,
                'children': []
            })
    
    # Строим иерархию
    def build_hierarchy(headings_list):
        """Строит иерархическую структуру из плоского списка заголовков"""
        if not headings_list:
            return []
        
        result = []
        stack = []  # Стек родительских элементов
        
        for heading in headings_list:
            # Удаляем из стека все элементы с уровнем >= текущего
            while stack and stack[-1]['level'] >= heading['level']:
                stack.pop()
            
            # Если стек не пуст, текущий заголовок - дочерний для последнего в стеке
            if stack:
                stack[-1]['children'].append(heading)
            else:
                # Иначе это заголовок верхнего уровня
                result.append(heading)
            
            # Добавляем текущий заголовок в стек
            stack.append(heading)
        
        return result
    
    hierarchical_headings = build_hierarchy(all_headings)
    
    # Статистика по уровням
    stats = {f'h{i}': 0 for i in range(1, 7)}
    for heading in all_headings:
        stats[heading['tag']] += 1
    
    # Проверяем SEO-проблемы
    issues = []
    
    # Проверка: должен быть хотя бы один H1
    if stats['h1'] == 0:
        issues.append("Отсутствует заголовок H1")
    elif stats['h1'] > 1:
        issues.append(f"Найдено {stats['h1']} заголовков H1 (рекомендуется 1)")
    
    # Проверка: H1 должен быть первым
    if all_headings and all_headings[0]['level'] != 1:
        issues.append(f"Первый заголовок - {all_headings[0]['tag'].upper()}, а не H1")
    
    # Проверка: нет пропусков уровней
    levels_used = sorted(set(h['level'] for h in all_headings))
    for i in range(len(levels_used) - 1):
        if levels_used[i+1] - levels_used[i] > 1:
            issues.append(f"Пропущен уровень между H{levels_used[i]} и H{levels_used[i+1]}")
    
    return {
        'headings': hierarchical_headings,
        'flat_headings': all_headings,  # Плоский список для обратной совместимости
        'total_count': len(all_headings),
        'stats': stats,
        'issues': issues
    }


def extract_from_parse_result(parse_result: dict) -> dict:
    """
    Извлекает заголовки из результата парсинга article_parser
    
    Args:
        parse_result: dict с результатом из article_parser.parse_for_ml()
        
    Returns:
        dict со структурой заголовков
    """
    if 'html_structure' not in parse_result:
        raise ValueError("parse_result должен содержать поле 'html_structure'")
    
    return extract_headings_structure(parse_result['html_structure'])


def format_headings_tree(headings: list, indent_level: int = 0) -> str:
    """
    Форматирует заголовки в виде дерева для красивого вывода
    
    Args:
        headings: иерархический список заголовков
        indent_level: уровень отступа
        
    Returns:
        отформатированная строка с деревом заголовков
    """
    lines = []
    for heading in headings:
        indent = "  " * indent_level
        lines.append(f"{indent}{heading['tag'].upper()}: {heading['text']}")
        
        # Рекурсивно обрабатываем дочерние заголовки
        if heading.get('children'):
            lines.append(format_headings_tree(heading['children'], indent_level + 1))
    
    return "\n".join(lines)


def save_headings_result(result: dict, output_path: str = "jsontests/headings_result.json"):
    """Сохраняет структуру заголовков в JSON файл"""
    output_dir = Path(output_path).parent
    output_dir.mkdir(exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\nРезультат сохранен в {output_path}")


if __name__ == "__main__":
    # Загружаем результат парсинга
    with open("jsontests/parse_result.json", 'r', encoding='utf-8') as f:
        parse_result = json.load(f)
    
    print("Извлечение структуры заголовков...")
    print(f"URL: {parse_result.get('url', 'N/A')}")
    print()
    
    # Извлекаем заголовки
    headings_data = extract_from_parse_result(parse_result)
    
    # Выводим статистику
    print("=== СТАТИСТИКА ===")
    print(f"Всего заголовков: {headings_data['total_count']}")
    for tag, count in headings_data['stats'].items():
        if count > 0:
            print(f"  {tag.upper()}: {count}")
    
    # Выводим проблемы
    if headings_data['issues']:
        print("\n=== SEO-ПРОБЛЕМЫ ===")
        for issue in headings_data['issues']:
            print(f"  ! {issue}")
    else:
        print("\nSEO-проблем не обнаружено")
    
    # Выводим дерево заголовков
    print("\n=== СТРУКТУРА ЗАГОЛОВКОВ ===")
    print(format_headings_tree(headings_data['headings']))
    
    # Сохраняем полный результат
    full_result = {
        "url": parse_result.get('url'),
        "headings": headings_data
    }
    save_headings_result(full_result)
