"""
Use Cases (сервисы) для ValutaTrade Hub.
Содержит бизнес-логику приложения.
"""

from datetime import datetime
from typing import Dict, Optional

from ..decorators import log_action
from ..infra.settings import get_settings
from .currencies import currency_exists
from .exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
    InvalidCurrencyCodeError,
    RateUnavailableError,
    WalletNotFoundError,
)
from .models import Portfolio, User, Wallet
from .utils import (
    get_current_datetime,
    get_next_user_id,
    hash_password,
    load_exchange_rates,
    read_json,
    validate_currency_code,
    write_json,
)


class AuthService:
    _current_user: Optional[User] = None
    
    @classmethod
    def get_current_user(cls) -> Optional[User]:
        return cls._current_user
    
    @classmethod
    def set_current_user(cls, user: Optional[User]):
        cls._current_user = user
    
    @classmethod
    @log_action(action="REGISTER", verbose=True)
    def register(cls, username: str, password: str) -> User:
        """Регистрация нового пользователя"""
        users = read_json("users.json")
        
        # Проверка уникальности username
        if any(user.get("username") == username for user in users):
            raise ValueError(f"Имя пользователя '{username}' уже занято")
        
        # Проверка длины пароля
        if len(password) < 4:
            raise ValueError("Пароль должен быть не короче 4 символов")
        
        # Создание пользователя
        user_id = get_next_user_id()
        hashed_password, salt = hash_password(password)
        
        user_data = {
            "user_id": user_id,
            "username": username,
            "hashed_password": hashed_password,
            "salt": salt,
            "registration_date": get_current_datetime()
        }
        
        users.append(user_data)
        write_json("users.json", users)
        
        # Создание портфеля с начальным балансом USD
        settings = get_settings()
        initial_balance = settings.get("initial_usd_balance", 1000.0)
        
        portfolios = read_json("portfolios.json")
        portfolio_data = {
            "user_id": user_id,
            "wallets": {
                "USD": {"currency_code": "USD", "balance": initial_balance}
            }
        }
        portfolios.append(portfolio_data)
        write_json("portfolios.json", portfolios)
        
        # Создаем и возвращаем объект User без автоматического входа
        user = User(
            user_id=user_id,
            username=username,
            hashed_password=hashed_password,
            salt=salt,
            registration_date=datetime.fromisoformat(user_data["registration_date"]) 
        )
        
        return user
    
    @classmethod
    @log_action(action="LOGIN", verbose=False)
    def login(cls, username: str, password: str) -> User:
        """Вход пользователя"""
        users = read_json("users.json")
        
        # Ищем пользователя по имени
        user_found = None
        for user_data in users:
            if user_data.get("username") == username:
                user_found = user_data
                break
        
        if not user_found:
            raise ValueError(f"Пользователь '{username}' не найден")
        
        # Проверка пароля
        stored_hash = user_found.get("hashed_password")
        salt = user_found.get("salt")
        test_hash, _ = hash_password(password, salt)
        
        if test_hash == stored_hash:
            # Создание объекта User
            user = User(
                user_id=user_found["user_id"],
                username=user_found["username"],
                hashed_password=stored_hash,
                salt=salt,
                registration_date=datetime.fromisoformat(user_found["registration_date"]) # noqa: E501
            )
            cls._current_user = user
            return user
        else:
            raise ValueError("Неверный пароль")
    
    @classmethod
    @log_action(action="LOGOUT", verbose=False)
    def logout(cls):
        """Выход пользователя"""
        cls._current_user = None


class PortfolioService:
    @staticmethod
    def get_portfolio(user_id: int) -> Portfolio:
        """Получение портфеля пользователя"""
        portfolios = read_json("portfolios.json")
        
        for portfolio_data in portfolios:
            if portfolio_data.get("user_id") == user_id:
                wallets = {}
                for currency_code, wallet_data in portfolio_data.get("wallets", {}).items(): # noqa: E501
                    wallets[currency_code] = Wallet(
                        currency_code=currency_code,
                        balance=wallet_data.get("balance", 0.0)
                    )
                return Portfolio(user_id, wallets)
        
        # Если портфеля нет, создаем пустой
        portfolio = Portfolio(user_id)
        PortfolioService.save_portfolio(portfolio)
        return portfolio
    
    @staticmethod
    def save_portfolio(portfolio: Portfolio):
        """Сохранение портфеля"""
        portfolios = read_json("portfolios.json")
        
        # Удаляем старый портфель, если есть
        portfolios = [p for p in portfolios if p.get("user_id") != portfolio.user_id]
        
        # Добавляем новый
        portfolios.append(portfolio.to_dict())
        write_json("portfolios.json", portfolios)
    
    @staticmethod
    @log_action(action="BUY", verbose=True)
    def buy_currency(user_id: int, currency_code: str, amount: float) -> Dict:
        """Покупка валюты"""
        # Валидация входа
        if amount <= 0:
            raise ValueError("Сумма покупки должна быть положительной")
        
        # Валидация кода валюты
        if not validate_currency_code(currency_code):
            raise InvalidCurrencyCodeError(currency_code)
        
        # Проверка существования валюты в реестре
        if not currency_exists(currency_code):
            raise CurrencyNotFoundError(currency_code)
        
        portfolio = PortfolioService.get_portfolio(user_id)
        
        # Получаем курс через RateService
        try:
            rate_info = RateService.get_rate(currency_code, "USD")
            rate = rate_info["rate"]
        except (RateUnavailableError, ApiRequestError) as e:
            raise RateUnavailableError(currency_code, "USD") from e
        
        cost_usd = amount * rate
        
        # Проверяем наличие USD кошелька
        try:
            usd_wallet = portfolio.get_wallet("USD")
        except ValueError:
            raise WalletNotFoundError("USD")
        
        # Проверяем достаточно ли USD
        if usd_wallet.balance < cost_usd:
            raise InsufficientFundsError(
                currency_code="USD",
                available=usd_wallet.balance,
                required=cost_usd
            )
        
        # Снимаем USD
        usd_wallet.withdraw(cost_usd)
        
        # Добавляем или пополняем кошелек целевой валюты
        if currency_code not in portfolio.wallets:
            portfolio.add_currency(currency_code)
        
        target_wallet = portfolio.get_wallet(currency_code)
        target_wallet.deposit(amount)
        
        # Сохраняем изменения
        PortfolioService.save_portfolio(portfolio)
        
        return {
            "currency": currency_code,
            "amount": amount,
            "rate": rate,
            "cost_usd": cost_usd,
            "user_id": user_id,
            "old_balance": target_wallet.balance - amount,
            "new_balance": target_wallet.balance
        }
    
    @staticmethod
    @log_action(action="SELL", verbose=True)
    def sell_currency(user_id: int, currency_code: str, amount: float) -> Dict:
        """Продажа валюты"""
        # Валидация входа
        if amount <= 0:
            raise ValueError("Сумма продажи должна быть положительной")
        
        # Валидация кода валюты
        if not validate_currency_code(currency_code):
            raise InvalidCurrencyCodeError(currency_code)
        
        # Проверка существования валюты в реестре
        if not currency_exists(currency_code):
            raise CurrencyNotFoundError(currency_code)
        
        portfolio = PortfolioService.get_portfolio(user_id)
        
        # Проверяем наличие кошелька
        if currency_code not in portfolio.wallets:
            raise WalletNotFoundError(currency_code)
        
        target_wallet = portfolio.get_wallet(currency_code)
        
        # Получаем курс через RateService
        try:
            rate_info = RateService.get_rate(currency_code, "USD")
            rate = rate_info["rate"]
        except (RateUnavailableError, ApiRequestError) as e:
            raise RateUnavailableError(currency_code, "USD") from e
        
        revenue_usd = amount * rate
        
        # Запоминаем старый баланс
        old_balance = target_wallet.balance
        
        # Снимаем целевую валюту (может выбросить InsufficientFundsError)
        target_wallet.withdraw(amount)
        
        # Начисляем USD
        usd_wallet = portfolio.get_wallet("USD")
        usd_wallet.deposit(revenue_usd)
        
        # Сохраняем изменения
        PortfolioService.save_portfolio(portfolio)
        
        return {
            "currency": currency_code,
            "amount": amount,
            "rate": rate,
            "revenue_usd": revenue_usd,
            "user_id": user_id,
            "old_balance": old_balance,
            "new_balance": target_wallet.balance
        }


class RateService:
    @staticmethod
    @log_action(action="GET_RATE", verbose=False)
    def get_rate(from_currency: str, to_currency: str) -> Dict:
        """Получение курса валюты (без автоматического обновления)"""
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()
        
        # Валидация кодов валют
        if not validate_currency_code(from_currency):
            raise InvalidCurrencyCodeError(from_currency)
        
        if not validate_currency_code(to_currency):
            raise InvalidCurrencyCodeError(to_currency)
        
        # Проверка существования валют в реестре
        if not currency_exists(from_currency):
            raise CurrencyNotFoundError(from_currency)
        
        if not currency_exists(to_currency):
            raise CurrencyNotFoundError(to_currency)
        
        if from_currency == to_currency:
            return {
                "rate": 1.0,
                "updated_at": get_current_datetime()
            }
        
        # Загружаем курсы (без автоматического обновления)
        rates_data = load_exchange_rates()
        
        # Проверяем, что rates_data - это словарь
        if not isinstance(rates_data, dict):
            rates_data = {"pairs": {}, "last_refresh": None}
            raise RateUnavailableError(from_currency, to_currency)
        
        # Получаем пары курсов
        pairs = rates_data.get("pairs", {})
        
        # Прямой курс
        direct_key = f"{from_currency}_{to_currency}"
        
        # Если курс есть в кеше
        if direct_key in pairs:
            rate_info = pairs[direct_key]
            
            if not isinstance(rate_info, dict):
                raise RateUnavailableError(from_currency, to_currency)
            
            return rate_info
        
        # Попробуем получить обратный курс
        reverse_key = f"{to_currency}_{from_currency}"
        if reverse_key in pairs:
            rate_info = pairs[reverse_key]
            
            if isinstance(rate_info, dict):
                # Вычисляем обратный курс
                return {
                    "rate": 1 / rate_info["rate"],
                    "updated_at": rate_info["updated_at"]
                }
        
        # Попробуем через USD
        if from_currency != "USD" and to_currency != "USD":
            # Попробуем получить оба курса к USD
            from_usd_key = f"{from_currency}_USD"
            usd_to_key = f"USD_{to_currency}"
            
            if from_usd_key in pairs and usd_to_key in pairs:
                from_usd_info = pairs[from_usd_key]
                usd_to_info = pairs[usd_to_key]
                
                if isinstance(from_usd_info, dict) and isinstance(usd_to_info, dict):
                    rate = from_usd_info["rate"] * usd_to_info["rate"]
                    updated_at = max(from_usd_info["updated_at"], usd_to_info["updated_at"]) # noqa: E501
                    return {
                        "rate": rate,
                        "updated_at": updated_at
                    }
        
        # Если курс не найден
        raise RateUnavailableError(from_currency, to_currency)