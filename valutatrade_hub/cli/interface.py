"""
CLI интерфейс для ValutaTrade Hub с командами парсера
"""

import argparse
import json
import logging
import shlex
import sys
from datetime import datetime
from typing import List

from ..core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
    InvalidCurrencyCodeError,
    RateUnavailableError,
    WalletNotFoundError,
)
from ..core.usecases import AuthService, PortfolioService, RateService
from ..infra.settings import get_settings
from ..parser_service.scheduler import RatesScheduler
from ..parser_service.updater import RatesUpdater


class CLIInterface:
    def __init__(self):
        self.parser = self._create_parser()
        self.settings = get_settings()
        
        # НЕ настраиваем логирование здесь - оно уже настроено в main.py
        self.logger = logging.getLogger("actions")
        
        # Инициализируем парсер и планировщик
        self.rates_updater = RatesUpdater()
        self.scheduler = None
        self.parser_config = None
    
    def _create_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            description="ValutaTrade Hub - Торговая платформа для криптовалют и фиата", # noqa: E501
            prog="valutatrade"
        )
        
        subparsers = parser.add_subparsers(dest="command", help="Доступные команды")
        
        # Команды аутентификации
        register_parser = subparsers.add_parser(
            "register", 
            help="Регистрация нового пользователя"
        )
        register_parser.add_argument("--username", required=True, help="Имя пользователя") # noqa: E501
        register_parser.add_argument("--password", required=True, help="Пароль")
        
        login_parser = subparsers.add_parser("login", help="Вход в систему")
        login_parser.add_argument("--username", required=True, help="Имя пользователя") # noqa: E501
        login_parser.add_argument("--password", required=True, help="Пароль")
        
        subparsers.add_parser("logout", help="Выход из системы")
        
        # Команды портфеля
        portfolio_parser = subparsers.add_parser(
            "show-portfolio", 
            help="Показать портфель"
        )
        portfolio_parser.add_argument(
            "--base", 
            default="USD", 
            help="Базовая валюта (по умолчанию: USD)"
        )
        
        buy_parser = subparsers.add_parser("buy", help="Купить валюту")
        buy_parser.add_argument(
            "--currency", 
            required=True, 
            help="Код покупаемой валюты (например, BTC)"
        )
        buy_parser.add_argument(
            "--amount", 
            type=float, 
            required=True, 
            help="Количество покупаемой валюты"
        )
        
        sell_parser = subparsers.add_parser("sell", help="Продать валюту")
        sell_parser.add_argument(
            "--currency", 
            required=True, 
            help="Код продаваемой валюты"
        )
        sell_parser.add_argument(
            "--amount", 
            type=float, 
            required=True, 
            help="Количество продаваемой валюты"
        )
        
        # Команды курсов (старые)
        rate_parser = subparsers.add_parser("get-rate", help="Получить курс валюты")
        rate_parser.add_argument(
            "--from", 
            dest="from_currency", 
            required=True, 
            help="Исходная валюта"
        )
        rate_parser.add_argument(
            "--to", 
            dest="to_currency", 
            required=True, 
            help="Целевая валюта"
        )
        
        # Команды парсера (новые)
        update_parser = subparsers.add_parser(
            "update-rates", 
            help="Обновить курсы валют из внешних API"
        )
        update_parser.add_argument(
            "--source", 
            choices=["all", "coingecko", "exchangerate"], 
            default="all", 
            help="Источник данных (по умолчанию: все)"
        )
        update_parser.add_argument(
            "--force", 
            action="store_true", 
            help="Принудительное обновление"
        )
        
        show_rates_parser = subparsers.add_parser(
            "show-rates", 
            help="Показать курсы из кеша"
        )
        show_rates_parser.add_argument(
            "--currency", 
            help="Показать курс только для указанной валюты"
        )
        show_rates_parser.add_argument(
            "--top", 
            type=int, 
            help="Показать N самых дорогих криптовалют"
        )
        show_rates_parser.add_argument(
            "--base", 
            default="USD", 
            help="Базовая валюта (по умолчанию: USD)"
        )
        show_rates_parser.add_argument(
            "--json", 
            action="store_true", 
            help="Вывод в формате JSON"
        )
        
        subparsers.add_parser(
            "list-currencies", 
            help="Показать список поддерживаемых валют"
        )
        
        config_parser = subparsers.add_parser("config", help="Показать конфигурацию") 
        config_parser.add_argument(
            "--key", 
            help="Ключ конфигурации (опционально)"
        )
        
        # Команды управления парсером        
        scheduler_parser = subparsers.add_parser(
            "scheduler", 
            help="Управление планировщиком обновлений"
        )
        scheduler_parser.add_argument(
            "action", 
            choices=["start", "stop", "status"], 
            help="Действие: start, stop, status"
        )
        scheduler_parser.add_argument(
            "--interval", 
            type=int, 
            help="Интервал обновления в минутах"
        )
        
        # Команды отладки (новые)
        debug_parser = subparsers.add_parser(
            "debug-rates", 
            help="Отладка курсов (для разработчиков)"
        )
        debug_parser.add_argument(
            "--api", 
            choices=["coingecko", "exchangerate"], 
            help="Тестировать конкретный API"
        )
        
        # Добавляем недостающие команды парсера (без присвоения переменным)
        subparsers.add_parser("parser-stats", help="Статистика работы парсера")
        subparsers.add_parser("validate-rates", help="Проверить валидность курсов")
        
        return parser
    
    def run(self, args=None):
        """Основной метод запуска"""
        if args is None:
            args = sys.argv[1:]
        
        # Если нет аргументов - запускаем интерактивный режим
        if not args:
            self.run_interactive()
        else:
            # Если первая команда help
            if args[0] == "help":
                self.show_help(show_welcome=True)
            else:
                self.execute_command(args)
    
    def run_interactive(self):
        """Запуск интерактивного режима"""
        # Сразу показываем справку при запуске
        self.show_help(show_welcome=True)
        
        while True:
            try:
                # Показ приглашения с именем пользователя
                user = AuthService.get_current_user()
                prompt = "\nvalutatrade"
                if user:
                    prompt += f"[{user.username}]"
                prompt += "> "
                
                user_input = input(prompt).strip()
                
                if not user_input:
                    continue
                
                # Проверка на команды выхода и помощи
                if user_input.lower() == "exit":
                    print("Выход из программы...")
                    self.logger.info("Завернение работы приложения")
                    break
                
                if user_input.lower() == "help":
                    self.show_help(show_welcome=False)
                    continue
                
                # Разбиваем ввод на аргументы
                args = shlex.split(user_input)
                
                # Выполняем команду
                self.execute_command(args)
                
            except KeyboardInterrupt:
                print("\n\nДля выхода введите 'exit'")
                try:
                    # Даем второй шанс
                    answer = input("Вы действительно хотите выйти? (y/n): ").strip().lower() # noqa: E501
                    if answer in ["y", "yes", "да"]:
                        print("Выход из программы...")
                        self.logger.info("Завершение работы приложения (KeyboardInterrupt)") # noqa: E501
                        break
                except KeyboardInterrupt:
                    print("\nВыход из программы...")
                    self.logger.info("Завернение работы приложения (KeyboardInterrupt)") # noqa: E501
                    break
            except EOFError:
                print("\nВыход из программы...")
                self.logger.info("Завернение работы приложения (EOFError)")
                break
            except Exception as e:
                print(f"Ошибка: {e}")
                self.logger.error(f"Неожиданная ошибка в интерактивном режиме: {e}")
    
    def execute_command(self, args: List[str]):
        """Выполнить одну команду"""
        try:
            parsed_args = self.parser.parse_args(args)
            
            # Обработка команд парсера
            if parsed_args.command == "update-rates":
                self.handle_update_rates(parsed_args)
            elif parsed_args.command == "show-rates":
                self.handle_show_rates(parsed_args)
            elif parsed_args.command == "parser-stats":
                self.handle_parser_stats(parsed_args)
            elif parsed_args.command == "validate-rates":
                self.handle_validate_rates(parsed_args)
            elif parsed_args.command == "scheduler":
                self.handle_scheduler(parsed_args)
            elif parsed_args.command == "debug-rates":
                self.handle_debug_rates(parsed_args)
            
            # Существующие команды...
            elif parsed_args.command == "register":
                self.handle_register(parsed_args)
            elif parsed_args.command == "login":
                self.handle_login(parsed_args)
            elif parsed_args.command == "logout":
                self.handle_logout()
            elif parsed_args.command == "show-portfolio":
                self.handle_show_portfolio(parsed_args)
            elif parsed_args.command == "buy":
                self.handle_buy(parsed_args)
            elif parsed_args.command == "sell":
                self.handle_sell(parsed_args)
            elif parsed_args.command == "get-rate":
                self.handle_get_rate(parsed_args)
            elif parsed_args.command == "list-currencies":
                self.handle_list_currencies()
            elif parsed_args.command == "config":
                self.handle_config(parsed_args)
            elif not parsed_args.command:
                print("Используйте 'help' для справки")
        
        except SystemExit:
            # Игнорируем выход от argparse при --help
            pass
        except Exception as e:
            print(f"Неожиданная ошибка: {e}")
            self.logger.error(f"Ошибка выполнения команды: {e}")
    
    def show_help(self, show_welcome: bool = False):
        """Показать красивую справку по командам"""
        if show_welcome:
            self._print_welcome_header()
        
        self._print_command_categories()
    
    def _print_welcome_header(self):
        """Печать приветственного заголовка"""
        print()
        print("╔" + "═" * 58 + "╗")
        print("║" + " " * 58 + "║")
        print("║" + "   ValutaTrade Hub - Торговая платформа".center(58) + "║")
        print("║" + " " * 58 + "║")
        print("╠" + "═" * 58 + "╣")
        print("║" + "   Добро пожаловать в интерактивную оболочку!".ljust(58) + "║")
        print("║" + "   Для выхода введите 'exit'".ljust(58) + "║")
        print("╚" + "═" * 58 + "╝")
        print()
    
    def _print_command_categories(self):
        """Печать категорий команд"""
        categories = [
            ("🔐 Аутентификация", [
                "register --username <имя> --password <пароль>",
                "login --username <имя> --password <пароль>",
                "logout"
            ]),
            ("💰 Торговля и портфель", [
                "show-portfolio [--base <валюта>]",
                "buy --currency <код> --amount <сумма>",
                "sell --currency <код> --amount <сумма>"
            ]),
            ("📈 Курсы валют", [
                "get-rate --from <валюта> --to <валюта>",
                "show-rates [--currency <код>] [--top N] [--base <валюта>]",
                "update-rates [--source <all|coingecko|exchangerate>]"
            ]),
            ("🐛 Отладка (разработчики)", [
                "debug-rates [--api <coingecko|exchangerate>] - тест API"
            ]),
            ("⚙️  Управление парсером", [
                "parser-stats                 - статистика работы",
                "validate-rates               - проверка валидности",
                "scheduler <start|stop|status> - управление планировщиком"
            ]),
            ("📚 Справочные команды", [
                "list-currencies              - список валют",
                "config [--key <ключ>]        - конфигурация",
                "help                         - эта справка",
                "exit                         - выход"
            ])
        ]
        
        print("📋 Основные команды:")
        print("─" * 60)
        
        for category_name, commands in categories:
            print(f"\n{category_name}:")
            for command in commands:
                print(f"  {command}")
        
        print("─" * 60)
        print("\n✨ Для подробной справки по команде: <команда> --help")
        print("=" * 60)
    
    def _get_scheduler(self):
        """Получить или создать экземпляр планировщика."""
        if self.scheduler is None:
            self.scheduler = RatesScheduler(self.rates_updater)
        return self.scheduler
    
    def handle_update_rates(self, args):
        """Обработка команды update-rates."""
        print("🔄 Обновление курсов валют...")
        print("-" * 50)
        
        try:
            result = self.rates_updater.run_update(source=args.source)
            
            if result.get("success"):
                print("✅ Курсы успешно обновлены!")
                print(f"   Обновлено пар: {result.get('updated_pairs', 0)}")
                print(f"   Добавлено новых: {result.get('new_pairs', 0)}")
                print(f"   Всего пар: {result.get('total_pairs', 0)}")
                print(f"   Время выполнения: {result.get('execution_time', 0):2f} сек") # noqa: E501
            else:
                print(f"{result.get('message', 'Неизвестная ошибка')}")
        
        except Exception as e:
            print(f"{e}")
            self.logger.error(f"Ошибка в handle_update_rates: {e}")
        
        print("-" * 50)
    
    def handle_show_rates(self, args):
        """Обработка команды show-rates."""
        from pathlib import Path
        
        rates_file = Path("data/rates.json")
        if not rates_file.exists():
            print("📭 Файл rates.json не найден")
            print("   Запустите 'update-rates' для получения данных")
            return
        
        with open(rates_file, 'r', encoding='utf-8') as f:
            rates_data = json.load(f)
        
        if not rates_data.get("pairs"):
            print("📭 Кеш курсов пуст")
            print("   Запустите 'update-rates' для получения данных")
            return
        
        pairs = rates_data.get("pairs", {})
        
        # Фильтрация по валюте, если указана
        if args.currency:
            currency_filter = args.currency.upper()
            filtered_pairs = {}
            for pair_key, pair_data in pairs.items():
                if (pair_key.startswith(f"{currency_filter}_") or 
                    pair_key.endswith(f"_{currency_filter}")):
                    filtered_pairs[pair_key] = pair_data
            pairs = filtered_pairs
        
        # Фильтруем топ N самых дорогих криптовалют
        if args.top:
            # Сортируем по значению курса (по убыванию)
            def get_rate_value(item):
                pair_data = item[1]
                if isinstance(pair_data, dict) and "rate" in pair_data:
                    return pair_data["rate"]
                return 0
            
            sorted_pairs = sorted(
                pairs.items(),
                key=get_rate_value,
                reverse=True
            )
            pairs = dict(sorted_pairs[:args.top])
        
        # Вывод в формате JSON
        if args.json:
            output = {
                "last_refresh": rates_data.get("last_refresh"),
                "base_currency": args.base.upper(),
                "rates": pairs
            }
            print(json.dumps(output, indent=2, ensure_ascii=False))
            return
        
        # Форматированный вывод
        print(f"📊 Курсы валют (база: {args.base.upper()})")
        print(f"   Обновлено: {rates_data.get('last_refresh', 'неизвестно')}")
        print("-" * 60)
        
        if not pairs:
            print("   Нет данных для отображения")
        else:
            for pair_key, pair_data in sorted(pairs.items()):
                if isinstance(pair_data, dict):
                    rate = pair_data.get("rate", 0)
                    source = pair_data.get("source", "unknown")
                    updated = pair_data.get("updated_at", "unknown")
                    if isinstance(updated, str) and len(updated) > 19:
                        updated = updated[:19]
                else:
                    rate = pair_data
                    source = "unknown"
                    updated = "unknown"
                
                # Форматируем в зависимости от величины
                if rate >= 1000:
                    rate_str = f"{rate:,.0f}"
                elif rate >= 1:
                    rate_str = f"{rate:,.2f}"
                elif rate >= 0.001:
                    rate_str = f"{rate:,.4f}"
                else:
                    rate_str = f"{rate:.6f}"
                
                print(f"  {pair_key:12} {rate_str:>15} {source:15} ({updated})")
        
        print("-" * 60)
        print(f"Всего курсов: {len(pairs)}")
    
    def handle_parser_stats(self, args):
        """Обработка команды parser-stats."""
        print("📈 Статистика работы парсера")
        print("=" * 60)
        
        try:
            stats = self.rates_updater.get_stats()
            
            print(f"Всего обновлений: {stats.get('total_updates', 0)}")
            print(f"Успешных: {stats.get('successful_updates', 0)}")
            print(f"Неудачных: {stats.get('failed_updates', 0)}")
            print(f"Последнее обновление: {stats.get('last_update_time', 'никогда')}")
            
            if stats.get('last_error'):
                print(f"Последняя ошибка: {stats.get('last_error')}")
            
            print(f"Всего пар курсов: {stats.get('total_pairs', 0)}")
            
            sources = stats.get('sources', {})
            if sources:
                print("\nПо источникам:")
                for source, count in sources.items():
                    print(f"  {source}: {count}")
            
            print(f"Последнее обновление кеша: {stats.get('last_refresh', 'неизвестно')}") # noqa: E501
            
        except Exception as e:
            print(f"❌ Ошибка при получении статистики: {e}")
            self.logger.error(f"Ошибка в handle_parser_stats: {e}")
        
        print("=" * 60)
    
    def handle_validate_rates(self, args):
        """Обработка команды validate-rates."""
        print("🔍 Проверка валидности курсов...")
        print("-" * 50)
        
        try:
            issues = self.rates_updater.validate_rates()
            
            if not issues:
                print("✅ Все курсы валидны и актуальны!")
            else:
                print(f"⚠️  Найдено проблем: {len(issues)}")
                
                for issue in issues:
                    print(f"\n  Пара: {issue.get('pair', 'unknown')}")
                    print(f"  Проблема: {issue.get('issue', 'unknown')}")
                    
                    if 'rate' in issue:
                        print(f"  Значение: {issue.get('rate')}")
                    
                    if 'age_hours' in issue:
                        print(f"  Возраст: {issue.get('age_hours')} часов")
                    
                    if 'updated_at' in issue:
                        print(f"  Обновлено: {issue.get('updated_at')}")
                
                print("\n⚠️  Рекомендуется запустить 'update-rates' для исправления проблем") # noqa: E501
        
        except Exception as e:
            print(f"❌ Ошибка при проверке валидности: {e}")
            self.logger.error(f"Ошибка в handle_validate_rates: {e}")
        
        print("-" * 50)
    
    def handle_scheduler(self, args):
        """Обработка команды scheduler."""
        scheduler = self._get_scheduler()
        
        print("📅 Управление планировщиком")
        print("=" * 50)
        
        try:
            if args.action == "start":
                interval = args.interval
                if interval:
                    print(f"Запуск планировщика с интервалом {interval} минут...")
                    scheduler.start(interval_minutes=interval)
                else:
                    print("Запуск планировщика с интервалом по умолчанию...")
                    scheduler.start()
                print("✅ Планировщик запущен")
            
            elif args.action == "stop":
                print("Остановка планировщика...")
                scheduler.stop()
                print("✅ Планировщик остановлен")
            
            elif args.action == "status":
                schedule_info = scheduler.get_schedule_info()
                
                status = "запущен" if schedule_info.get('is_running') else "остановлен"
                print(f"Состояние: {status}")
                
                jobs = schedule_info.get('jobs', [])
                if jobs:
                    print("\nЗадачи:")
                    for i, job in enumerate(jobs, 1):
                        print(f"  {i}. Следующий запуск: {job.get('next_run')}")
                        print(f"     Интервал: {job.get('interval')}")
                
                stats = schedule_info.get('stats', {})
                if stats:
                    print("\nСтатистика:")
                    updates = stats.get('scheduled_updates', 0)
                    print(f"  Запланированных обновлений: {updates}")
                    
                    last_update = stats.get('last_scheduled_update', 'никогда')
                    print(f"  Последнее запланированное: {last_update}")
                    
                    next_update = stats.get('next_scheduled_update', 'не запланировано') # noqa: E501
                    print(f"  Следующее запланированное: {next_update}")
            
        except Exception as e:
            print(f"❌ Ошибка при работе с планировщиком: {e}")
            self.logger.error(f"Ошибка в handle_scheduler: {e}")
        
        print("=" * 50)
    
    def handle_debug_rates(self, args):
        """Обработка команды debug-rates."""
        print("🐛 Отладка получения курсов")
        print("=" * 60)
        
        if args.api == "coingecko" or not args.api:
            print("\nТестирование CoinGecko API:")
            print("-" * 40)
            try:
                from ..parser_service.api_clients import CoinGeckoClient
                client = CoinGeckoClient()
                rates = client.fetch_rates()
                print(f"✅ Получено курсов: {len(rates)}")
                for pair, rate in list(rates.items())[:10]:
                    print(f"  {pair}: {rate}")
                if len(rates) > 10:
                    print(f"  ... и еще {len(rates) - 10} курсов")
            except Exception as e:
                print(f"❌ Ошибка: {e}")
        
        if args.api == "exchangerate" or not args.api:
            print("\nТестирование ExchangeRate-API:")
            print("-" * 40)
            try:
                from ..parser_service.api_clients import ExchangeRateApiClient
                client = ExchangeRateApiClient()
                rates = client.fetch_rates()
                print(f"✅ Получено курсов: {len(rates)}")
                
                # Покажем все полученные курсы для фиатных валют
                print("\nВсе полученные курсы фиатных валют:")
                for pair, rate in sorted(rates.items()):
                    if pair != "USD_USD":  # Пропускаем базовый курс
                        print(f"  {pair}: {rate}")
                
                # Покажем USD_USD отдельно
                if "USD_USD" in rates:
                    print(f"  USD_USD: {rates['USD_USD']}")
                    
            except Exception as e:
                print(f"❌ Ошибка: {e}")
        
        print("=" * 60)
    
    def _check_auth(self):
        """Проверка аутентификации"""
        user = AuthService.get_current_user()
        if not user:
            print("Сначала выполните login")
            raise ValueError("Сначала выполните login")
        return user
    
    def handle_register(self, args):
        try:
            user = AuthService.register(args.username, args.password)
            print(f"✓ Пользователь '{args.username}' зарегистрирован (id={user.user_id}).") # noqa: E501
        except ValueError as e:
            error_msg = str(e)
            if "уже занято" in error_msg:
                print(f"Имя пользователя '{args.username}' уже занято")
            elif "не короче 4 символов" in error_msg:
                print("Пароль должен быть не короче 4 символов")
            else:
                print(f"{error_msg}")
    
    def handle_login(self, args):
        try:
            AuthService.login(args.username, args.password)
            print(f"✓ Вы вошли как '{args.username}'")
        except ValueError as e:
            error_msg = str(e)
            if "Пользователь" in error_msg and "не найден" in error_msg:
                print(f"Пользователь '{args.username}' не найден")
            elif "Неверный пароль" in error_msg:
                print("Неверный пароль")
            else:
                print(f"{error_msg}")
    
    def handle_logout(self):
        AuthService.logout()
        print("✓ Вы вышли из системы")
    
    def handle_show_portfolio(self, args):
        user = self._check_auth()
        portfolio = PortfolioService.get_portfolio(user.user_id)
        
        if not portfolio.wallets:
            print(f"Портфель пользователя '{user.username}' пуст.")
            return
        
        print(f"Портфель пользователя '{user.username}' (база: {args.base}):")
        
        total_value = 0.0
        
        try:
            # Проверяем, доступна ли базовая валюта
            if args.base.upper() != "USD":
                RateService.get_rate("USD", args.base.upper())
        except (CurrencyNotFoundError, RateUnavailableError, ApiRequestError):
            print(f"Неизвестная базовая валюта '{args.base}'")
            return
        
        # Получаем информацию о курсах один раз для всех валют
        rates_cache = {}
        for currency_code, wallet in sorted(portfolio.wallets.items()):
            try:
                if currency_code not in rates_cache:
                    rates_cache[currency_code] = RateService.get_rate(currency_code, args.base.upper()) # noqa: E501
            except Exception:
                rates_cache[currency_code] = None
        
        # Выводим портфель (как в описании)
        for currency_code, wallet in sorted(portfolio.wallets.items()):
            try:
                rate_info = rates_cache[currency_code]
                if not rate_info:
                    raise RateUnavailableError(currency_code, args.base.upper())
                
                converted = wallet.balance * rate_info["rate"]
                total_value += converted
                
                # Форматирование баланса (как в описании)
                if currency_code in ["USD", "EUR", "GBP", "JPY", "CNY", "RUB"]:
                    balance_str = f"{wallet.balance:.2f}"
                    converted_str = f"{converted:.2f}"
                else:
                    balance_str = f"{wallet.balance:.4f}"
                    if converted >= 1:
                        converted_str = f"{converted:.2f}"
                    else:
                        converted_str = f"{converted:.4f}"
                
                print(f"- {currency_code}: {balance_str:>8} → {converted_str:>8} {args.base}") # noqa: E501
                
            except (CurrencyNotFoundError, RateUnavailableError, ApiRequestError):
                # Если курс не доступен, показываем только баланс
                if currency_code in ["USD", "EUR", "GBP", "JPY", "CNY", "RUB"]:
                    balance_str = f"{wallet.balance:.2f}"
                else:
                    balance_str = f"{wallet.balance:.4f}"
                
                print(f"- {currency_code}: {balance_str:>8} → {'N/A':>8} {args.base}")
            except Exception as e:
                print(f"- {currency_code}: {e}")
        
        print("-" * 33)  # 33 символа как в описании
        
        # Форматируем итоговую сумму (как в описании)
        total_formatted = f"{total_value:,.2f}"
        print(f"ИТОГО: {total_formatted} {args.base}")
    
    def handle_buy(self, args):
        user = self._check_auth()
        
        if args.amount <= 0:
            print("'amount' должен быть положительным числом")
            return
        
        try:
            result = PortfolioService.buy_currency(
                user.user_id, 
                args.currency.upper(), 
                args.amount
            )
            
            # Вывод как в описании
            print(f"Покупка выполнена: {args.amount:.4f} {args.currency.upper()} по курсу {result['rate']:.2f} USD/{args.currency.upper()}") # noqa: E501
            print("Изменения в портфеле:")
            print(f"- {args.currency.upper()}: было {result['old_balance']:.4f} → стало {result['new_balance']:.4f}") # noqa: E501
            print(f"Оценочная стоимость покупки: {result['cost_usd']:.2f} USD")
            
        except CurrencyNotFoundError as e:
            print(f"{e}")
            print("  Используйте команду 'list-currencies' для просмотра доступных валют") # noqa: E501
        except InsufficientFundsError as e:
            print(f"{e}")
        except RateUnavailableError:
            print(f"Не удалось получить курс для {args.currency}→USD")
            print("  Повторите попытку позже или проверьте доступность курса")
        except ApiRequestError:
            print(f"Не удалось получить курс для {args.currency}→USD")
            print("  Повторите попытку позже или проверьте доступность курса")
        except WalletNotFoundError as e:
            print(f"{e}")
            print("  Для работы с валютой сначала нужно создать кошелек "
                "(автоматически создается при первой покупке)")
        except InvalidCurrencyCodeError as e:
            print(f"{e}")
        except ValueError as e:
            print(f"{e}")
    
    def handle_sell(self, args):
        user = self._check_auth()
        
        if args.amount <= 0:
            print("'amount' должен быть положительным числом")
            return
        
        try:
            result = PortfolioService.sell_currency(
                user.user_id, 
                args.currency.upper(), 
                args.amount
            )
            
            # Вывод как в описании
            print(f"Продажа выполнена: {args.amount:.4f} {args.currency.upper()} по курсу {result['rate']:.2f} USD/{args.currency.upper()}") # noqa: E501
            print("Изменения в портфеле:")
            print(f"- {args.currency.upper()}: было {result['old_balance']:.4f} → стало {result['new_balance']:.4f}") # noqa: E501
            print(f"Оценочная выручка: {result['revenue_usd']:.2f} USD")
            
        except InsufficientFundsError as e:
            print(f"{e}")
            print("  Проверьте баланс валюты в вашем портфеле")
        except CurrencyNotFoundError as e:
            print(f"{e}")
        except RateUnavailableError:
            print(f"Не удалось получить курс для {args.currency}→USD")
            print("  Повторите попытку позже или проверьте доступность курса")
        except ApiRequestError:
            print(f"Не удалось получить курс для {args.currency}→USD")
            print("  Повторите попытку позже или проверьте доступность курса")
        except WalletNotFoundError:
            print(f"У вас нет кошелька '{args.currency}'. Добавьте валюту: она создаётся автоматически при первой покупке.")  # noqa: E501
        except InvalidCurrencyCodeError as e:
            print(f"{e}")
        except ValueError as e:
            print(f"{e}")
    
    def handle_get_rate(self, args):
        from_currency = args.from_currency.upper()
        to_currency = args.to_currency.upper()
        
        try:
            rate_info = RateService.get_rate(from_currency, to_currency)
            
            # Форматируем дату для вывода
            updated_at = rate_info['updated_at']
            try:
                dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                formatted_time = updated_at
            
            print(f"\nКурс {from_currency}→{to_currency}: {rate_info['rate']:.8f} (обновлено: {formatted_time})")  # noqa: E501
            
            # Выводим обратный курс
            if from_currency != to_currency and rate_info['rate'] != 0:
                reverse_rate = 1 / rate_info['rate']
                print(f"Обратный курс {to_currency}→{from_currency}: {reverse_rate:.8f}")  # noqa: E501
                
        except CurrencyNotFoundError as e:
            print(f"{e}")
            print("  Используйте команду 'list-currencies' для просмотра доступных валют")  # noqa: E501
        except RateUnavailableError as e:
            print(f"{e}. Повторите попытку позже.")
        except ApiRequestError as e:
            print(f"{e}. Повторите попытку позже.")
        except InvalidCurrencyCodeError as e:
            print(f"{e}")
        except ValueError as e:
            print(f"{e}")
    
    def handle_list_currencies(self):
        """Обработка команды list-currencies"""
        from ..core.currencies import get_currency_registry
        registry = get_currency_registry()
        
        print("\n" + "="*60)
        print("Поддерживаемые валюты:")
        print("="*60)
        
        # Фиатные валюты
        print("\nФиатные валюты:")
        print("-" * 40)
        for code, currency in registry.get_fiat_currencies().items():
            print(f"  {code} - {currency.name} ({currency.issuing_country})")
        
        # Криптовалюты
        print("\nКриптовалюты:")
        print("-" * 40)
        for code, currency in registry.get_crypto_currencies().items():
            print(f"  {code} - {currency.name} ({currency.algorithm})")
        
        print("-" * 40)
        print("\nИспользуйте: get-rate --from <валюта> --to <валюта>")
        print("Пример: get-rate --from USD --to BTC")
        print("="*60)
    
    def handle_config(self, args):
        """Обработка команда config"""
        print("\n" + "="*60)
        print("Конфигурация ValutaTrade Hub:")
        print("="*60)
        
        if args.key:
            value = self.settings.get(args.key, "Ключ не найден")
            print(f"{args.key}: {value}")
        else:
            config = self.settings.get_all()
            for k, v in sorted(config.items()):
                # Пропускаем длинные списки для читаемости
                if isinstance(v, list) and len(v) > 5:
                    print(f"{k}: [{len(v)} элементов]")
                else:
                    print(f"{k}: {v}")
        
        print("="*60)


def main():
    cli = CLIInterface()
    cli.run()


if __name__ == "__main__":
    main()