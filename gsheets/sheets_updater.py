"""
Модуль для обновления Google Таблиц сгенерированными метатегами
"""
import json
import sys
import gspread
from google.oauth2.service_account import Credentials
from typing import Dict, List
from pathlib import Path
import time

# Добавляем корень проекта в путь для импорта
sys.path.insert(0, str(Path(__file__).parent.parent))

from logger_config import get_sheets_updater_logger

logger = get_sheets_updater_logger()


def get_sheets_client():
    """
    Создает и возвращает клиент Google Sheets API
    
    Returns:
        gspread.Client: Авторизованный клиент
    """
    # Определяем путь к credentials
    credentials_path = Path(__file__).parent / "credentials.json"
    
    # Scopes для Google Sheets API
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    
    # Создаем credentials
    credentials = Credentials.from_service_account_file(
        str(credentials_path),
        scopes=scopes
    )
    
    # Авторизуемся
    client = gspread.authorize(credentials)
    return client


def get_meta_sheet_data(worksheet) -> tuple:
    """
    Загружает все данные из листа Meta
    
    Args:
        worksheet: Лист Google Sheets
        
    Returns:
        Tuple: (headers, all_rows, url_to_row_mapping)
            - headers: список заголовков
            - all_rows: список всех строк (list of lists)
            - url_to_row_mapping: словарь {url: row_number}
    """
    try:
        # Получаем все данные листа сразу (быстрее чем построчно)
        all_values = worksheet.get_all_values()
        
        if not all_values:
            return [], [], {}
        
        headers = all_values[0]  # Первая строка - заголовки
        data_rows = all_values[1:]  # Остальные строки - данные
        
        # Находим индекс колонки URL
        try:
            url_col_idx = headers.index('URL') if 'URL' in headers else headers.index('url')
        except ValueError:
            logger.error("[ОШИБКА] Колонка URL не найдена в заголовках")
            return headers, data_rows, {}
        
        # Создаем маппинг URL -> номер строки (1-based, +2 т.к. пропускаем заголовок и начинаем с 1)
        url_to_row = {}
        for i, row in enumerate(data_rows, start=2):  # Начинаем со 2, т.к. 1 - заголовки
            if len(row) > url_col_idx and row[url_col_idx]:
                url_to_row[row[url_col_idx]] = i
        
        return headers, data_rows, url_to_row
        
    except Exception as e:
        logger.error(f"[ОШИБКА] Загрузка данных листа: {str(e)}")
        return [], [], {}


def update_spreadsheet_metatags(
    client,
    spreadsheet_id: str,
    urls_data: Dict,
    sheet_name: str = "Meta"
) -> Dict:
    """
    Обновляет метатеги в Google Таблице для всех URL (батчевое обновление)
    - Если URL есть в таблице - дозаполняет пустые поля
    - Если URL нет в таблице - создает новую строку
    
    Args:
        client: Авторизованный клиент gspread
        spreadsheet_id: ID таблицы
        urls_data: Словарь с данными URL и сгенерированными метатегами
        sheet_name: Название листа (по умолчанию "Meta")
        
    Returns:
        Словарь со статистикой обновлений
    """
    stats = {
        "processed": 0,
        "updated": 0,
        "created": 0,
        "skipped": 0,
        "errors": 0,
        "details": []
    }
    
    try:
        # Открываем таблицу
        spreadsheet = client.open_by_key(spreadsheet_id)
        logger.info(f"[OK] Открыта таблица: {spreadsheet.title}")
        
        # Открываем лист
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            logger.info(f"[OK] Открыт лист: {sheet_name}")
        except gspread.WorksheetNotFound:
            logger.error(f"[ОШИБКА] Лист '{sheet_name}' не найден")
            stats["errors"] += len(urls_data)
            return stats
        
        # Загружаем все данные листа
        headers, data_rows, url_to_row = get_meta_sheet_data(worksheet)
        
        if not headers:
            logger.error(f"[ОШИБКА] Не удалось загрузить данные листа")
            stats["errors"] += len(urls_data)
            return stats
        
        # Находим индексы нужных колонок
        try:
            url_col_idx = headers.index('URL') if 'URL' in headers else headers.index('url')
            h1_col_idx = headers.index('h1') if 'h1' in headers else headers.index('H1')
            title_col_idx = headers.index('title') if 'title' in headers else headers.index('Title')
            description_col_idx = headers.index('description') if 'description' in headers else headers.index('Description')
        except ValueError as e:
            logger.error(f"[ОШИБКА] Не найдена необходимая колонка: {e}")
            logger.error(f"[DEBUG] Доступные колонки: {headers}")
            stats["errors"] += len(urls_data)
            return stats
        
        logger.info(f"[INFO] Найдены колонки: URL={url_col_idx}, H1={h1_col_idx}, Title={title_col_idx}, Description={description_col_idx}")
        logger.info(f"[INFO] В листе Meta найдено {len(url_to_row)} URL")
        
        # Собираем все обновления и вставки в один батч
        batch_updates = []
        rows_to_append = []
        
        # Обрабатываем каждый URL
        for url, url_info in urls_data.items():
            stats["processed"] += 1
            
            # Проверяем, есть ли сгенерированные метатеги
            generated = url_info.get("generated_metatags")
            if not generated or generated.get("error"):
                logger.warning(f"[ПРОПУСК] Нет сгенерированных метатегов для: {url}")
                stats["skipped"] += 1
                stats["details"].append({
                    "url": url,
                    "status": "no_generated_data"
                })
                continue
            
            # Проверяем, есть ли URL в таблице
            if url in url_to_row:
                # URL существует - обновляем пустые поля
                row_num = url_to_row[url]
                row_data = data_rows[row_num - 2]  # -2 т.к. data_rows начинается с 0, а row_num с 2
                
                # Читаем текущие значения
                current_h1 = row_data[h1_col_idx] if len(row_data) > h1_col_idx else ""
                current_title = row_data[title_col_idx] if len(row_data) > title_col_idx else ""
                current_description = row_data[description_col_idx] if len(row_data) > description_col_idx else ""
                
                # Подготавливаем обновления только для пустых полей
                url_updates = []
                
                # H1 - заполняем если пусто
                if not current_h1 and generated.get("h1"):
                    col_letter = chr(65 + h1_col_idx)  # 65 = 'A'
                    url_updates.append({
                        "range": f"{col_letter}{row_num}",
                        "values": [[generated["h1"]]]
                    })
                
                # Title - заполняем если пусто
                if not current_title and generated.get("title"):
                    col_letter = chr(65 + title_col_idx)
                    url_updates.append({
                        "range": f"{col_letter}{row_num}",
                        "values": [[generated["title"]]]
                    })
                
                # Description - заполняем если пусто
                if not current_description and generated.get("description"):
                    col_letter = chr(65 + description_col_idx)
                    url_updates.append({
                        "range": f"{col_letter}{row_num}",
                        "values": [[generated["description"]]]
                    })
                
                # Добавляем обновления в общий батч
                if url_updates:
                    batch_updates.extend(url_updates)
                    logger.info(f"[ОБНОВЛЕНИЕ] {len(url_updates)} полей для: {url} (строка {row_num})")
                    stats["updated"] += 1
                    stats["details"].append({
                        "url": url,
                        "status": "updated",
                        "row": row_num,
                        "fields_updated": len(url_updates)
                    })
                else:
                    logger.info(f"[ПРОПУСК] Все поля уже заполнены для: {url} (строка {row_num})")
                    stats["skipped"] += 1
                    stats["details"].append({
                        "url": url,
                        "status": "already_filled",
                        "row": row_num
                    })
            else:
                # URL не существует - создаем новую строку
                # Создаем строку с нужным количеством колонок
                new_row = [""] * len(headers)
                new_row[url_col_idx] = url
                new_row[h1_col_idx] = generated.get("h1", "")
                new_row[title_col_idx] = generated.get("title", "")
                new_row[description_col_idx] = generated.get("description", "")
                
                rows_to_append.append(new_row)
                logger.info(f"[СОЗДАНИЕ] Новая строка для: {url}")
                stats["created"] += 1
                stats["details"].append({
                    "url": url,
                    "status": "created"
                })
        
        # Применяем все обновления одним батчем
        if batch_updates:
            try:
                logger.info(f"[BATCH UPDATE] Применение {len(batch_updates)} обновлений...")
                worksheet.batch_update(batch_updates)
                logger.info(f"[OK] Обновления применены успешно")
            except Exception as e:
                logger.error(f"[ОШИБКА] Батчевое обновление: {str(e)}")
                stats["errors"] += len(batch_updates)
                # Помечаем все подготовленные URL как ошибочные
                for detail in stats["details"]:
                    if detail.get("status") == "updated":
                        detail["status"] = "error"
                        detail["error"] = str(e)
        
        # Добавляем новые строки одним батчем
        if rows_to_append:
            try:
                logger.info(f"[BATCH APPEND] Добавление {len(rows_to_append)} новых строк...")
                worksheet.append_rows(rows_to_append)
                logger.info(f"[OK] Новые строки добавлены успешно")
            except Exception as e:
                logger.error(f"[ОШИБКА] Добавление строк: {str(e)}")
                stats["errors"] += len(rows_to_append)
                # Помечаем все созданные URL как ошибочные
                for detail in stats["details"]:
                    if detail.get("status") == "created":
                        detail["status"] = "error"
                        detail["error"] = str(e)
        
    except Exception as e:
        logger.error(f"[ОШИБКА] Обработка таблицы {spreadsheet_id}: {str(e)}")
        stats["errors"] += len(urls_data) - stats["processed"]
    
    return stats


def update_all_spreadsheets(
    data: Dict,
    sheet_name: str = "Meta"
) -> Dict:
    """
    Обновляет все таблицы из данных metagenerator_batch_results.json (батчевое обновление)
    
    Args:
        data: Словарь с данными из metagenerator_batch_results.json
        sheet_name: Название листа для обновления
        
    Returns:
        Общая статистика по всем таблицам
    """
    logger.info("НАЧАЛО ОБНОВЛЕНИЯ GOOGLE ТАБЛИЦ")
    
    # Создаем клиент
    client = get_sheets_client()
    logger.info("[OK] Авторизация в Google Sheets успешна")
    
    # Общая статистика
    total_stats = {
        "spreadsheets_processed": 0,
        "spreadsheets_success": 0,
        "spreadsheets_failed": 0,
        "total_urls_processed": 0,
        "total_urls_updated": 0,
        "total_urls_created": 0,
        "total_urls_skipped": 0,
        "total_errors": 0,
        "by_spreadsheet": {}
    }
    
    # Обрабатываем каждую таблицу
    for spreadsheet_id, spreadsheet_data in data.items():
        total_stats["spreadsheets_processed"] += 1
        
        logger.info(f"Обработка таблицы: {spreadsheet_id}")
        
        urls_data = spreadsheet_data.get("urls", {})
        
        if not urls_data:
            logger.warning("[ПРОПУСК] Нет данных для обновления")
            total_stats["spreadsheets_failed"] += 1
            continue
        
        # Обновляем таблицу (батчевое обновление)
        stats = update_spreadsheet_metatags(
            client=client,
            spreadsheet_id=spreadsheet_id,
            urls_data=urls_data,
            sheet_name=sheet_name
        )
        
        # Обновляем общую статистику
        total_stats["total_urls_processed"] += stats["processed"]
        total_stats["total_urls_updated"] += stats["updated"]
        total_stats["total_urls_created"] += stats["created"]
        total_stats["total_urls_skipped"] += stats["skipped"]
        total_stats["total_errors"] += stats["errors"]
        total_stats["by_spreadsheet"][spreadsheet_id] = stats
        
        if stats["errors"] == 0:
            total_stats["spreadsheets_success"] += 1
        else:
            total_stats["spreadsheets_failed"] += 1
    
    # Итоговая статистика
    logger.info("ИТОГОВАЯ СТАТИСТИКА")
    logger.info(f"Таблиц обработано: {total_stats['spreadsheets_processed']}")
    logger.info(f"Таблиц успешно: {total_stats['spreadsheets_success']}")
    logger.info(f"Таблиц с ошибками: {total_stats['spreadsheets_failed']}")
    logger.info(f"URL обработано: {total_stats['total_urls_processed']}")
    logger.info(f"URL обновлено: {total_stats['total_urls_updated']}")
    logger.info(f"URL создано: {total_stats['total_urls_created']}")
    logger.info(f"URL пропущено: {total_stats['total_urls_skipped']}")
    logger.info(f"Ошибок: {total_stats['total_errors']}")
    
    return total_stats


if __name__ == "__main__":
    """
    Тестовый запуск - обновляет Google Таблицы на основе metagenerator_batch_results.json
    """
    # Определяем пути
    project_root = Path(__file__).parent.parent
    input_file = project_root / "jsontests" / "metagenerator_batch_results.json"
    
    logger.info("Загрузка данных из metagenerator_batch_results.json...")
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    logger.info(f"[OK] Загружено данных для {len(data)} таблиц")
    
    # Обновляем все таблицы (батчевое обновление)
    stats = update_all_spreadsheets(
        data=data,
        sheet_name="Meta"
    )
    
    # Сохраняем статистику
    output_file = project_root / "jsontests" / "sheets_update_stats.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Статистика сохранена в: {output_file}")
