"""
Модуль для чтения данных из Google Sheets
Читает таблицы, находит URL с незаполненными метатегами на листе "Meta"
и собирает вводные данные с листа "Data"
"""
import json
import os
from typing import List, Dict, Optional
import gspread
from google.oauth2.service_account import Credentials


def get_sheets_client():
    """
    Создает и возвращает клиент Google Sheets
    
    Returns:
        gspread.Client: Авторизованный клиент
    """
    # Путь к файлу с credentials
    credentials_path = os.path.join(os.path.dirname(__file__), 'credentials.json')
    
    # Определяем scopes
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    
    # Создаем credentials
    creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
    
    # Создаем клиент
    client = gspread.authorize(creds)
    
    return client


def load_spreadsheet_ids() -> List[str]:
    """
    Загружает список ID таблиц из spreadsheets.json
    
    Returns:
        List[str]: Список ID таблиц
    """
    spreadsheets_path = os.path.join(os.path.dirname(__file__), 'spreadsheets.json')
    
    with open(spreadsheets_path, 'r', encoding='utf-8') as f:
        spreadsheet_ids = json.load(f)
    
    return spreadsheet_ids


def get_urls_with_empty_meta(worksheet) -> Dict[str, Dict[str, bool]]:
    """
    Находит URL с незаполненными метатегами (h1, title или description)
    
    Args:
        worksheet: Лист Google Sheets
    
    Returns:
        Dict[str, Dict[str, bool]]: Словарь {url: {"h1": True/False, "title": True/False, "description": True/False}}
    """
    # Получаем все данные листа
    all_values = worksheet.get_all_values()
    
    if not all_values:
        return []
    
    # Первая строка - заголовки
    headers = all_values[0]
    
    # Находим индексы нужных колонок
    try:
        url_idx = headers.index('URL') if 'URL' in headers else headers.index('url')
        h1_idx = headers.index('h1') if 'h1' in headers else headers.index('H1')
        title_idx = headers.index('title') if 'title' in headers else headers.index('Title')
        desc_idx = headers.index('description') if 'description' in headers else headers.index('Description')
    except ValueError as e:
        print(f"Не найдена обязательная колонка: {e}")
        return []
    
    # Собираем URL с незаполненными метатегами и информацией о заполненности
    urls_meta_status = {}
    
    for row in all_values[1:]:  # Пропускаем заголовок
        if len(row) <= max(url_idx, h1_idx, title_idx, desc_idx):
            continue
        
        url = row[url_idx].strip() if url_idx < len(row) else ""
        h1 = row[h1_idx].strip() if h1_idx < len(row) else ""
        title = row[title_idx].strip() if title_idx < len(row) else ""
        description = row[desc_idx].strip() if desc_idx < len(row) else ""
        
        # Если хотя бы одно поле пустое и есть URL
        if url and (not h1 or not title or not description):
            urls_meta_status[url] = {
                "h1": bool(h1),
                "title": bool(title),
                "description": bool(description)
            }
    
    return urls_meta_status


def get_input_data_for_urls(worksheet, urls_meta_status: Dict[str, Dict[str, bool]]) -> Dict[str, Dict]:
    """
    Получает вводные данные для URL с листа "Data"
    
    Args:
        worksheet: Лист "Data"
        urls_meta_status: Словарь {url: {"h1": bool, "title": bool, "description": bool}}
    
    Returns:
        Dict[str, Dict]: Словарь {url: {данные + статус метатегов}}
    """
    # Получаем все данные листа
    all_values = worksheet.get_all_values()
    
    if not all_values:
        return {}
    
    # Первая строка - заголовки
    headers = all_values[0]
    
    # Находим индексы нужных колонок
    try:
        url_idx = headers.index('URL') if 'URL' in headers else headers.index('url')
        queries_idx = headers.index('Querries') if 'Querries' in headers else None
        company_idx = headers.index('Company name') if 'Company name' in headers else None
        var_h1_idx = headers.index('Variables h1') if 'Variables h1' in headers else None
        var_title_idx = headers.index('Variables title') if 'Variables title' in headers else None
        var_desc_idx = headers.index('Variables description') if 'Variables description' in headers else None
    except ValueError as e:
        print(f"Не найдена колонка URL: {e}")
        return {}
    
    # Собираем данные для каждого URL (URL может быть в нескольких строках)
    result = {}
    
    for row in all_values[1:]:  # Пропускаем заголовок
        if len(row) <= url_idx:
            continue
        
        url = row[url_idx].strip()
        
        # Если этот URL в словаре нужных
        if url in urls_meta_status:
            # Инициализируем словарь для URL если его еще нет
            if url not in result:
                result[url] = {
                    "queries": [],
                    "company_name": set(),
                    "variables_h1": [],
                    "variables_title": [],
                    "variables_description": []
                }
            
            # Получаем запросы (могут быть разделены новой строкой)
            queries = row[queries_idx].strip() if queries_idx and queries_idx < len(row) else ""
            queries_list = [q.strip() for q in queries.split('\n') if q.strip()] if queries else []
            
            # Добавляем уникальные запросы
            for q in queries_list:
                if q and q not in result[url]["queries"]:
                    result[url]["queries"].append(q)
            
            # Получаем название компании
            company_name = row[company_idx].strip() if company_idx and company_idx < len(row) else ""
            if company_name:
                result[url]["company_name"].add(company_name)
            
            # Получаем переменные для h1 (могут быть разделены новой строкой)
            var_h1 = row[var_h1_idx].strip() if var_h1_idx and var_h1_idx < len(row) else ""
            var_h1_list = [v.strip() for v in var_h1.split('\n') if v.strip()] if var_h1 else []
            
            # Добавляем уникальные переменные h1
            for v in var_h1_list:
                if v and v not in result[url]["variables_h1"]:
                    result[url]["variables_h1"].append(v)
            
            # Получаем переменные для title (могут быть разделены новой строкой)
            var_title = row[var_title_idx].strip() if var_title_idx and var_title_idx < len(row) else ""
            var_title_list = [v.strip() for v in var_title.split('\n') if v.strip()] if var_title else []
            
            # Добавляем уникальные переменные title
            for v in var_title_list:
                if v and v not in result[url]["variables_title"]:
                    result[url]["variables_title"].append(v)
            
            # Получаем переменные для description (могут быть разделены новой строкой)
            var_desc = row[var_desc_idx].strip() if var_desc_idx and var_desc_idx < len(row) else ""
            var_desc_list = [v.strip() for v in var_desc.split('\n') if v.strip()] if var_desc else []
            
            # Добавляем уникальные переменные description
            for v in var_desc_list:
                if v and v not in result[url]["variables_description"]:
                    result[url]["variables_description"].append(v)
    
    # Преобразуем company_name из set в строку и добавляем статус метатегов
    for url in result:
        company_names = list(result[url]["company_name"])
        # Если несколько названий компании, берем первое непустое
        result[url]["company_name"] = company_names[0] if company_names else ""
        
        # Добавляем информацию о статусе метатегов
        result[url]["meta_status"] = urls_meta_status.get(url, {
            "h1": False,
            "title": False,
            "description": False
        })
    
    return result


def process_all_spreadsheets() -> Dict:
    """
    Обрабатывает все таблицы из spreadsheets.json
    
    Returns:
        Dict: Словарь с данными для всех таблиц
    """
    # Загружаем ID таблиц
    spreadsheet_ids = load_spreadsheet_ids()
    
    # Создаем клиент
    client = get_sheets_client()
    
    # Результат для всех таблиц
    all_data = {}
    
    for spreadsheet_id in spreadsheet_ids:
        print(f"\nОбработка таблицы: {spreadsheet_id}")
        
        try:
            # Открываем таблицу
            spreadsheet = client.open_by_key(spreadsheet_id)
            print(f"✓ Таблица открыта: {spreadsheet.title}")
            
            # Получаем лист "Meta"
            try:
                meta_sheet = spreadsheet.worksheet("Meta")
            except gspread.exceptions.WorksheetNotFound:
                print(f"  ✗ Лист 'Meta' не найден")
                continue
            
            # Находим URL с незаполненными метатегами и их статус
            urls_meta_status = get_urls_with_empty_meta(meta_sheet)
            print(f"  Найдено URL с незаполненными метатегами: {len(urls_meta_status)}")
            
            if not urls_meta_status:
                print(f"  ✓ Все метатеги заполнены")
                continue
            
            # Получаем лист "Data"
            try:
                input_sheet = spreadsheet.worksheet("Data")
            except gspread.exceptions.WorksheetNotFound:
                print(f"  ✗ Лист 'Data' не найден")
                continue
            
            # Получаем вводные данные для URL
            input_data = get_input_data_for_urls(input_sheet, urls_meta_status)
            print(f"  Получено данных для URL: {len(input_data)}")
            
            # Сохраняем данные для этой таблицы
            all_data[spreadsheet_id] = {
                "urls": input_data
            }
            
        except Exception as e:
            print(f"  ✗ Ошибка при обработке таблицы {spreadsheet_id}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    return all_data


def save_to_json(data: Dict, filename: str = "jsontests/sheets_data.json") -> None:
    """
    Сохраняет данные в JSON файл
    
    Args:
        data: Данные для сохранения
        filename: Путь к файлу
    """
    os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else ".", exist_ok=True)
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Данные сохранены в файл: {filename}")


if __name__ == "__main__":
    """
    Тест чтения данных из Google Sheets
    """
    print("Начало обработки Google Sheets...")
    print("="*80)
    
    try:
        # Обрабатываем все таблицы
        data = process_all_spreadsheets()
        
        # Сохраняем в JSON
        save_to_json(data)
        
        # Выводим краткую статистику
        print("\n" + "="*80)
        print("СТАТИСТИКА:")
        print("="*80)
        
        total_urls = 0
        for spreadsheet_id, sheet_data in data.items():
            urls_count = len(sheet_data.get('urls', {}))
            total_urls += urls_count
            print(f"\nТаблица ID: {spreadsheet_id}")
            print(f"  URL для обработки: {urls_count}")
        
        print(f"\nВсего URL для обработки: {total_urls}")
        
        # Выводим пример данных
        if data:
            print("\n" + "="*80)
            print("ПРИМЕР ДАННЫХ:")
            print("="*80)
            
            first_sheet = list(data.values())[0]
            if first_sheet.get('urls'):
                first_url = list(first_sheet['urls'].keys())[0]
                first_data = first_sheet['urls'][first_url]
                
                print(f"\nURL: {first_url}")
                print(f"Запросы: {first_data.get('queries', [])}")
                print(f"Компания: {first_data.get('company_name', '')}")
                print(f"Переменные h1: {first_data.get('variables_h1', [])}")
                print(f"Переменные title: {first_data.get('variables_title', [])}")
                print(f"Переменные description: {first_data.get('variables_description', [])}")
                print(f"Статус метатегов: {first_data.get('meta_status', {})}")
        
    except Exception as e:
        print(f"\nОшибка: {e}")
        import traceback
        traceback.print_exc()
