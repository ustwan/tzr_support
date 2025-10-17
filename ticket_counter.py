"""
Счетчик тикетов с сохранением в файл.
Генерирует уникальные номера для обращений.
"""

import os
import json
from pathlib import Path
from datetime import datetime


class TicketCounter:
    """Счетчик тикетов с персистентностью."""
    
    def __init__(self, counter_file='ticket_counter.json'):
        self.counter_file = Path(counter_file)
        self.data = self._load()
    
    def _load(self):
        """Загружает данные из файла."""
        if self.counter_file.exists():
            try:
                with open(self.counter_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        
        # Начальное состояние
        return {
            'site': 0,
            'tg': 0,
            'last_updated': None
        }
    
    def _save(self):
        """Сохраняет данные в файл."""
        self.data['last_updated'] = datetime.now().isoformat()
        with open(self.counter_file, 'w') as f:
            json.dump(self.data, f, indent=2)
    
    def get_next_site(self):
        """Получает следующий номер для обращения с сайта."""
        self.data['site'] += 1
        self._save()
        return f"ticket_site_{self.data['site']}"
    
    def get_next_tg(self):
        """Получает следующий номер для обращения из Telegram."""
        self.data['tg'] += 1
        self._save()
        return f"ticket_tg_{self.data['tg']}"
    
    def get_stats(self):
        """Возвращает статистику."""
        return {
            'site_total': self.data['site'],
            'tg_total': self.data['tg'],
            'total': self.data['site'] + self.data['tg'],
            'last_updated': self.data['last_updated']
        }


# Singleton instance
_counter = None

def get_counter():
    """Получает глобальный экземпляр счетчика."""
    global _counter
    if _counter is None:
        _counter = TicketCounter('/app/logs/ticket_counter.json')
    return _counter

