"""
Основной модуль обновления курсов валют.
Координирует получение данных от всех клиентов и их сохранение.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

try:
    from valutatrade_hub.core.exceptions import ApiRequestError
except ImportError:
    from ..core.exceptions import ApiRequestError

from .api_clients import CoinGeckoClient, ExchangeRateApiClient
from .config import config
from .storage import RatesStorage


class RatesUpdater:
    """Класс для координации обновления курсов валют."""
    
    def __init__(self):
        self.config = config
        self.logger = logging.getLogger("parser.updater")
        
        # Инициализируем клиенты
        self.coingecko_client = CoinGeckoClient()
        self.exchangerate_client = ExchangeRateApiClient()
        
        # Инициализируем хранилище
        self.storage = RatesStorage(config)
        
        # Статистика
        self.stats = {
            "total_updates": 0,
            "successful_updates": 0,
            "failed_updates": 0,
            "last_update_time": None,
            "last_error": None
        }
    
    def run_update(self, source: str = "all") -> Dict[str, Any]:
        """
        Запустить обновление курсов валют.
        
        Args:
            source: Источник для обновления ('all', 'coingecko', 'exchangerate')
            
        Returns:
            Словарь со статистикой обновления
        """
        self.logger.info(f"Запуск обновления курсов (источник: {source})")
        start_time = time.time()
        
        try:
            # Загружаем текущие курсы
            current_rates = self.storage.load_rates()
            pairs = current_rates.get("pairs", {})
            
            # Получаем новые курсы
            new_rates = {}
            
            # Обновляем от CoinGecko (криптовалюты)
            if source in ["all", "coingecko"]:
                try:
                    crypto_rates = self.coingecko_client.fetch_rates()
                    if crypto_rates:
                        new_rates.update(crypto_rates)
                        self.logger.info(f"Получено {len(crypto_rates)} курсов от CoinGecko") # noqa: E501
                    else:
                        self.logger.warning("CoinGecko вернул пустой ответ")
                except ApiRequestError as e:
                    self.logger.error(f"Ошибка при получении данных от CoinGecko: {e}")
                    if source == "coingecko":
                        raise
            
            # Обновляем от ExchangeRate-API (фиатные валюты)
            if source in ["all", "exchangerate"]:
                try:
                    fiat_rates = self.exchangerate_client.fetch_rates()
                    if fiat_rates:
                        new_rates.update(fiat_rates)
                        self.logger.info(f"Получено {len(fiat_rates)} курсов от ExchangeRate-API") # noqa: E501
                    else:
                        self.logger.warning("ExchangeRate-API вернул пустой ответ")
                except ApiRequestError as e:
                    self.logger.error(f"Ошибка при получении данных от ExchangeRate-API: {e}") # noqa: E501
                    if source == "exchangerate":
                        raise
            
            # Проверяем, есть ли новые данные
            if not new_rates:
                self.logger.warning("Не получено ни одного курса")
                return {
                    "success": False,
                    "message": "Не удалось получить курсы ни от одного источника",
                    "updated_pairs": 0
                }
            
            # Обновляем пары курсов
            updated_count = 0
            new_count = 0
            current_time = datetime.now(timezone.utc).isoformat()
            
            for pair_key, rate in new_rates.items():
                # Проверяем валидность курса
                if not self.storage.validate_rate(rate, pair_key):
                    self.logger.warning(f"Пропускаем невалидный курс: {pair_key} = {rate}") # noqa: E501
                    continue
                
                # Определяем источник
                from_curr, to_curr = pair_key.split("_", 1)
                if from_curr in self.config.CRYPTO_CURRENCIES:
                    source_name = "CoinGecko"
                else:
                    source_name = "ExchangeRate-API"
                
                # Проверяем, есть ли уже такая пара
                current_pair = pairs.get(pair_key, {})
                current_rate = current_pair.get("rate")
                
                # Всегда обновляем курс
                pairs[pair_key] = {
                    "rate": rate,
                    "updated_at": current_time,
                    "source": source_name
                }
                
                # Создаем историческую запись
                try:
                    record = self.storage.create_history_record(
                        from_currency=from_curr,
                        to_currency=to_curr,
                        rate=rate,
                        source=source_name,
                        meta={
                            "previous_rate": current_rate,
                            "change_pct": abs((rate - current_rate) / current_rate * 100) if current_rate else None # noqa: E501
                        }
                    )
                    self.storage.add_history_record(record)
                except Exception as e:
                    self.logger.warning(f"Не удалось создать историческую запись для {pair_key}: {e}") # noqa: E501
                
                if pair_key in current_pair:
                    updated_count += 1
                else:
                    new_count += 1
            
            # Сохраняем обновленные курсы
            current_rates["pairs"] = pairs
            current_rates["last_refresh"] = current_time
            self.storage.save_rates(current_rates)
            
            # Очищаем старую историю
            self.storage.cleanup_old_history(max_records=1000)
            
            # Обновляем статистику
            execution_time = time.time() - start_time
            self.stats["total_updates"] += 1
            self.stats["successful_updates"] += 1
            self.stats["last_update_time"] = current_time
            
            result = {
                "success": True,
                "message": "Обновление успешно завершено",
                "execution_time": round(execution_time, 2),
                "total_pairs": len(pairs),
                "updated_pairs": updated_count,
                "new_pairs": new_count,
                "source": source
            }
            
            self.logger.info(
                f"Обновление завершено за {execution_time:.2f} сек. "
                f"Обновлено: {updated_count}, Добавлено: {new_count}, Всего: {len(pairs)}" # noqa: E501
            )
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Ошибка при обновлении курсов: {e}")
            
            self.stats["total_updates"] += 1
            self.stats["failed_updates"] += 1
            self.stats["last_error"] = str(e)
            
            return {
                "success": False,
                "message": f"Ошибка при обновлении: {str(e)}",
                "execution_time": round(execution_time, 2),
                "source": source
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Получить статистику обновлений.
        
        Returns:
            Словарь со статистикой
        """
        current_rates = self.storage.load_rates()
        pairs = current_rates.get("pairs", {})
        
        sources = {}
        for pair_key, pair_data in pairs.items():
            source = pair_data.get("source", "Unknown")
            if source not in sources:
                sources[source] = 0
            sources[source] += 1
        
        stats = self.stats.copy()
        stats.update({
            "total_pairs": len(pairs),
            "sources": sources,
            "last_refresh": current_rates.get("last_refresh")
        })
        
        return stats
    
    def validate_rates(self) -> List[Dict[str, Any]]:
        """
        Проверить валидность всех сохраненных курсов.
        
        Returns:
            Список проблемных курсов
        """
        current_rates = self.storage.load_rates()
        pairs = current_rates.get("pairs", {})
        
        issues = []
        
        for pair_key, pair_data in pairs.items():
            # ИГНОРИРУЕМ КУРСЫ С SOURCE "test" - они ручные/тестовые
            if pair_data.get("source") == "test":
                continue  # Пропускаем тестовые курсы
            
            rate = pair_data.get("rate")
            updated_at = pair_data.get("updated_at")
            source = pair_data.get("source", "unknown")
            
            # Проверка валидности курса
            if not self.storage.validate_rate(rate, pair_key):
                issues.append({
                    "pair": pair_key,
                    "issue": "Невалидное значение курса",
                    "rate": rate,
                    "updated_at": updated_at,
                    "source": source
                })
                continue
            
            # Проверка свежести данных
            if updated_at:
                try:
                    # Нормализуем формат времени
                    if updated_at.endswith("Z"):
                        update_time = datetime.fromisoformat(updated_at.replace("Z", "+00:00")) # noqa: E501
                    else:
                        update_time = datetime.fromisoformat(updated_at)
                    
                    # Убедимся, что update_time в UTC
                    if update_time.tzinfo is None:
                        update_time = update_time.replace(tzinfo=timezone.utc)
                    
                    now = datetime.now(timezone.utc)
                    age = (now - update_time).total_seconds()
                    
                    if age > config.UPDATE_INTERVAL * 2:  # Вдвое больше интервала обновления # noqa: E501
                        issues.append({
                            "pair": pair_key,
                            "issue": "Устаревшие данные",
                            "age_hours": round(age / 3600, 1),
                            "updated_at": updated_at,
                            "source": source
                        })
                except Exception as e:
                    issues.append({
                        "pair": pair_key,
                        "issue": f"Некорректная дата обновления: {str(e)}",
                        "updated_at": updated_at,
                        "source": source
                    })
        
        return issues