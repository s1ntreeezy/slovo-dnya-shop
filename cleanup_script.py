#!/usr/bin/env python3
"""
Скрипт для очистки истёкших промокодов и слов дня.
Может запускаться через cron или планировщик задач.
"""

import os
import sys
from datetime import datetime

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, cleanup_expired_data

def main():
    """Основная функция очистки"""
    with app.app_context():
        try:
            print(f"[{datetime.now()}] Начинаем очистку истёкших данных...")
            promocodes_cleaned, words_cleaned = cleanup_expired_data()
            print(f"[{datetime.now()}] Очистка завершена. Удалено промокодов: {promocodes_cleaned}, слов дня: {words_cleaned}")
        except Exception as e:
            print(f"[{datetime.now()}] Ошибка при очистке: {e}")
            sys.exit(1)

if __name__ == '__main__':
    main() 