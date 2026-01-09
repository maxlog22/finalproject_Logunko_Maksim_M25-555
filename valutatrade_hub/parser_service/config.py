"""
Конфигурация для Parser Service.
Хранит настройки API, списки валют и другие параметры.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple


@dataclass
class ParserConfig:
    """Конфигурация для сервиса парсинга курсов валют."""
    
    # API ключи (загружаются из переменных окружения)
    EXCHANGERATE_API_KEY: str = os.getenv("EXCHANGERATE_API_KEY", "c9e445b3a03e91c0ed51a1c6") # noqa: E501
    # Это реальный ключ API для ExchangeRate-API
    
    # URL эндпоинтов API
    COINGECKO_URL: str = "https://api.coingecko.com/api/v3/simple/price"
    EXCHANGERATE_API_URL: str = "https://v6.exchangerate-api.com/v6"
    
    # Базовая валюта для фиатных курсов
    BASE_FIAT_CURRENCY: str = "USD"
    
    # Списки отслеживаемых валют (только основные)
    FIAT_CURRENCIES: Tuple[str, ...] = field(default_factory=lambda: (
        "EUR", "GBP", "JPY", "CNY", "RUB", 
        "CHF", "CAD", "AUD", "NZD", "SGD",
        "HKD", "SEK", "NOK", "DKK", "PLN",
        "CZK", "HUF", "TRY", "MXN", "BRL"
    ))
    
    CRYPTO_CURRENCIES: Tuple[str, ...] = field(default_factory=lambda: (
        "BTC", "ETH", "SOL", "BNB", "XRP",
        "ADA", "DOGE", "DOT", "MATIC", "LTC",
        "SHIB", "TRX", "AVAX", "LINK", "UNI"
    ))
    
    # Соответствие кодов криптовалют их ID в CoinGecko (ID а не тикеры!)
    CRYPTO_ID_MAP: Dict[str, str] = field(default_factory=lambda: {
        "BTC": "bitcoin",
        "ETH": "ethereum", 
        "SOL": "solana",
        "BNB": "binancecoin",
        "XRP": "ripple",
        "ADA": "cardano",
        "DOGE": "dogecoin",
        "DOT": "polkadot",
        "MATIC": "matic-network",
        "LTC": "litecoin",
        "SHIB": "shiba-inu",
        "TRX": "tron",
        "AVAX": "avalanche-2",
        "LINK": "chainlink",
        "UNI": "uniswap"
    })
    
    # Параметры запросов
    REQUEST_TIMEOUT: int = 30  # секунд
    RETRY_ATTEMPTS: int = 3
    RETRY_DELAY: int = 5  # секунд между попытками
    
    # Интервал обновления (в секундах)
    UPDATE_INTERVAL: int = 3600  # 1 час
    
    # Пути к файлам данных
    BASE_DATA_DIR: str = "data"
    RATES_FILE: str = "rates.json"  # Для Core Service
    EXCHANGE_RATES_FILE: str = "exchange_rates.json"  # Журнал измерений
    PARSER_LOG_FILE: str = "parser.log"  # Лог парсера
    
    # Настройки логирования
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "detailed"  # 'detailed' или 'json'
    
    # Параметры валидации
    MIN_RATE_VALUE: float = 0.00000001
    MAX_RATE_VALUE: float = 1000000000
    
    def get_rates_file_path(self) -> str:
        """Получить полный путь к файлу rates.json."""
        return str(Path(self.BASE_DATA_DIR) / self.RATES_FILE)
    
    def get_exchange_rates_file_path(self) -> str:
        """Получить полный путь к файлу exchange_rates.json."""
        return str(Path(self.BASE_DATA_DIR) / self.EXCHANGE_RATES_FILE)
    
    def get_parser_log_path(self) -> str:
        """Получить полный путь к файлу логов парсера."""
        return str(Path(self.BASE_DATA_DIR) / self.PARSER_LOG_FILE)
    
    def get_coingecko_url(self, currencies: List[str] = None) -> str:
        """
        Сформировать URL для запроса к CoinGecko API.
        
        Args:
            currencies: Список кодов криптовалют для запроса
            
        Returns:
            Строка с URL
        """
        if currencies is None:
            currencies = list(self.CRYPTO_CURRENCIES)
        
        # Конвертируем коды в ID для CoinGecko (используем ID из CRYPTO_ID_MAP)
        ids = []
        for code in currencies:
            if code in self.CRYPTO_ID_MAP:
                ids.append(self.CRYPTO_ID_MAP[code])
        
        if not ids:
            return f"{self.COINGECKO_URL}?ids=bitcoin&vs_currencies=usd"
        
        ids_param = ",".join(ids)
        return f"{self.COINGECKO_URL}?ids={ids_param}&vs_currencies=usd"
    
    def get_exchangerate_url(self) -> str:
        """
        Сформировать URL для запроса к ExchangeRate-API.
        
        Returns:
            Строка с URL
        """
        return f"{self.EXCHANGERATE_API_URL}/{self.EXCHANGERATE_API_KEY}/latest/{self.BASE_FIAT_CURRENCY}" # noqa: E501
    
    def validate(self) -> bool:
        """
        Проверить валидность конфигурации.
        
        Returns:
            True если конфигурация валидна
        """
        # Проверка API ключа (минимальная длина)
        if not self.EXCHANGERATE_API_KEY or len(self.EXCHANGERATE_API_KEY) < 10:
            print("⚠️  Внимание: API ключ ExchangeRate-API может быть некорректным")
            print("   Используйте переменную окружения EXCHANGERATE_API_KEY для установки ключа") # noqa: E501
        
        # Проверка списков валют
        if not self.FIAT_CURRENCIES:
            print("⚠️  Внимание: список фиатных валют пуст")
            return False
        
        if not self.CRYPTO_CURRENCIES:
            print("⚠️  Внимание: список криптовалют пуст")
            return False
        
        # Проверка соответствия кодов криптовалют
        for code in self.CRYPTO_CURRENCIES:
            if code not in self.CRYPTO_ID_MAP:
                print(f"⚠️  Внимание: для криптовалюты {code} не указан ID для CoinGecko") # noqa: E501
                return False
        
        return True


# Создаем глобальный экземпляр конфигурации
config = ParserConfig()