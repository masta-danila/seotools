"""
Модуль для работы с XMLRiver API (Яндекс поиск)
"""
from .single_search import search_yandex
from .yandex_parser import (
    get_top_results,
    parse_yandex_xml,
    process_url,
    process_sheets_data,
    save_results_to_json
)

__all__ = [
    'search_yandex',
    'get_top_results',
    'parse_yandex_xml',
    'process_url',
    'process_sheets_data',
    'save_results_to_json'
]
