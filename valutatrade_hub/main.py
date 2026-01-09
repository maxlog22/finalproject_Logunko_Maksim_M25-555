#!/usr/bin/env python
"""Точка входа в приложение ValutaTrade Hub"""

import os
import sys

# Добавляем корневую директорию проекта в sys.path для корректных импортов
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def main():
    from valutatrade_hub.logging_config import configure_logging
    configure_logging()
    
    from valutatrade_hub.cli.interface import main as cli_main
    return cli_main()

if __name__ == "__main__":
    sys.exit(main())