import hashlib
from datetime import datetime
from typing import Dict, Optional

from .exceptions import InsufficientFundsError


class User:
    def __init__(self, user_id: int, username: str, hashed_password: str, 
                 salt: str, registration_date: datetime):
        self._user_id = user_id
        self._username = username
        self._hashed_password = hashed_password
        self._salt = salt
        self._registration_date = registration_date
    
    @property
    def user_id(self) -> int:
        return self._user_id
    
    @property
    def username(self) -> str:
        return self._username
    
    @username.setter
    def username(self, value: str):
        if not value or not isinstance(value, str):
            raise ValueError("Имя пользователя не может быть пустым")
        self._username = value
    
    @property
    def hashed_password(self) -> str:
        return self._hashed_password
    
    @property
    def salt(self) -> str:
        return self._salt
    
    @property
    def registration_date(self) -> datetime:
        return self._registration_date
    
    def get_user_info(self) -> Dict:
        return {
            "user_id": self._user_id,
            "username": self._username,
            "registration_date": self._registration_date.isoformat()
        }
    
    def change_password(self, new_password: str):
        if len(new_password) < 4:
            raise ValueError("Пароль должен быть не короче 4 символов")
        # Генерируем новую соль и хеш
        new_salt = hashlib.sha256(str(datetime.now().timestamp()).encode()).hexdigest()[:8] # noqa: E501
        new_hashed = hashlib.sha256((new_password + new_salt).encode()).hexdigest()
        self._hashed_password = new_hashed
        self._salt = new_salt
    
    def verify_password(self, password: str) -> bool:
        test_hash = hashlib.sha256((password + self._salt).encode()).hexdigest()
        return test_hash == self._hashed_password


class Wallet:
    def __init__(self, currency_code: str, balance: float = 0.0):
        self.currency_code = currency_code
        self._balance = balance
    
    @property
    def balance(self) -> float:
        return self._balance
    
    @balance.setter
    def balance(self, value: float):
        if not isinstance(value, (int, float)):
            raise TypeError("Баланс должен быть числом")
        if value < 0:
            raise ValueError("Баланс не может быть отрицательным")
        self._balance = float(value)
    
    def deposit(self, amount: float):
        if amount <= 0:
            raise ValueError("Сумма пополнения должна быть положительной")
        self.balance += amount
    
    def withdraw(self, amount: float):
        if amount <= 0:
            raise ValueError("Сумма снятия должна быть положительной")
        if amount > self._balance:
            raise InsufficientFundsError(
                currency_code=self.currency_code,
                available=self._balance,
                required=amount
            )
        self.balance -= amount
    
    def get_balance_info(self) -> Dict:
        return {
            "currency_code": self.currency_code,
            "balance": self._balance
        }


class Portfolio:
    def __init__(self, user_id: int, wallets: Optional[Dict[str, Wallet]] = None):
        self._user_id = user_id
        self._wallets = wallets or {}
    
    @property
    def user_id(self) -> int:
        return self._user_id
    
    @property
    def wallets(self) -> Dict[str, Wallet]:
        return self._wallets.copy()
    
    def add_currency(self, currency_code: str):
        if currency_code in self._wallets:
            raise ValueError(f"Кошелек для валюты {currency_code} уже существует")
        self._wallets[currency_code] = Wallet(currency_code)
    
    def get_wallet(self, currency_code: str) -> Wallet:
        wallet = self._wallets.get(currency_code)
        if not wallet:
            raise ValueError(f"Кошелек для валюты {currency_code} не найден")
        return wallet
    
    def get_total_value(self, base_currency: str = 'USD') -> float:
        # Для примера используем фиксированные курсы
        exchange_rates = {
            'USD_USD': 1.0,
            'EUR_USD': 1.0786,
            'BTC_USD': 59337.21,
            'RUB_USD': 0.01016,
            'ETH_USD': 3720.00,
        }
        
        total = 0.0
        for wallet in self._wallets.values():
            rate_key = f"{wallet.currency_code}_{base_currency}"
            rate = exchange_rates.get(rate_key)
            if rate:
                total += wallet.balance * rate
            else:
                # Если курса нет, считаем через USD
                if wallet.currency_code != 'USD':
                    to_usd = exchange_rates.get(f"{wallet.currency_code}_USD")
                    usd_to_base = exchange_rates.get(f"USD_{base_currency}")
                    if to_usd and usd_to_base:
                        total += wallet.balance * to_usd * usd_to_base
                else:
                    total += wallet.balance * exchange_rates.get(f"USD_{base_currency}", 1.0) # noqa: E501
        
        return total
    
    def to_dict(self) -> Dict:
        return {
            "user_id": self._user_id,
            "wallets": {
                code: wallet.get_balance_info() 
                for code, wallet in self._wallets.items()
            }
        }