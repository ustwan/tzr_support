"""
Rate limiter для ограничения частоты обращений.
5 сообщений в 10 минут от одного Telegram ID.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict


class RateLimiter:
    """Rate limiter с персистентностью."""
    
    def __init__(self, storage_file='rate_limit.json', max_requests=5, window_minutes=10):
        self.storage_file = Path(storage_file)
        self.max_requests = max_requests
        self.window_minutes = window_minutes
        self.requests = self._load()
    
    def _load(self):
        """Загружает данные из файла."""
        if self.storage_file.exists():
            try:
                with open(self.storage_file, 'r') as f:
                    data = json.load(f)
                    # Конвертируем строки дат обратно в datetime
                    result = {}
                    for user_id, timestamps in data.items():
                        result[int(user_id)] = [
                            datetime.fromisoformat(ts) for ts in timestamps
                        ]
                    return result
            except:
                pass
        
        return {}
    
    def _save(self):
        """Сохраняет данные в файл."""
        # Конвертируем datetime в строки для JSON
        data = {}
        for user_id, timestamps in self.requests.items():
            data[str(user_id)] = [ts.isoformat() for ts in timestamps]
        
        with open(self.storage_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _cleanup_old(self, user_id):
        """Удаляет старые запросы вне окна."""
        if user_id not in self.requests:
            return
        
        cutoff = datetime.now() - timedelta(minutes=self.window_minutes)
        self.requests[user_id] = [
            ts for ts in self.requests[user_id] if ts > cutoff
        ]
        
        if not self.requests[user_id]:
            del self.requests[user_id]
    
    def check(self, user_id):
        """
        Проверяет можно ли пользователю отправить обращение.
        
        Returns:
            tuple: (allowed: bool, remaining: int, reset_in_seconds: int)
        """
        self._cleanup_old(user_id)
        
        if user_id not in self.requests:
            self.requests[user_id] = []
        
        count = len(self.requests[user_id])
        remaining = self.max_requests - count
        
        if count >= self.max_requests:
            # Лимит превышен
            oldest = min(self.requests[user_id])
            reset_at = oldest + timedelta(minutes=self.window_minutes)
            reset_in_seconds = int((reset_at - datetime.now()).total_seconds())
            return (False, 0, reset_in_seconds)
        
        return (True, remaining, 0)
    
    def record(self, user_id):
        """Записывает новый запрос."""
        self._cleanup_old(user_id)
        
        if user_id not in self.requests:
            self.requests[user_id] = []
        
        self.requests[user_id].append(datetime.now())
        self._save()
    
    def reset(self, user_id):
        """Сбрасывает лимит для пользователя."""
        if user_id in self.requests:
            del self.requests[user_id]
            self._save()


# Singleton instance
_limiter = None

def get_limiter():
    """Получает глобальный экземпляр rate limiter."""
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter('/app/logs/rate_limit.json', max_requests=5, window_minutes=10)
    return _limiter

