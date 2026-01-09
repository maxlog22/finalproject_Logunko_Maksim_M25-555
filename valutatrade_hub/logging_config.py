"""
Настройка логирования для ValutaTrade Hub
"""

import json
import logging
import logging.handlers
import os
from datetime import datetime

from .infra.settings import get_settings


def setup_logging():
    """
    Настройка системы логирования
    """
    settings = get_settings()
    
    # Создаем директорию для логов, если она не существует
    log_dir = settings.get_log_path()
    os.makedirs(log_dir, exist_ok=True)
    
    # Получаем настройки логирования
    log_file = settings.get_log_path(settings.get("log_file", "actions.log"))
    log_level = settings.get("log_level", "INFO").upper()
    log_format_type = settings.get("log_format", "detailed")
    max_size_mb = settings.get("log_max_size_mb", 10)
    backup_count = settings.get("log_backup_count", 5)
    
    # Создаем корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Очищаем существующие обработчики
    root_logger.handlers.clear()
    
    # Создаем форматтер в зависимости от типа
    if log_format_type == "json":
        formatter = JSONFormatter()
    else:
        formatter = DetailedFormatter()
    
    # Обработчик для файла с ротацией
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_file,
        maxBytes=max_size_mb * 1024 * 1024,  # Конвертируем МБ в байты
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)
    
    # Обработчик для консоли ТОЛЬКО для ошибок и выше
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.WARNING)  # Только WARNING и выше
    
    # Фильтр, чтобы исключить логгер "actions" из вывода в консоль
    class ExcludeActionsFilter(logging.Filter):
        def filter(self, record):
            # Исключаем записи от логгера "actions"
            return record.name != "actions"
    
    # Добавляем фильтр к консольному обработчику
    console_handler.addFilter(ExcludeActionsFilter())
    
    # Добавляем обработчики к корневому логгеру
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Создаем логгер для действий с отдельной настройкой
    action_logger = logging.getLogger("actions")
    action_logger.setLevel(log_level)
    action_logger.propagate = False  # Не пропускаем события в корневой логгер
    
    # Добавляем ТОЛЬКО файловый обработчик для логгера действий
    action_file_handler = logging.handlers.RotatingFileHandler(
        filename=log_file,
        maxBytes=max_size_mb * 1024 * 1024,
        backupCount=backup_count,
        encoding='utf-8'
    )
    action_file_handler.setFormatter(formatter)
    action_file_handler.setLevel(log_level)
    action_logger.addHandler(action_file_handler)
    
    # НЕ логируем начало работы в консоль, только в файл
    # Записываем в файл, но не в консоль
    action_logger.info("=" * 60)
    action_logger.info("ValutaTrade Hub - Начало работы")
    action_logger.info(f"Директория логов: {log_dir}")
    action_logger.info(f"Уровень логирования: {log_level}")
    action_logger.info(f"Формат логов: {log_format_type}")
    action_logger.info("=" * 60)


class DetailedFormatter(logging.Formatter):
    """Форматтер для читаемых логов"""
    
    def __init__(self):
        super().__init__(
            fmt='%(levelname)-8s %(asctime)s %(action)s %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    def format(self, record):
        # Добавляем действие, если оно не указано
        if not hasattr(record, 'action'):
            record.action = ''
        
        # Форматируем время
        record.asctime = self.formatTime(record, self.datefmt)
        
        return super().format(record)


class JSONFormatter(logging.Formatter):
    """Форматтер для логов в формате JSON"""
    
    def format(self, record):
        log_record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Добавляем дополнительные поля из record
        for key, value in record.__dict__.items():
            if key not in ['args', 'created', 'exc_info', 'exc_text', 'filename', 
                          'funcName', 'levelname', 'levelno', 'lineno', 'module', 
                          'msecs', 'message', 'msg', 'name', 'pathname', 'process', 
                          'processName', 'relativeCreated', 'stack_info', 'thread', 
                          'threadName', 'asctime']:
                if key == 'action':
                    log_record[key] = value
                elif isinstance(value, (str, int, float, bool, type(None))):
                    log_record[key] = value
                else:
                    log_record[key] = str(value)
        
        # Добавляем информацию об исключении, если есть
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_record, ensure_ascii=False)


# Глобальная функция для быстрой настройки логирования
def configure_logging():
    """Настройка логирования (вызывается при старте приложения)"""
    setup_logging()