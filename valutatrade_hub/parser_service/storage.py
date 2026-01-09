"""
Модуль для работы с хранилищем курсов валют.
Обеспечивает чтение и запись файлов rates.json и exchange_rates.json.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Исправляем импорт
try:
    # Пытаемся импортировать абсолютным путем
    from valutatrade_hub.infra.database import get_database
except ImportError:
    # Если не сработает, используем относительный
    from ...infra.database import get_database



class RatesStorage:
    """Класс для работы с хранилищем курсов валют."""
    
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger("parser.storage")
        self.db = get_database()
        
        # Создаем директорию для данных, если она не существует
        self.data_dir = Path(self.config.BASE_DATA_DIR)
        self.data_dir.mkdir(exist_ok=True)
        
        self.rates_file = self.data_dir / self.config.RATES_FILE
        self.history_file = self.data_dir / self.config.EXCHANGE_RATES_FILE
    
    def load_rates(self) -> Dict[str, Any]:
        """
        Загрузить текущие курсы из файла rates.json через DatabaseManager.
        
        Returns:
            Словарь с курсами или пустой словарь
        """
        rates_data = self.db.get_rates()
        self.logger.debug(f"Загружено {len(rates_data.get('pairs', {}))} курсов из rates.json") # noqa: E501
        return rates_data
    
    def save_rates(self, rates_data: Dict[str, Any]):
        """
        Сохранить текущие курсы в файл rates.json через DatabaseManager.
        
        Args:
            rates_data: Данные для сохранения
        """
        try:
            self.db.save_rates(rates_data)
            self.logger.info(f"Сохранено {len(rates_data.get('pairs', {}))} курсов в rates.json") # noqa: E501
            
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении rates.json: {e}")
            raise
    
    def load_history(self) -> List[Dict[str, Any]]:
        """
        Загрузить историю курсов из файла exchange_rates.json через DatabaseManager.
        
        Returns:
            Список исторических записей
        """
        history_data = self.db.get_exchange_rates_history()
        self.logger.debug(f"Загружено {len(history_data)} исторических записей")
        return history_data
    
    def save_history(self, history_data: List[Dict[str, Any]]):
        """
        Сохранить историю курсов в файл exchange_rates.json через DatabaseManager.
        
        Args:
            history_data: Исторические данные для сохранения
        """
        try:
            self.db.save_exchange_rates_history(history_data)
            self.logger.info(f"Сохранено {len(history_data)} исторических записей")
            
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении exchange_rates.json: {e}")
            raise
    
    def add_history_record(self, record: Dict[str, Any]):
        """
        Добавить одну запись в историю.
        
        Args:
            record: Запись для добавления
        """
        try:
            # Загружаем существующую историю
            history = self.load_history()
            
            # Добавляем новую запись
            history.append(record)
            
            # Сохраняем обратно
            self.save_history(history)
            
            self.logger.debug(f"Добавлена историческая запись: {record.get('id', 'unknown')}") # noqa: E501
            
        except Exception as e:
            self.logger.error(f"Ошибка при добавлении исторической записи: {e}")
    
    def cleanup_old_history(self, max_records: int = 1000):
        """
        Очистить старые записи из истории.
        
        Args:
            max_records: Максимальное количество записей для хранения
        """
        try:
            history = self.load_history()
            
            if len(history) > max_records:
                # Оставляем только последние max_records записей
                history = history[-max_records:]
                self.save_history(history)
                self.logger.info(f"Очищена история, оставлено {len(history)} записей")
                
        except Exception as e:
            self.logger.error(f"Ошибка при очистке истории: {e}")
    
    def validate_rate(self, rate: float, currency_pair: str) -> bool:
        """
        Проверить валидность курса.
        
        Args:
            rate: Значение курса
            currency_pair: Валютная пара
            
        Returns:
            True если курс валиден
        """
        if not isinstance(rate, (int, float)):
            self.logger.warning(f"Некорректный тип курса для {currency_pair}: {type(rate)}") # noqa: E501
            return False
        
        if rate < self.config.MIN_RATE_VALUE:
            self.logger.warning(f"Курс для {currency_pair} слишком мал: {rate}")
            return False
        
        if rate > self.config.MAX_RATE_VALUE:
            self.logger.warning(f"Курс для {currency_pair} слишком велик: {rate}")
            return False
        
        # Проверка на NaN и бесконечность
        import math
        if math.isnan(rate) or math.isinf(rate):
            self.logger.warning(f"Курс для {currency_pair} не является числом: {rate}")
            return False
        
        return True
    
    def create_history_record(self, 
                            from_currency: str, 
                            to_currency: str, 
                            rate: float, 
                            source: str,
                            meta: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Создать историческую запись.
        
        Args:
            from_currency: Исходная валюта
            to_currency: Целевая валюта
            rate: Значение курса
            source: Источник данных
            meta: Дополнительные метаданные
            
        Returns:
            Словарь с исторической записью
        """
        timestamp = datetime.now(timezone.utc)
        
        # Формируем уникальный ID
        from_upper = from_currency.upper()
        to_upper = to_currency.upper()
        timestamp_str = timestamp.isoformat().replace("+00:00", "Z")
        record_id = f"{from_upper}_{to_upper}_{timestamp_str}"
        
        record = {
            "id": record_id,
            "from_currency": from_upper,
            "to_currency": to_upper,
            "rate": rate,
            "timestamp": timestamp_str,
            "source": source,
            "meta": meta or {}
        }
        
        return record
    
    def backup_data(self):
        """Создать резервную копию данных."""
        try:
            self.db.backup_data()
            self.logger.info("Создана резервная копия данных")
        except Exception as e:
            self.logger.error(f"Ошибка при создании резервной копии: {e}")
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """
        Получить статистику хранилища.
        
        Returns:
            Словарь со статистикой
        """
        rates = self.load_rates()
        history = self.load_history()
        
        return {
            "rates": {
                "total_pairs": len(rates.get("pairs", {})),
                "last_refresh": rates.get("last_refresh"),
            },
            "history": {
                "total_records": len(history),
                "oldest_record": history[0]["timestamp"] if history else None,
                "newest_record": history[-1]["timestamp"] if history else None,
            },
            "storage": {
                "rates_file_size": self.rates_file.stat().st_size if self.rates_file.exists() else 0, # noqa: E501
                "history_file_size": self.history_file.stat().st_size if self.history_file.exists() else 0, # noqa: E501
            }
        }
    
