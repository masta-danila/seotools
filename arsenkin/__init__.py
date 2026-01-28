"""
Модуль для работы с API Arsenkin Tools
Получение топ-10 результатов поисковой выдачи
"""

from .search_parser import (
    get_top_results,
    save_results_to_json,
    create_task,
    check_task_status,
    get_task_result,
    wait_for_task,
    parse_top_results
)

__all__ = [
    'get_top_results',
    'save_results_to_json',
    'create_task',
    'check_task_status',
    'get_task_result',
    'wait_for_task',
    'parse_top_results'
]

__version__ = '1.0.0'
__author__ = 'Articulus'
__description__ = 'API клиент для получения топ-10 поисковой выдачи через Arsenkin Tools'
