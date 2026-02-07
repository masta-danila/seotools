"""
Модуль для чтения данных из Google Sheets

Логика работы:
1. Получает статус всех URL из листа "Meta" (заполнены все поля или нет)
2. Собирает все URL из листа "Data" и фильтрует те, которые:
   - отсутствуют в Meta, ИЛИ
   - присутствуют в Meta, но имеют незаполненные поля (h1, title, description)
3. Возвращает вводные данные для отфильтрованных URL
"""
import json
import os
import sys
from typing import List, Dict, Optional
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

# Добавляем корень проекта в путь для импорта
sys.path.insert(0, str(Path(__file__).parent.parent))

from logger_config import get_sheets_reader_logger

logger = get_sheets_reader_logger()


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


def get_meta_urls_status(worksheet) -> Dict[str, bool]:
    """
    Получает статус заполненности метатегов для всех URL на листе Meta
    
    Args:
        worksheet: Лист "Meta"
    
    Returns:
        Dict[str, bool]: Словарь {url: True/False}, где True = все поля заполнены, False = есть пустые поля
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
        h1_idx = headers.index('h1') if 'h1' in headers else headers.index('H1')
        title_idx = headers.index('title') if 'title' in headers else headers.index('Title')
        desc_idx = headers.index('description') if 'description' in headers else headers.index('Description')
    except ValueError as e:
        logger.error(f"Не найдена обязательная колонка в Meta: {e}")
        return {}
    
    # Собираем статус для каждого URL
    meta_status = {}
    
    for row in all_values[1:]:  # Пропускаем заголовок
        if len(row) <= url_idx:
            continue
        
        url = row[url_idx].strip() if url_idx < len(row) else ""
        if not url:
            continue
            
        h1 = row[h1_idx].strip() if h1_idx < len(row) else ""
        title = row[title_idx].strip() if title_idx < len(row) else ""
        description = row[desc_idx].strip() if desc_idx < len(row) else ""
        
        # True если все поля заполнены, False если хотя бы одно пустое
        meta_status[url] = bool(h1 and title and description)
    
    return meta_status


def get_all_data_urls(worksheet, meta_status: Dict[str, bool]) -> Dict[str, Dict]:
    """
    Получает вводные данные для всех URL с листа "Data", которые:
    - отсутствуют в Meta, ИЛИ
    - присутствуют в Meta, но имеют незаполненные поля
    
    Args:
        worksheet: Лист "Data"
        meta_status: Словарь {url: True/False} со статусом заполненности Meta
    
    Returns:
        Dict[str, Dict]: Словарь {url: {данные}}
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
        region_idx = headers.index('Region') if 'Region' in headers else None
        var_h1_idx = headers.index('Variables h1') if 'Variables h1' in headers else None
        var_title_idx = headers.index('Variables title') if 'Variables title' in headers else None
        var_desc_idx = headers.index('Variables description') if 'Variables description' in headers else None
    except ValueError as e:
        logger.error(f"Не найдена колонка URL в Data: {e}")
        return {}
    
    # Собираем данные для каждого URL (URL может быть в нескольких строках)
    all_data = {}
    
    for row in all_values[1:]:  # Пропускаем заголовок
        if len(row) <= url_idx:
            continue
        
        url = row[url_idx].strip()
        if not url:
            continue
        
        # Инициализируем словарь для URL если его еще нет
        if url not in all_data:
            all_data[url] = {
                "queries": [],
                "company_name": set(),
                "region": set(),
                "variables_h1": [],
                "variables_title": [],
                "variables_description": []
            }
        
        # Получаем запросы (могут быть разделены новой строкой)
        queries = row[queries_idx].strip() if queries_idx and queries_idx < len(row) else ""
        queries_list = [q.strip() for q in queries.split('\n') if q.strip()] if queries else []
        
        # Добавляем уникальные запросы
        for q in queries_list:
            if q and q not in all_data[url]["queries"]:
                all_data[url]["queries"].append(q)
        
        # Получаем название компании
        company_name = row[company_idx].strip() if company_idx and company_idx < len(row) else ""
        if company_name:
            all_data[url]["company_name"].add(company_name)
        
        # Получаем регион
        region = row[region_idx].strip() if region_idx and region_idx < len(row) else ""
        if region:
            all_data[url]["region"].add(region)
        
        # Получаем переменные для h1 (могут быть разделены новой строкой)
        var_h1 = row[var_h1_idx].strip() if var_h1_idx and var_h1_idx < len(row) else ""
        var_h1_list = [v.strip() for v in var_h1.split('\n') if v.strip()] if var_h1 else []
        
        # Добавляем уникальные переменные h1
        for v in var_h1_list:
            if v and v not in all_data[url]["variables_h1"]:
                all_data[url]["variables_h1"].append(v)
        
        # Получаем переменные для title (могут быть разделены новой строкой)
        var_title = row[var_title_idx].strip() if var_title_idx and var_title_idx < len(row) else ""
        var_title_list = [v.strip() for v in var_title.split('\n') if v.strip()] if var_title else []
        
        # Добавляем уникальные переменные title
        for v in var_title_list:
            if v and v not in all_data[url]["variables_title"]:
                all_data[url]["variables_title"].append(v)
        
        # Получаем переменные для description (могут быть разделены новой строкой)
        var_desc = row[var_desc_idx].strip() if var_desc_idx and var_desc_idx < len(row) else ""
        var_desc_list = [v.strip() for v in var_desc.split('\n') if v.strip()] if var_desc else []
        
        # Добавляем уникальные переменные description
        for v in var_desc_list:
            if v and v not in all_data[url]["variables_description"]:
                all_data[url]["variables_description"].append(v)
    
    # Фильтруем URL: берем только те, которых нет в Meta или они есть но не полностью заполнены
    result = {}
    for url, data in all_data.items():
        # URL отсутствует в Meta (не в словаре) ИЛИ присутствует но не все поля заполнены (False)
        if url not in meta_status or not meta_status[url]:
            # Преобразуем company_name из set в строку
            company_names = list(data["company_name"])
            data["company_name"] = company_names[0] if company_names else ""
            
            # Преобразуем region из set в int или строку
            regions = list(data["region"])
            if regions:
                region_value = regions[0]
                # Пытаемся преобразовать в int, если это число
                try:
                    data["region"] = int(region_value)
                except ValueError:
                    data["region"] = region_value
            else:
                data["region"] = None
            
            result[url] = data
    
    return result


def process_all_spreadsheets() -> Dict:
    """
    Обрабатывает все таблицы из spreadsheets.json
    
    Логика:
    - Получает статус всех URL из листа "Meta"
    - Берет все URL из листа "Data", которые:
      * отсутствуют в Meta, ИЛИ
      * присутствуют в Meta, но имеют незаполненные поля (h1, title, description)
    
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
        logger.info(f"Обработка таблицы: {spreadsheet_id}")
        
        try:
            # Открываем таблицу
            spreadsheet = client.open_by_key(spreadsheet_id)
            logger.info(f"✓ Таблица открыта: {spreadsheet.title}")
            
            # Получаем лист "Meta"
            meta_status = {}
            try:
                meta_sheet = spreadsheet.worksheet("Meta")
                # Получаем статус заполненности для всех URL в Meta
                meta_status = get_meta_urls_status(meta_sheet)
                logger.info(f"  Найдено URL в Meta: {len(meta_status)}")
            except gspread.exceptions.WorksheetNotFound:
                logger.warning(f"  ✗ Лист 'Meta' не найден, будут обработаны все URL из Data")
            
            # Получаем лист "Data"
            try:
                input_sheet = spreadsheet.worksheet("Data")
            except gspread.exceptions.WorksheetNotFound:
                logger.warning(f"  ✗ Лист 'Data' не найден")
                continue
            
            # Получаем данные для всех URL из Data, фильтруя по статусу Meta
            input_data = get_all_data_urls(input_sheet, meta_status)
            
            # Считаем сколько URL отсутствуют в Meta и сколько с незаполненными полями
            missing_in_meta = sum(1 for url in input_data.keys() if url not in meta_status)
            incomplete_in_meta = sum(1 for url in input_data.keys() if url in meta_status and not meta_status[url])
            
            logger.info(f"  URL для обработки: {len(input_data)}")
            logger.info(f"    - отсутствуют в Meta: {missing_in_meta}")
            logger.info(f"    - есть в Meta, но не заполнены: {incomplete_in_meta}")
            
            if not input_data:
                logger.info(f"  ✓ Нет URL для обработки")
                continue
            
            # Сохраняем данные для этой таблицы
            all_data[spreadsheet_id] = {
                "urls": input_data
            }
            
        except Exception as e:
            logger.error(f"  ✗ Ошибка при обработке таблицы {spreadsheet_id}: {e}", exc_info=True)
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
    
    logger.info(f"✓ Данные сохранены в файл: {filename}")


if __name__ == "__main__":
    """
    Тест чтения данных из Google Sheets
    """
    logger.info("Начало обработки Google Sheets...")
    logger.info("="*80)
    
    try:
        # Обрабатываем все таблицы
        data = process_all_spreadsheets()
        
        # Сохраняем в JSON
        save_to_json(data)
        
        # Выводим краткую статистику
        logger.info("="*80)
        logger.info("СТАТИСТИКА:")
        logger.info("="*80)
        
        total_urls = 0
        for spreadsheet_id, sheet_data in data.items():
            urls_count = len(sheet_data.get('urls', {}))
            total_urls += urls_count
            logger.info(f"Таблица ID: {spreadsheet_id}")
            logger.info(f"  URL для обработки: {urls_count}")
        
        logger.info(f"Всего URL для обработки: {total_urls}")
        
        # Выводим пример данных
        if data:
            logger.info("="*80)
            logger.info("ПРИМЕР ДАННЫХ:")
            logger.info("="*80)
            
            first_sheet = list(data.values())[0]
            if first_sheet.get('urls'):
                first_url = list(first_sheet['urls'].keys())[0]
                first_data = first_sheet['urls'][first_url]
                
                logger.info(f"URL: {first_url}")
                logger.info(f"Запросы: {first_data.get('queries', [])}")
                logger.info(f"Компания: {first_data.get('company_name', '')}")
                logger.info(f"Регион: {first_data.get('region', None)}")
                logger.info(f"Переменные h1: {first_data.get('variables_h1', [])}")
                logger.info(f"Переменные title: {first_data.get('variables_title', [])}")
                logger.info(f"Переменные description: {first_data.get('variables_description', [])}")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
