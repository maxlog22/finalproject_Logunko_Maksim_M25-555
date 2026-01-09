"""
Планировщик периодического обновления курсов валют.
"""

import logging
import threading
from datetime import datetime
from typing import Callable, Optional

import schedule

from .config import config
from .updater import RatesUpdater


class RatesScheduler:
    """Планировщик для периодического обновления курсов."""
    
    def __init__(self, updater: Optional[RatesUpdater] = None):
        self.updater = updater or RatesUpdater()
        self.logger = logging.getLogger("parser.scheduler")
        self.is_running = False
        self.scheduler_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        
        # Статистика
        self.schedule_stats = {
            "scheduled_updates": 0,
            "last_scheduled_update": None,
            "next_scheduled_update": None
        }
    
    def start(self, interval_minutes: Optional[int] = None):
        """
        Запустить планировщик.
        
        Args:
            interval_minutes: Интервал обновления в минутах (по умолчанию из конфига)
        """
        if self.is_running:
            self.logger.warning("Планировщик уже запущен")
            return
        
        interval = interval_minutes or (config.UPDATE_INTERVAL // 60)
        
        self.logger.info(f"Запуск планировщика с интервалом {interval} минут")
        
        # Настраиваем расписание
        schedule.clear()  # Очищаем существующее расписание
        schedule.every(interval).minutes.do(self._scheduled_update)
        
        # Запускаем фоновый поток
        self.is_running = True
        self.stop_event.clear()
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True) # noqa: E501
        self.scheduler_thread.start()
        
        # Запланировать первое обновление
        next_run = schedule.next_run()
        self.schedule_stats["next_scheduled_update"] = next_run.isoformat() if next_run else None # noqa: E501
        
        self.logger.info("Планировщик запущен")
    
    def stop(self):
        """Остановить планировщик."""
        if not self.is_running:
            self.logger.warning("Планировщик не запущен")
            return
        
        self.logger.info("Остановка планировщика...")
        self.is_running = False
        self.stop_event.set()
        
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=10)
        
        schedule.clear()
        self.logger.info("Планировщик остановлен")
    
    def _run_scheduler(self):
        """Основной цикл планировщика."""
        self.logger.info("Фоновый поток планировщика запущен")
        
        while not self.stop_event.is_set():
            try:
                schedule.run_pending()
            except Exception as e:
                self.logger.error(f"Ошибка в планировщике: {e}")
            
            # Ждем 1 секунду перед следующей проверкой
            self.stop_event.wait(1)
        
        self.logger.info("Фоновый поток планировщика завершен")
    
    def _scheduled_update(self):
        """Выполнить запланированное обновление."""
        self.logger.info("Запуск запланированного обновления...")
        
        try:
            result = self.updater.run_update()
            
            # Обновляем статистику
            self.schedule_stats["scheduled_updates"] += 1
            self.schedule_stats["last_scheduled_update"] = datetime.now().isoformat()
            
            next_run = schedule.next_run()
            self.schedule_stats["next_scheduled_update"] = next_run.isoformat() if next_run else None # noqa: E501
            
            if result.get("success"):
                self.logger.info(
                    f"Запланированное обновление завершено: "
                    f"обновлено {result.get('updated_pairs', 0)}, "
                    f"новых {result.get('new_pairs', 0)}"
                )
            else:
                self.logger.error(f"Запланированное обновление завершилось с ошибкой: {result.get('message')}") # noqa: E501
                
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка при запланированном обновлении: {e}")
    
    def run_once(self) -> dict:
        """
        Выполнить однократное обновление.
        
        Returns:
            Результат обновления
        """
        self.logger.info("Запуск однократного обновления...")
        return self.updater.run_update()
    
    def get_schedule_info(self) -> dict:
        """
        Получить информацию о расписании.
        
        Returns:
            Словарь с информацией о расписании
        """
        jobs = schedule.get_jobs()
        
        schedule_info = {
            "is_running": self.is_running,
            "jobs": [
                {
                    "next_run": job.next_run.isoformat() if job.next_run else None,
                    "interval": str(job.interval) if hasattr(job, 'interval') else None
                }
                for job in jobs
            ],
            "stats": self.schedule_stats.copy()
        }
        
        return schedule_info
    
    def add_custom_schedule(self, 
                          interval_minutes: int, 
                          callback: Optional[Callable] = None):
        """
        Добавить пользовательское расписание.
        
        Args:
            interval_minutes: Интервал в минутах
            callback: Функция для вызова (по умолчанию обновление курсов)
        """
        if callback is None:
            callback = self._scheduled_update
        
        schedule.every(interval_minutes).minutes.do(callback)
        self.logger.info(f"Добавлено пользовательское расписание: каждые {interval_minutes} минут") # noqa: E501
    
    def run_at_time(self, time_str: str):
        """
        Запускать обновление в указанное время каждый день.
        
        Args:
            time_str: Время в формате "HH:MM"
        """
        try:
            schedule.every().day.at(time_str).do(self._scheduled_update)
            self.logger.info(f"Добавлено ежедневное обновление в {time_str}")
        except Exception as e:
            self.logger.error(f"Ошибка при добавлении расписания на время: {e}")