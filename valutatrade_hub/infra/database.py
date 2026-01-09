"""
Singleton DatabaseManager для работы с JSON-хранилищем.
Абстракция над файловой системой для работы с данными приложения.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .settings import get_settings


class DatabaseManager:
    """
    Singleton для работы с JSON файлами данных.
    Реализует паттерн Singleton для обеспечения единой точки доступа к данным.
    """
    
    _instance: Optional['DatabaseManager'] = None
    _initialized: bool = False
    
    def __new__(cls):
        """Реализация паттерна Singleton."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Инициализация менеджера базы данных."""
        if not self._initialized:
            self.settings = get_settings()
            self.logger = logging.getLogger("database")
            
            # Создаем директорию данных, если она не существует
            self.data_dir = Path(self.settings.get_data_path())
            self.data_dir.mkdir(parents=True, exist_ok=True)
            
            self._initialized = True
    
    def _get_file_path(self, file_name: str) -> Path:
        """
        Получить полный путь к файлу данных.
        
        Args:
            file_name: Имя файла
            
        Returns:
            Полный путь Path
        """
        return self.data_dir / file_name
    
    def read_json(self, file_name: str) -> List[Dict]:
        """
        Чтение JSON файла из директории данных.
        
        Args:
            file_name: Имя файла
            
        Returns:
            Список словарей с данными
        """
        file_path = self._get_file_path(file_name)
        
        if not file_path.exists():
            self.logger.debug(f"Файл {file_name} не существует, возвращаем пустой список") # noqa: E501
            return []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Обработка специальных случаев
            if file_name == "rates.json" and isinstance(data, dict):
                return [data]
            elif isinstance(data, list):
                return data
            else:
                return [data]
                
        except json.JSONDecodeError as e:
            self.logger.error(f"Ошибка декодирования JSON в файле {file_name}: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Ошибка при чтении файла {file_name}: {e}")
            return []
    
    def write_json(self, file_name: str, data: Any):
        """
        Запись данных в JSON файл.
        
        Args:
            file_name: Имя файла
            data: Данные для записи
        """
        file_path = self._get_file_path(file_name)
        
        try:
            # Для rates.json сохраняем как словарь
            if file_name == "rates.json":
                if isinstance(data, list) and len(data) == 1:
                    data_to_write = data[0]
                elif isinstance(data, dict):
                    data_to_write = data
                else:
                    data_to_write = data
            else:
                data_to_write = data
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_write, f, indent=2, ensure_ascii=False, default=str) # noqa: E501
            
            self.logger.debug(f"Данные успешно записаны в {file_name}")
            
        except Exception as e:
            self.logger.error(f"Ошибка при записи в файл {file_name}: {e}")
            raise
    
    def get_users(self) -> List[Dict]:
        """Получить список всех пользователей."""
        return self.read_json("users.json")
    
    def save_users(self, users: List[Dict]):
        """Сохранить список пользователей."""
        self.write_json("users.json", users)
    
    def get_portfolios(self) -> List[Dict]:
        """Получить список всех портфелей."""
        return self.read_json("portfolios.json")
    
    def save_portfolios(self, portfolios: List[Dict]):
        """Сохранить список портфелей."""
        self.write_json("portfolios.json", portfolios)
    
    def get_rates(self) -> Dict:
        """Получить текущие курсы валют."""
        rates_list = self.read_json("rates.json")
        
        if not rates_list:
            return {"pairs": {}, "last_refresh": None}
        
        rates_data = rates_list[0] if isinstance(rates_list, list) and rates_list else rates_list # noqa: E501
        
        # Убедимся в правильной структуре
        if not isinstance(rates_data, dict):
            return {"pairs": {}, "last_refresh": None}
        
        if "pairs" not in rates_data:
            rates_data["pairs"] = {}
        
        if "last_refresh" not in rates_data:
            rates_data["last_refresh"] = None
        
        return rates_data
    
    def save_rates(self, rates_data: Dict):
        """Сохранить курсы валют."""
        self.write_json("rates.json", rates_data)
    
    def get_exchange_rates_history(self) -> List[Dict]:
        """Получить историю курсов валют."""
        return self.read_json("exchange_rates.json")
    
    def save_exchange_rates_history(self, history: List[Dict]):
        """Сохранить историю курсов валют."""
        self.write_json("exchange_rates.json", history)
    
    def backup_data(self, backup_name: str = None):
        """
        Создать резервную копию всех данных.
        
        Args:
            backup_name: Имя резервной копии (по умолчанию: timestamp)
        """
        import shutil
        from datetime import datetime
        
        if backup_name is None:
            backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        backup_dir = self.data_dir / "backups" / backup_name
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Копируем все JSON файлы
        for file_path in self.data_dir.glob("*.json"):
            if file_path.is_file():
                shutil.copy2(file_path, backup_dir / file_path.name)
        
        self.logger.info(f"Создана резервная копия данных в {backup_dir}")
    
    def cleanup_old_backups(self, keep_last: int = 5):
        """
        Удалить старые резервные копии.
        
        Args:
            keep_last: Сколько последних копий оставить
        """
        import shutil
        from datetime import datetime
        
        backups_dir = self.data_dir / "backups"
        if not backups_dir.exists():
            return
        
        # Получаем все поддиректории и сортируем по дате создания
        backup_dirs = []
        for item in backups_dir.iterdir():
            if item.is_dir():
                try:
                    # Пытаемся извлечь дату из имени директории
                    if item.name.startswith("backup_"):
                        date_str = item.name[7:]  # Убираем "backup_"
                        # Пытаемся распарсить дату
                        try:
                            dt = datetime.strptime(date_str, "%Y%m%d_%H%M%S")
                        except ValueError:
                            dt = datetime.fromtimestamp(item.stat().st_mtime)
                    else:
                        dt = datetime.fromtimestamp(item.stat().st_mtime)
                    
                    backup_dirs.append((dt, item))
                except Exception:
                    continue
        
        # Сортируем по дате (старые первыми)
        backup_dirs.sort(key=lambda x: x[0])
        
        # Удаляем старые копии, оставляя только keep_last последних
        for dt, backup_dir in backup_dirs[:-keep_last]:
            try:
                shutil.rmtree(backup_dir)
                self.logger.debug(f"Удалена старая резервная копия: {backup_dir.name}") # noqa: E501
            except Exception as e:
                self.logger.error(f"Ошибка при удалении резервной копии {backup_dir.name}: {e}") # noqa: E501


# Фабричная функция для удобного доступа
def get_database() -> DatabaseManager:
    """
    Получить экземпляр DatabaseManager.
    
    Returns:
        Экземпляр DatabaseManager
    """
    return DatabaseManager()