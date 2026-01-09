"""
Декораторы для ValutaTrade Hub.
Основной декоратор @log_action для логирования операций.
"""

import functools
import logging
from datetime import datetime
from typing import Any, Callable, Dict


def log_action(action: str = "", verbose: bool = False):
    """
    Декоратор для логирования действий приложения
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            logger = logging.getLogger("actions")
            
            # Импортируем get_settings внутри функции, чтобы избежать циклических импортов # noqa: E501
            from .infra.settings import get_settings
            settings = get_settings()
            
            # Определяем действие
            action_name = action or func.__name__.upper()
            
            # Подготовка информации для лога
            log_info: Dict[str, Any] = {
                "action": action_name,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "result": "OK",
            }
            
            try:
                # Пытаемся извлечь информацию из аргументов
                self_arg = None
                
                # Ищем self (экземпляр класса) в аргументах
                if args and hasattr(args[0], func.__name__):
                    self_arg = args[0]
                    method_args = args[1:]
                else:
                    method_args = args
                
                # Обрабатываем позиционные аргументы
                for i, arg in enumerate(method_args):
                    if isinstance(arg, (int, str, float)):
                        log_info[f"arg_{i}"] = arg
                
                # Обрабатываем именованные аргументы
                for key, value in kwargs.items():
                    if isinstance(value, (int, str, float)):
                        log_info[key] = value
                    elif value is None:
                        log_info[key] = "None"
                
                # Если у нас есть self и это метод класса с определенными атрибутами
                if self_arg:
                    # Пытаемся получить user_id из self или аргументов
                    if hasattr(self_arg, 'user_id'):
                        log_info["user_id"] = self_arg.user_id
                    elif hasattr(self_arg, '_user_id'):
                        log_info["user_id"] = self_arg._user_id
                    
                    # Пытаемся получить username
                    if hasattr(self_arg, 'username'):
                        log_info["username"] = self_arg.username
                    elif hasattr(self_arg, '_username'):
                        log_info["username"] = self_arg._username
                
                # Выполняем оригинальную функцию
                result = func(*args, **kwargs)
                
                # Если функция возвращает результат с полезной информацией
                if result and isinstance(result, dict):
                    # Добавляем информацию из результата
                    for key in ['currency', 'currency_code', 'amount', 'rate', 'cost_usd', 'revenue_usd']: # noqa: E501
                        if key in result:
                            log_info[key] = result[key]
                    
                    # Добавляем информацию о базовой валюте
                    if 'cost_usd' in result:
                        log_info['base'] = 'USD'
                    elif 'revenue_usd' in result:
                        log_info['base'] = 'USD'
                
                # В режиме verbose добавляем дополнительную информацию
                if verbose and result:
                    log_info["details"] = str(result)
                
                # Форматируем и записываем лог
                _write_log(logger, log_info, settings)
                
                return result
                
            except Exception as e:
                # Логируем ошибку
                log_info["result"] = "ERROR"
                log_info["error_type"] = type(e).__name__
                log_info["error_message"] = str(e)
                
                # Форматируем и записываем лог ошибки
                _write_log(logger, log_info, settings, level=logging.ERROR)
                
                # Пробрасываем исключение дальше
                raise
        
        def _write_log(logger: logging.Logger, info: Dict[str, Any], 
                      settings, level: int = logging.INFO):
            """
            Запись лога в соответствующем формате
            
            Args:
                logger: Логгер для записи
                info: Информация для лога
                settings: Объект настроек
                level: Уровень логирования
            """
            log_format = settings.get("log_format", "detailed")
            
            if log_format == "json":
                # JSON формат
                log_data = {
                    "timestamp": info["timestamp"],
                    "level": logging.getLevelName(level),
                    "action": info["action"],
                    **{k: v for k, v in info.items() if k not in ["timestamp", "action"]} # noqa: E501
                }
                message = log_data
            else:
                # Текстовый формат
                parts = []
                
                # Добавляем пользователя
                if "username" in info:
                    parts.append(f"user='{info['username']}'")
                elif "user_id" in info:
                    parts.append(f"user_id={info['user_id']}")
                
                # Добавляем валюту
                if "currency" in info:
                    parts.append(f"currency='{info['currency']}'")
                elif "currency_code" in info:
                    parts.append(f"currency='{info['currency_code']}'")
                
                # Добавляем сумму
                if "amount" in info:
                    if isinstance(info["amount"], (int, float)):
                        parts.append(f"amount={info['amount']:.4f}")
                    else:
                        parts.append(f"amount={info['amount']}")
                
                # Добавляем курс
                if "rate" in info:
                    if isinstance(info["rate"], (int, float)):
                        parts.append(f"rate={info['rate']:.2f}")
                    else:
                        parts.append(f"rate={info['rate']}")
                
                # Добавляем базовую валюту
                if "base" in info:
                    parts.append(f"base='{info['base']}'")
                
                # Добавляем результат
                parts.append(f"result={info['result']}")
                
                # Добавляем информацию об ошибке
                if info["result"] == "ERROR":
                    parts.append(f"error_type='{info.get('error_type', 'UNKNOWN')}'")
                    parts.append(f"error='{info.get('error_message', 'Unknown error')}'") # noqa: E501
                
                message = " ".join(parts)
            
            # Записываем лог
            logger.log(level, message, extra={"action": info["action"]})
        
        return wrapper
    
    return decorator


def log_method_call(func: Callable) -> Callable:
    """
    Декоратор для логирования вызовов методов.
    Упрощенная версия без параметров.
    """
    return log_action(func.__name__.upper())(func)