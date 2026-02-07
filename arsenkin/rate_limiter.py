"""
Глобальный rate limiter для управления запросами к Arsenkin API
Реализует скользящее окно для точного контроля лимита 30 запросов/минуту
"""
import asyncio
import time
from collections import deque
from typing import Dict
import sys
from pathlib import Path

# Добавляем корень проекта в путь для импорта
sys.path.insert(0, str(Path(__file__).parent.parent))

from logger_config import get_search_logger

logger = get_search_logger()


class AsyncRateLimiter:
    """
    Глобальный rate limiter со скользящим окном для Arsenkin API
    Ограничение: 30 запросов в минуту
    
    Использует скользящее окно для точного отслеживания запросов,
    обеспечивая безопасную параллельную работу через asyncio.Lock
    """
    
    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        """
        Args:
            max_requests: Максимальное количество запросов в окне (по умолчанию 30)
            window_seconds: Размер окна в секундах (по умолчанию 60)
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.request_times = deque()
        self._lock = asyncio.Lock()
        self._total_requests = 0
        self._total_waits = 0
        self._total_wait_time = 0.0
    
    async def acquire(self) -> None:
        """
        Ожидает, пока не станет доступен слот для запроса
        
        Автоматически удаляет старые запросы из окна и ждёт,
        если достигнут лимит запросов
        """
        async with self._lock:
            now = time.time()
            
            # Удаляем запросы старше окна
            while self.request_times and now - self.request_times[0] > self.window_seconds:
                self.request_times.popleft()
            
            # Если достигли лимита, ждём
            if len(self.request_times) >= self.max_requests:
                oldest_request = self.request_times[0]
                wait_time = self.window_seconds - (now - oldest_request) + 0.1  # +0.1 для безопасности
                
                logger.debug(f"[RateLimiter] Достигнут лимит {self.max_requests} запросов. Ожидание {wait_time:.1f}s")
                self._total_waits += 1
                self._total_wait_time += wait_time
                
                await asyncio.sleep(wait_time)
                # Рекурсивно пробуем снова после ожидания
                return await self.acquire()
            
            # Регистрируем новый запрос
            self.request_times.append(now)
            self._total_requests += 1
    
    def get_stats(self) -> Dict:
        """
        Возвращает текущую статистику использования
        
        Returns:
            Словарь со статистикой: active_requests, max_requests, available_slots,
            total_requests, total_waits, avg_wait_time
        """
        now = time.time()
        # Считаем активные запросы в текущем окне
        active_requests = sum(1 for t in self.request_times if now - t <= self.window_seconds)
        
        return {
            "active_requests": active_requests,
            "max_requests": self.max_requests,
            "available_slots": self.max_requests - active_requests,
            "total_requests": self._total_requests,
            "total_waits": self._total_waits,
            "total_wait_time": round(self._total_wait_time, 2),
            "avg_wait_time": round(self._total_wait_time / self._total_waits, 2) if self._total_waits > 0 else 0
        }
    
    def reset_stats(self) -> None:
        """Сбрасывает статистику (но не очищает окно запросов)"""
        self._total_requests = 0
        self._total_waits = 0
        self._total_wait_time = 0.0


# Глобальный экземпляр rate limiter для всех запросов к Arsenkin API
_global_rate_limiter = AsyncRateLimiter(max_requests=30, window_seconds=60)


def get_rate_limiter() -> AsyncRateLimiter:
    """
    Возвращает глобальный экземпляр rate limiter
    
    Returns:
        AsyncRateLimiter: Глобальный rate limiter
    """
    return _global_rate_limiter
