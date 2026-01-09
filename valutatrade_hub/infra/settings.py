"""
SettingsLoader - Singleton для загрузки и управления конфигурацией приложения.
Реализация через __new__ для простоты и читабельности.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import tomli


class SettingsLoader:
    """
    Singleton для загрузки конфигурации.
    Реализация через __new__ выбрана для простоты и понятности кода.
    Альтернатива через метакласс была бы избыточной для данной задачи.
    """
    
    _instance: Optional['SettingsLoader'] = None
    _config: Dict[str, Any] = {}
    _initialized: bool = False
    
    def __new__(cls):
        """Реализация паттерна Singleton через переопределение __new__"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Инициализация конфигурации (выполняется только один раз)"""
        if not self._initialized:
            self._load_configuration()
            self._initialized = True
    
    def _load_configuration(self):
        """Загрузка конфигурации из различных источников"""
        # Базовые значения по умолчанию
        self._config = {
            # Пути к данным
            "data_dir": "data",
            "users_file": "users.json",
            "portfolios_file": "portfolios.json",
            "rates_file": "rates.json",
            
            # Настройки курсов валют
            "rates_ttl_seconds": 300,  # 5 минут
            "default_base_currency": "USD",
            
            # Настройки логирования
            "log_dir": "logs",
            "log_file": "actions.log",
            "log_level": "INFO",
            "log_format": "detailed",  # 'detailed' или 'json'
            "log_max_size_mb": 10,  # Максимальный размер файла лога в МБ
            "log_backup_count": 5,  # Количество бэкап файлов
            
            # Настройки приложения
            "initial_usd_balance": 1000.0,
            "supported_currencies": ["USD", "EUR", "RUB", "BTC", "ETH", "GBP", "JPY", "CNY", "LTC", "XRP", "DOGE"], # noqa: E501
            
            # Параметры API (заглушка для Parser Service)
            "api_simulate_errors": False,  # Симулировать ошибки API для тестирования
            "api_error_probability": 0.2,  # Вероятность ошибки API (0.0-1.0)
        }
        
        # Пытаемся загрузить конфигурацию из pyproject.toml
        self._load_from_pyproject()
        
        # Пытаемся загрузить конфигурацию из config.json
        self._load_from_json()
        
        # Применяем относительные пути
        base_dir = Path(__file__).parent.parent.parent
        self._config["data_dir"] = str(base_dir / self._config["data_dir"])
        self._config["log_dir"] = str(base_dir / self._config["log_dir"])
    
    def _load_from_pyproject(self):
        """Загрузка конфигурации из pyproject.toml"""
        try:
            pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
            if pyproject_path.exists():
                with open(pyproject_path, "rb") as f:
                    data = tomli.load(f)
                
                if "tool" in data and "valutatrade" in data["tool"]:
                    config = data["tool"]["valutatrade"]
                    
                    # Обновляем конфигурацию
                    for key, value in config.items():
                        if key in self._config:
                            self._config[key] = value
                        else:
                            # Добавляем новые ключи
                            self._config[key] = value
        except (FileNotFoundError, KeyError, tomli.TOMLDecodeError):
            # Если файл не найден или некорректен, используем значения по умолчанию
            pass
    
    def _load_from_json(self):
        """Загрузка конфигурации из config.json"""
        try:
            config_path = Path(__file__).parent.parent.parent / "config.json"
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                
                # Обновляем конфигурацию
                for key, value in config.items():
                    if key in self._config:
                        self._config[key] = value
                    else:
                        # Добавляем новые ключи
                        self._config[key] = value
        except (FileNotFoundError, json.JSONDecodeError):
            # Если файл не найден или некорректен, используем значения по умолчанию
            pass
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Получение значения конфигурации по ключу.
        
        Args:
            key: Ключ конфигурации
            default: Значение по умолчанию, если ключ не найден
        
        Returns:
            Значение конфигурации или default
        """
        return self._config.get(key, default)
    
    def reload(self):
        """Перезагрузка конфигурации из файлов"""
        self._initialized = False
        self._config.clear()
        self.__init__()
    
    def get_all(self) -> Dict[str, Any]:
        """
        Получение всей конфигурации.
        
        Returns:
            Словарь со всей конфигурацией
        """
        return self._config.copy()
    
    def set(self, key: str, value: Any):
        """
        Установка значения конфигурации (только для текущей сессии).
        
        Args:
            key: Ключ конфигурации
            value: Значение
        """
        self._config[key] = value
    
    def get_data_path(self, filename: str = "") -> str:
        """
        Получение полного пути к файлу в директории данных.
        
        Args:
            filename: Имя файла (опционально)
        
        Returns:
            Полный путь к файлу
        """
        data_dir = self.get("data_dir", "data")
        if filename:
            return os.path.join(data_dir, filename)
        return data_dir
    
    def get_log_path(self, filename: str = "") -> str:
        """
        Получение полного пути к файлу в директории логов.
        
        Args:
            filename: Имя файла (опционально)
        
        Returns:
            Полный путь к файлу
        """
        log_dir = self.get("log_dir", "logs")
        if filename:
            return os.path.join(log_dir, filename)
        return log_dir


# Создаем глобальный экземпляр для удобного доступа
_settings: Optional[SettingsLoader] = None

def get_settings() -> SettingsLoader:
    """
    Получение экземпляра SettingsLoader (глобальный доступ).
    
    Returns:
        Экземпляр SettingsLoader
    """
    global _settings
    if _settings is None:
        _settings = SettingsLoader()
    return _settings