"""
Утилиты для ValutaTrade Hub.
Включает валидации валютных кодов, конвертации и работу с JSON.
"""

import hashlib
import json  # Добавлен импорт
import random
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from ..infra.database import get_database
from ..infra.settings import get_settings
from .exceptions import ApiRequestError


def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """Хеширование пароля с солью."""
    if salt is None:
        salt = hashlib.sha256(str(datetime.now().timestamp()).encode()).hexdigest()[:8]
    
    hashed = hashlib.sha256((password + salt).encode()).hexdigest()
    return hashed, salt


def get_next_user_id() -> int:
    """Получение следующего ID пользователя."""
    users = read_json("users.json")
    if not users:
        return 1
    return max(user.get("user_id", 0) for user in users) + 1


def get_current_datetime() -> str:
    """Получение текущей даты-времени в строковом формате ISO."""
    return datetime.now().isoformat()


def read_json(file_name: str) -> List[Dict]:
    """Чтение JSON файла из директории данных через DatabaseManager."""
    db = get_database()
    return db.read_json(file_name)


def write_json(file_name: str, data):
    """Запись в JSON файл в директории данных через DatabaseManager."""
    db = get_database()
    db.write_json(file_name, data)


def load_exchange_rates() -> Dict:
    """Загрузка курсов валют из файла rates.json через DatabaseManager."""
    db = get_database()
    return db.get_rates()


def _simulate_rate_update():
    """Симуляция обновления курсов (запасной вариант)."""
    # Симулируем задержку запроса
    time.sleep(1)
    
    # Проверяем настройки для симуляции ошибок
    settings = get_settings()
    simulate_errors = settings.get("api_simulate_errors", False)
    error_probability = settings.get("api_error_probability", 0.2)
    
    if simulate_errors and random.random() < error_probability:
        raise ApiRequestError("Сервер курсов валют временно недоступен")
    
    # Загружаем текущие курсы
    rates = load_exchange_rates()
    current_time = datetime.now(timezone.utc).isoformat()
    pairs = rates.get("pairs", {})
    
    # Симулируем небольшое изменение курса
    for key in list(pairs.keys()):
        if isinstance(pairs[key], dict) and 'rate' in pairs[key]:
            # Симулируем небольшое изменение курса
            if random.random() < 0.5:  # 50% вероятность изменения
                change = random.uniform(-0.01, 0.01)  # Изменение на ±1%
                pairs[key]['rate'] *= (1 + change)
                pairs[key]['rate'] = round(pairs[key]['rate'], 4)
            
            pairs[key]['updated_at'] = current_time
    
    rates['last_refresh'] = current_time
    
    # Сохраняем обновленные курсы
    write_json("rates.json", rates)
    
    print("⚠️  Использованы симулированные данные (Parser Service недоступен)")
    return rates


def update_rates_from_parser():
    """
    Интеграция с Parser Service для обновления курсов.
    Вызывается ТОЛЬКО по команде update-rates.
    """
    try:
        from ..parser_service.updater import RatesUpdater
        updater = RatesUpdater()
        result = updater.run_update(source="all")
        
        if result.get("success"):
            # Загружаем ОБНОВЛЕННЫЕ данные
            from ..infra.database import get_database
            db = get_database()
            updated_rates = db.get_rates()
            return updated_rates
        else:
            error_msg = result.get("message", "Неизвестная ошибка Parser Service")
            raise ApiRequestError(error_msg)
            
    except ImportError:
        raise ApiRequestError("Parser Service не доступен")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise ApiRequestError(f"Ошибка при обновлении через Parser Service: {e}")


def is_rate_fresh(rate_info: Dict) -> bool:
    """Проверка свежести курса на основе TTL из настроек."""
    settings = get_settings()
    ttl_seconds = settings.get("rates_ttl_seconds", 3600)  # Увеличиваем до 1 часа
    
    if "updated_at" not in rate_info:
        return False
    
    try:
        updated_at_str = rate_info["updated_at"].replace("Z", "+00:00")
        updated_at = datetime.fromisoformat(updated_at_str)
        now = datetime.now(updated_at.tzinfo) if updated_at.tzinfo else datetime.now()
        age = now - updated_at
        return age.total_seconds() < ttl_seconds
    except (ValueError, KeyError, AttributeError):
        return False

def validate_currency_code(code: str) -> bool:
    """
    Валидация кода валюты.
    
    Args:
        code: Код валюты для проверки
    
    Returns:
        True если код валиден, иначе False
    """
    from .currencies import currency_exists
    
    if not isinstance(code, str):
        return False
    
    code = code.strip().upper()
    
    # Проверка длины
    if not 2 <= len(code) <= 5:
        return False
    
    # Проверка символов (только буквы и цифры)
    if not code.isalnum():
        return False
    
    # Проверка существования в реестре
    return currency_exists(code)


def convert_currency(amount: float, from_currency: str, to_currency: str, rates: Dict) -> Optional[float]: # noqa: E501
    """
    Конвертация суммы из одной валюты в другую.
    
    Args:
        amount: Сумма для конвертации
        from_currency: Исходная валюта
        to_currency: Целевая валюта
        rates: Словарь с курсами (должен содержать ключ "pairs")
    
    Returns:
        Конвертированная сумма или None если курс недоступен
    """
    if from_currency == to_currency:
        return amount
    
    pairs = rates.get("pairs", {})
    
    # Прямой курс
    direct_key = f"{from_currency}_{to_currency}"
    if direct_key in pairs and 'rate' in pairs[direct_key]:
        return amount * pairs[direct_key]['rate']
    
    # Обратный курс
    reverse_key = f"{to_currency}_{from_currency}"
    if reverse_key in pairs and 'rate' in pairs[reverse_key]:
        return amount / pairs[reverse_key]['rate']
    
    # Попробуем через USD
    if from_currency != "USD" and to_currency != "USD":
        from_usd_key = f"{from_currency}_USD"
        usd_to_key = f"USD_{to_currency}"
        
        if (from_usd_key in pairs and 'rate' in pairs[from_usd_key] and
            usd_to_key in pairs and 'rate' in pairs[usd_to_key]):
            return amount * pairs[from_usd_key]['rate'] * pairs[usd_to_key]['rate']
    
    return None


def format_currency_amount(amount: float, currency_code: str) -> str:
    """
    Форматирование суммы валюты для отображения.
    
    Args:
        amount: Сумма
        currency_code: Код валюты
    
    Returns:
        Отформатированная строка
    """
    # Определяем формат в зависимости от типа валюты
    from .currencies import get_currency_registry
    
    try:
        registry = get_currency_registry()
        currency = registry.get_currency(currency_code)
        
        if hasattr(currency, 'issuing_country'):  # Фиатная валюта
            return f"{amount:,.2f}"
        else:  # Криптовалюта
            if abs(amount) < 0.01:
                return f"{amount:.6f}"
            elif abs(amount) < 1:
                return f"{amount:.4f}"
            else:
                return f"{amount:.2f}"
    except (ValueError, TypeError):
        # По умолчанию
        if currency_code in ["USD", "EUR", "RUB", "GBP", "JPY", "CNY"]:
            return f"{amount:,.2f}"
        else:
            return f"{amount:.4f}"


def safe_file_operation(file_path, operation: callable, default=None):
    """
    Безопасное выполнение операции с файлом.
    
    Args:
        file_path: Путь к файлу
        operation: Функция для выполнения
        default: Значение по умолчанию при ошибке
    
    Returns:
        Результат операции или default
    """
    try:
        return operation(file_path)
    except (IOError, OSError, json.JSONDecodeError) as e:
        print(f"Ошибка при работе с файлом {file_path}: {e}")
        return default