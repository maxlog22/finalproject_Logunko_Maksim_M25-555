"""
Клиенты для работы с внешними API курсов валют.
"""

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional

import requests

try:
    from valutatrade_hub.core.exceptions import ApiRequestError
except ImportError:
    from ..core.exceptions import ApiRequestError

from .config import config


class BaseApiClient(ABC):
    """Абстрактный базовый класс для API клиентов."""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"parser.{name}")
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'ValutaTradeHub/1.0 (https://github.com/yourusername/valutatrade)' # noqa: E501
        })
    
    @abstractmethod
    def fetch_rates(self) -> Dict[str, Any]:
        """
        Получить курсы валют от API.
        
        Returns:
            Словарь с курсами в формате {currency_code: rate}
            
        Raises:
            ApiRequestError: При ошибке запроса к API
        """
        pass
    
    def _make_request(self, url: str, params: Dict = None) -> Dict[str, Any]:
        """
        Выполнить HTTP запрос с обработкой ошибок и повторными попытками.
        
        Args:
            url: URL для запроса
            params: Параметры запроса
            
        Returns:
            Ответ API в виде словаря
            
        Raises:
            ApiRequestError: При ошибке запроса
        """
        for attempt in range(config.RETRY_ATTEMPTS):
            try:
                self.logger.debug(f"Запрос к {self.name}: {url}")
                start_time = time.time()
                
                response = self.session.get(
                    url, 
                    params=params, 
                    timeout=config.REQUEST_TIMEOUT
                )
                
                request_time = time.time() - start_time
                
                # Проверка статуса ответа
                if response.status_code == 200:
                    self.logger.debug(f"Ответ от {self.name} получен за {request_time:.2f} сек") # noqa: E501
                    return response.json()
                elif response.status_code == 429:  # Too Many Requests
                    self.logger.warning(f"{self.name}: Превышен лимит запросов")
                    if attempt < config.RETRY_ATTEMPTS - 1:
                        wait_time = config.RETRY_DELAY * (attempt + 1)
                        self.logger.info(f"Повтор через {wait_time} сек...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise ApiRequestError(f"{self.name}: Превышен лимит запросов")
                else:
                    error_msg = f"{self.name}: Ошибка {response.status_code}"
                    if response.text:
                        error_msg += f" - {response.text[:200]}"
                    raise ApiRequestError(error_msg)
                    
            except requests.exceptions.Timeout:
                self.logger.warning(f"{self.name}: Таймаут запроса")
                if attempt < config.RETRY_ATTEMPTS - 1:
                    time.sleep(config.RETRY_DELAY)
                    continue
                raise ApiRequestError(f"{self.name}: Таймаут при подключении к API")
                
            except requests.exceptions.ConnectionError:
                self.logger.warning(f"{self.name}: Ошибка подключения")
                if attempt < config.RETRY_ATTEMPTS - 1:
                    time.sleep(config.RETRY_DELAY)
                    continue
                raise ApiRequestError(f"{self.name}: Не удалось подключиться к API")
                
            except requests.exceptions.RequestException as e:
                self.logger.error(f"{self.name}: Ошибка запроса: {e}")
                if attempt < config.RETRY_ATTEMPTS - 1:
                    time.sleep(config.RETRY_DELAY)
                    continue
                raise ApiRequestError(f"{self.name}: Ошибка при выполнении запроса: {e}") # noqa: E501
                
            except ValueError as e:
                self.logger.error(f"{self.name}: Ошибка парсинга JSON: {e}")
                raise ApiRequestError(f"{self.name}: Неверный формат ответа от API")
        
        raise ApiRequestError(f"{self.name}: Не удалось выполнить запрос после {config.RETRY_ATTEMPTS} попыток") # noqa: E501


class CoinGeckoClient(BaseApiClient):
    """Клиент для работы с CoinGecko API."""
    
    def __init__(self):
        super().__init__("CoinGecko")
    
    def fetch_rates(self) -> Dict[str, Any]:
        """
        Получить курсы криптовалют от CoinGecko.
        
        Returns:
            Словарь с курсами в формате {currency_code: rate}
        """
        self.logger.info("Получение курсов криптовалют от CoinGecko...")
        
        # Формируем URL для запроса с ID криптовалют (не тикерами!)
        url = config.get_coingecko_url()
        self.logger.info(f"CoinGecko URL: {url}")
        
        try:
            data = self._make_request(url)
            
            # Логируем полученные данные
            self.logger.debug(f"CoinGecko ответ: {data}")
            
            # Обрабатываем ответ
            rates = {}
            
            if not data:
                self.logger.error("CoinGecko вернул пустой ответ")
                return rates
            
            # Создаем обратный словарь для поиска кода по ID
            id_to_code = {v: k for k, v in config.CRYPTO_ID_MAP.items()}
            
            for crypto_id, price_data in data.items():
                # Находим код валюты по ID через обратный словарь
                currency_code = id_to_code.get(crypto_id)
                
                if currency_code and price_data and "usd" in price_data:
                    rate = price_data["usd"]
                    rates[f"{currency_code}_USD"] = rate
                    self.logger.debug(f"Добавлен курс: {currency_code}/USD = {rate}")
                else:
                    self.logger.warning(f"Не удалось обработать: {crypto_id} -> {price_data}") # noqa: E501
             
            self.logger.info(f"Получено {len(rates)} курсов от CoinGecko")
            return rates
            
        except ApiRequestError as e:
            self.logger.error(f"Ошибка при получении данных от CoinGecko: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка в CoinGeckoClient: {e}")
            raise ApiRequestError(f"CoinGecko: {str(e)}")
    
    def get_currency_info(self, currency_code: str) -> Optional[Dict[str, Any]]:
        """
        Получить дополнительную информацию о криптовалюте.
        
        Args:
            currency_code: Код криптовалюты
            
        Returns:
            Словарь с информацией или None
        """
        if currency_code not in config.CRYPTO_ID_MAP:
            return None
        
        crypto_id = config.CRYPTO_ID_MAP[currency_code]
        url = f"https://api.coingecko.com/api/v3/coins/{crypto_id}"
        
        try:
            data = self._make_request(url)
            return {
                "name": data.get("name"),
                "symbol": data.get("symbol", "").upper(),
                "market_cap": data.get("market_data", {}).get("market_cap", {}).get("usd"), # noqa: E501
                "volume": data.get("market_data", {}).get("total_volume", {}).get("usd"), # noqa: E501
                "price_change_24h": data.get("market_data", {}).get("price_change_percentage_24h"), # noqa: E501
            }
        except Exception as e:
            self.logger.warning(f"Не удалось получить информацию о {currency_code}: {e}") # noqa: E501
            return None


class ExchangeRateApiClient(BaseApiClient):
    """Клиент для работы с ExchangeRate-API."""
    
    def __init__(self):
        super().__init__("ExchangeRate-API")
    
    def fetch_rates(self) -> Dict[str, Any]:
        """
        Получить курсы фиатных валют от ExchangeRate-API.
        
        Returns:
            Словарь с курсами в формате {currency_code: rate}
        """
        self.logger.info("Получение курсов фиатных валют от ExchangeRate-API...")
        
        # Формируем URL для запроса с API ключом
        url = config.get_exchangerate_url()
        self.logger.info(f"ExchangeRate-API URL: {url}")
        
        try:
            data = self._make_request(url)
            
            # Проверяем успешность ответа
            if data.get("result") != "success":
                error_msg = data.get("error-type", "Unknown error")
                raise ApiRequestError(f"ExchangeRate-API: {error_msg}")
            
            # Получаем базовую валюту
            base_currency = data.get("base_code", "USD")
            
            # ВАЖНО: В ExchangeRate-API поле называется "conversion_rates", а не "rates"
            raw_rates = data.get("conversion_rates", {})
            
            self.logger.info(f"ExchangeRate-API вернул {len(raw_rates)} валют")
            
            # Добавляем только целевые валюты из конфига
            rates = {}
            found_currencies = []
            not_found_currencies = []
            
            for currency_code in config.FIAT_CURRENCIES:
                if currency_code in raw_rates:
                    rate = raw_rates[currency_code]
                    rates[f"{currency_code}_{base_currency}"] = rate
                    found_currencies.append(currency_code)
                    self.logger.debug(f"Добавлен курс: {currency_code}/{base_currency} = {rate}") # noqa: E501
                else:
                    not_found_currencies.append(currency_code)
            
            # Логируем, какие валюты нашли, а какие нет
            if found_currencies:
                self.logger.info(f"Найдено валют в ответе: {', '.join(found_currencies)}") # noqa: E501
            if not_found_currencies:
                self.logger.warning(f"Не найдено валют в ответе: {', '.join(not_found_currencies)}") # noqa: E501
            
            # Добавляем курс базовой валюты к самой себе
            rates[f"{base_currency}_{base_currency}"] = 1.0
            
            self.logger.info(f"Итоговые курсы от ExchangeRate-API: {len(rates)} записей") # noqa: E501
            return rates
            
        except ApiRequestError as e:
            self.logger.error(f"Ошибка при получении данных от ExchangeRate-API: {e}")
            raise
    
    def get_last_update_time(self) -> Optional[datetime]:
        """
        Получить время последнего обновления курсов.
        
        Returns:
            Время обновления или None
        """
        try:
            data = self._make_request(config.get_exchangerate_url())
            
            # Парсим время из ответа
            time_str = data.get("time_last_update_utc")
            if time_str:
                try:
                    # Формат: "Fri, 10 Oct 2025 12:00:00 +0000"
                    time_str_clean = " ".join(time_str.split()[1:5])
                    return datetime.strptime(time_str_clean, "%d %b %Y %H:%M:%S")
                except (ValueError, TypeError):
                    pass
            
            return None
            
        except Exception:
            return None