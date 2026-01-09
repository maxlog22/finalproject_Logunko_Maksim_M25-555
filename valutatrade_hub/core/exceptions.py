"""
Пользовательские исключения для ValutaTrade Hub
"""


class ValutaTradeError(Exception):
    """Базовое исключение для всех ошибок ValutaTrade Hub"""
    pass


class CurrencyNotFoundError(ValutaTradeError):
    """Исключение для случая, когда валюта не найдена"""
    def __init__(self, currency_code: str, message: str = None):
        self.currency_code = currency_code
        self.message = message or f"Неизвестная валюта '{currency_code}'"
        super().__init__(self.message)


class UserNotFoundError(ValutaTradeError):
    """Исключение для случая, когда пользователь не найден"""
    def __init__(self, username: str = None, user_id: int = None, message: str = None):
        self.username = username
        self.user_id = user_id
        if message:
            self.message = message
        elif username:
            self.message = f"Пользователь '{username}' не найден"
        elif user_id:
            self.message = f"Пользователь с ID {user_id} не найден"
        else:
            self.message = "Пользователь не найден"
        super().__init__(self.message)


class InsufficientFundsError(ValutaTradeError):
    """Исключение для случая недостаточных средств"""
    def __init__(self, currency_code: str, available: float, required: float, message: str = None): # noqa: E501
        self.currency_code = currency_code
        self.available = available
        self.required = required
        self.message = message or (
            f"Недостаточно средств: доступно {available:.4f} {currency_code}, "
            f"требуется {required:.4f} {currency_code}"
        )
        super().__init__(self.message)


class InvalidCurrencyCodeError(ValutaTradeError):
    """Исключение для невалидного кода валюты"""
    def __init__(self, currency_code: str, message: str = None):
        self.currency_code = currency_code
        self.message = message or f"Некорректный код валюты: '{currency_code}'"
        super().__init__(self.message)


class RateUnavailableError(ValutaTradeError):
    """Исключение для случая недоступного курса"""
    def __init__(self, from_currency: str, to_currency: str, message: str = None):
        self.from_currency = from_currency
        self.to_currency = to_currency
        self.message = message or f"Курс {from_currency}→{to_currency} недоступен"
        super().__init__(self.message)


class AuthenticationError(ValutaTradeError):
    """Исключение для ошибок аутентификации"""
    def __init__(self, message: str = "Ошибка аутентификации"):
        self.message = message
        super().__init__(self.message)


class WalletNotFoundError(ValutaTradeError):
    """Исключение для случая, когда кошелёк не найден"""
    def __init__(self, currency_code: str, message: str = None):
        self.currency_code = currency_code
        self.message = message or f"Кошелёк для валюты '{currency_code}' не найден"
        super().__init__(self.message)


class ApiRequestError(ValutaTradeError):
    """Исключение для сбоя внешнего API"""
    def __init__(self, reason: str, message: str = None):
        self.reason = reason
        self.message = message or f"Ошибка при обращении к внешнему API: {reason}"
        super().__init__(self.message)