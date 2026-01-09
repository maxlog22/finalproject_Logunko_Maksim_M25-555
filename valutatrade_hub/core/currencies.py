"""
Модуль для работы с валютами
"""

import re
from abc import ABC, abstractmethod
from typing import Dict

from .exceptions import CurrencyNotFoundError, InvalidCurrencyCodeError


class Currency(ABC):
    """
    Абстрактный базовый класс для всех валют.
    Определяет общий интерфейс и базовую валидацию.
    """
    
    def __init__(self, name: str, code: str):
        """
        Инициализация валюты.
        
        Args:
            name: Читаемое имя валюты (например, "US Dollar", "Bitcoin")
            code: Код валюты (например, "USD", "BTC")
        
        Raises:
            InvalidCurrencyCodeError: Если код валюты невалидный
            ValueError: Если имя валюты пустое
        """
        self._validate_code(code)
        self._validate_name(name)
        
        self._name = name
        self._code = code.upper()
    
    def _validate_code(self, code: str) -> None:
        """
        Валидация кода валюты.
        
        Правила:
        - Длина от 2 до 5 символов
        - Только буквы и цифры
        - Без пробелов и специальных символов
        """
        if not isinstance(code, str):
            raise InvalidCurrencyCodeError(code, "Код валюты должен быть строкой")
        
        code = code.strip()
        
        if not 2 <= len(code) <= 5:
            raise InvalidCurrencyCodeError(
                code, 
                f"Код валюты должен быть от 2 до 5 символов. Получено: {len(code)}"
            )
        
        if not re.match(r'^[A-Za-z0-9]+$', code):
            raise InvalidCurrencyCodeError(
                code,
                "Код валюты должен содержать только буквы и цифры без пробелов"
            )
    
    def _validate_name(self, name: str) -> None:
        """
        Валидация имени валюты.
        
        Правила:
        - Не пустая строка
        - Минимальная длина 2 символа
        """
        if not isinstance(name, str):
            raise ValueError("Имя валюты должно быть строкой")
        
        name = name.strip()
        
        if not name:
            raise ValueError("Имя валюты не может быть пустым")
        
        if len(name) < 2:
            raise ValueError("Имя валюты должно быть не короче 2 символов")
    
    @property
    def name(self) -> str:
        """Получить имя валюты"""
        return self._name
    
    @property
    def code(self) -> str:
        """Получить код валюты"""
        return self._code
    
    @abstractmethod
    def get_display_info(self) -> str:
        """
        Абстрактный метод для получения строкового представления валюты.
        
        Returns:
            Строка с информацией о валюте для отображения в UI/логах
        """
        pass
    
    def __str__(self) -> str:
        """Строковое представление валюты"""
        return f"{self._code} - {self._name}"
    
    def __repr__(self) -> str:
        """Репрезентативное представление для отладки"""
        return f"<{self.__class__.__name__}: {self._code} - {self._name}>"
    
    def __eq__(self, other) -> bool:
        """Сравнение валют по коду"""
        if isinstance(other, Currency):
            return self._code == other.code
        elif isinstance(other, str):
            return self._code == other.upper()
        return False
    
    def __hash__(self) -> int:
        """Хеш валюты для использования в словарях и множествах"""
        return hash(self._code)


class FiatCurrency(Currency):
    """
    Класс для фиатных валют (традиционных государственных валют).
    """
    
    def __init__(self, name: str, code: str, issuing_country: str):
        """
        Инициализация фиатной валюты.
        
        Args:
            name: Человекочитаемое имя валюты (например, "US Dollar")
            code: Код валюты (например, "USD")
            issuing_country: Страна/зона эмиссии (например, "United States")
        """
        super().__init__(name, code)
        self._issuing_country = issuing_country
    
    @property
    def issuing_country(self) -> str:
        """Получить страну/зону эмиссии"""
        return self._issuing_country
    
    def get_display_info(self) -> str:
        """
        Получить строковое представление фиатной валюты.
        
        Формат: "[FIAT] USD — US Dollar (Issuing: United States)"
        
        Returns:
            Строка с информацией о фиатной валюте
        """
        return f"[FIAT] {self._code} — {self._name} (Issuing: {self._issuing_country})"
    
    def __repr__(self) -> str:
        """Репрезентативное представление для отладки"""
        return f"<FiatCurrency: {self._code} - {self._name}, Country: {self._issuing_country}>" # noqa: E501


class CryptoCurrency(Currency):
    """
    Класс для криптовалют.
    """
    
    def __init__(self, name: str, code: str, algorithm: str, market_cap: float = 0.0):
        """
        Инициализация криптовалюты.
        
        Args:
            name: Читаемое имя криптовалюты (например, "Bitcoin")
            code: Код криптовалюты (например, "BTC")
            algorithm: Алгоритм консенсуса/шифрования (например, "SHA-256")
            market_cap: Рыночная капитализация (по умолчанию 0.0)
        """
        super().__init__(name, code)
        self._algorithm = algorithm
        self._market_cap = float(market_cap)
    
    @property
    def algorithm(self) -> str:
        """Получить алгоритм криптовалюты"""
        return self._algorithm
    
    @property
    def market_cap(self) -> float:
        """Получить рыночную капитализацию"""
        return self._market_cap
    
    @market_cap.setter
    def market_cap(self, value: float):
        """Установить рыночную капитализацию"""
        if value < 0:
            raise ValueError("Рыночная капитализация не может быть отрицательной")
        self._market_cap = float(value)
    
    def get_display_info(self) -> str:
        """
        Получить строковое представление криптовалюты.
        
        Формат: "[CRYPTO] BTC — Bitcoin (Algo: SHA-256, MCAP: 1.12e12)"
        
        Returns:
            Строка с информацией о криптовалюте
        """
        # Форматируем рыночную капитализацию в научной нотации
        mcap_str = f"{self._market_cap:.2e}" if self._market_cap >= 1000000 else f"{self._market_cap:,.2f}" # noqa: E501
        return f"[CRYPTO] {self._code} — {self._name} (Algo: {self._algorithm}, MCAP: {mcap_str})" # noqa: E501
    
    def __repr__(self) -> str:
        """Репрезентативное представление для отладки"""
        return f"<CryptoCurrency: {self._code} - {self._name}, Algo: {self._algorithm}>"


class CurrencyRegistry:
    """
    Реестр валют для получения экземпляров по коду.
    Реализует паттерн Singleton для глобального доступа.
    """
    
    _instance = None
    _currencies: Dict[str, Currency] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize_currencies()
        return cls._instance
    
    def _initialize_currencies(self) -> None:
        """
        Инициализация предопределённых валют.
        В реальном приложении это можно загружать из конфигурационного файла или БД.
        """
        # Фиатные валюты
        self._register_fiat("USD", "US Dollar", "United States")
        self._register_fiat("EUR", "Euro", "Eurozone")
        self._register_fiat("RUB", "Russian Ruble", "Russia")
        self._register_fiat("GBP", "British Pound", "United Kingdom")
        self._register_fiat("JPY", "Japanese Yen", "Japan")
        self._register_fiat("CNY", "Chinese Yuan", "China")
        
        # Криптовалюты
        self._register_crypto("BTC", "Bitcoin", "SHA-256", 1.12e12)
        self._register_crypto("ETH", "Ethereum", "Ethash", 4.5e11)
        self._register_crypto("LTC", "Litecoin", "Scrypt", 1.2e10)
        self._register_crypto("XRP", "Ripple", "Ripple Protocol", 3.0e10)
        self._register_crypto("DOGE", "Dogecoin", "Scrypt", 2.0e10)
    
    def _register_fiat(self, code: str, name: str, issuing_country: str) -> None:
        """Регистрация фиатной валюты"""
        currency = FiatCurrency(name, code, issuing_country)
        self._currencies[code.upper()] = currency
    
    def _register_crypto(self, code: str, name: str, algorithm: str, market_cap: float) -> None: # noqa: E501
        """Регистрация криптовалюты"""
        currency = CryptoCurrency(name, code, algorithm, market_cap)
        self._currencies[code.upper()] = currency
    
    def register_currency(self, currency: Currency) -> None:
        """
        Регистрация валюты в реестре.
        
        Args:
            currency: Экземпляр валюты для регистрации
        
        Raises:
            ValueError: Если валюта с таким кодом уже зарегистрирована
        """
        code = currency.code.upper()
        if code in self._currencies:
            raise ValueError(f"Валюта с кодом '{code}' уже зарегистрирована")
        self._currencies[code] = currency
    
    def get_currency(self, code: str) -> Currency:
        """
        Получить валюту по коду.
        
        Args:
            code: Код валюты (например, "USD", "BTC")
        
        Returns:
            Экземпляр валюты
        
        Raises:
            CurrencyNotFoundError: Если валюта с указанным кодом не найдена
        """
        code = code.upper()
        if code not in self._currencies:
            raise CurrencyNotFoundError(code)
        return self._currencies[code]
    
    def get_all_currencies(self) -> Dict[str, Currency]:
        """
        Получить все зарегистрированные валюты.
        
        Returns:
            Словарь с кодами валют в качестве ключей и экземплярами валют в качестве значений""" # noqa: E501
        
        return self._currencies.copy()
    
    def get_fiat_currencies(self) -> Dict[str, FiatCurrency]:
        """
        Получить все фиатные валюты.
        
        Returns:
            Словарь с кодами фиатных валют
        """
        return {
            code: currency 
            for code, currency in self._currencies.items() 
            if isinstance(currency, FiatCurrency)
        }
    
    def get_crypto_currencies(self) -> Dict[str, CryptoCurrency]:
        """
        Получить все криптовалюты.
        
        Returns:
            Словарь с кодами криптовалют
        """
        return {
            code: currency 
            for code, currency in self._currencies.items() 
            if isinstance(currency, CryptoCurrency)
        }
    
    def is_registered(self, code: str) -> bool:
        """
        Проверить, зарегистрирована ли валюта.
        
        Args:
            code: Код валюты
        
        Returns:
            True, если валюта зарегистрирована, иначе False
        """
        return code.upper() in self._currencies
    
    def is_fiat(self, code: str) -> bool:
        """
        Проверить, является ли валюта фиатной.
        
        Args:
            code: Код валюты
        
        Returns:
            True, если валюта фиатная, иначе False
        
        Raises:
            CurrencyNotFoundError: Если валюта с указанным кодом не найдена
        """
        currency = self.get_currency(code)
        return isinstance(currency, FiatCurrency)
    
    def is_crypto(self, code: str) -> bool:
        """
        Проверить, является ли валюта криптовалютой.
        
        Args:
            code: Код валюты
        
        Returns:
            True, если валюта криптовалюта, иначе False
        
        Raises:
            CurrencyNotFoundError: Если валюта с указанным кодом не найдена
        """
        currency = self.get_currency(code)
        return isinstance(currency, CryptoCurrency)


# Фабричная функция для удобного доступа к реестру
def get_currency_registry() -> CurrencyRegistry:
    """
    Получить экземпляр реестра валют (Singleton).
    
    Returns:
        Экземпляр CurrencyRegistry
    """
    return CurrencyRegistry()


# Фабричная функция для получения валюты по коду
def get_currency(code: str) -> Currency:
    """
    Получить валюту по коду.
    
    Args:
        code: Код валюты (например, "USD", "BTC")
    
    Returns:
        Экземпляр валюты
    
    Raises:
        CurrencyNotFoundError: Если валюта с указанным кодом не найдена
    """
    return get_currency_registry().get_currency(code)


# Функция для проверки существования валюты
def currency_exists(code: str) -> bool:
    """
    Проверить, существует ли валюта с указанным кодом.
    
    Args:
        code: Код валюты
    
    Returns:
        True, если валюта существует, иначе False
    """
    return get_currency_registry().is_registered(code)