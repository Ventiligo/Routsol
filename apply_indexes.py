#!/usr/bin/env python3
"""
Скрипт для применения индексов к базе данных
Улучшает производительность запросов
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from sqlalchemy import text

def apply_indexes():
    """Применяет индексы из create_indexes.sql"""
    print("=" * 60)
    print("Применение индексов к базе данных")
    print("=" * 60)
    
    # Читаем SQL файл
    sql_file = os.path.join(os.path.dirname(__file__), 'create_indexes.sql')
    
    if not os.path.exists(sql_file):
        print(f"Ошибка: файл {sql_file} не найден")
        return False
    
    with open(sql_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    # Разбиваем на отдельные команды
    commands = [cmd.strip() for cmd in sql_content.split(';') if cmd.strip() and not cmd.strip().startswith('--')]
    
    with app.app_context():
        try:
            for i, command in enumerate(commands, 1):
                # Пропускаем комментарии
                if command.startswith('--'):
                    continue
                
                print(f"\n[{i}/{len(commands)}] Выполнение команды...")
                
                # Выполняем команду
                db.session.execute(text(command))
                db.session.commit()
                
                # Выводим краткое описание
                if 'CREATE INDEX' in command:
                    index_name = command.split('idx_')[1].split(' ')[0] if 'idx_' in command else 'unknown'
                    print(f"✓ Создан индекс: idx_{index_name}")
                elif 'ANALYZE' in command:
                    table_name = command.split('ANALYZE')[1].strip()
                    print(f"✓ Обновлена статистика: {table_name}")
                elif 'SELECT' in command:
                    result = db.session.execute(text(command))
                    print(f"✓ Получено индексов: {result.rowcount}")
            
            print("\n" + "=" * 60)
            print("✅ Все индексы успешно применены!")
            print("=" * 60)
            
            # Выводим статистику
            print("\nСтатистика индексов:")
            result = db.session.execute(text("""
                SELECT 
                    tablename,
                    COUNT(*) as index_count
                FROM pg_indexes
                WHERE schemaname = 'public'
                GROUP BY tablename
                ORDER BY tablename;
            """))
            
            for row in result:
                print(f"  {row[0]}: {row[1]} индексов")
            
            return True
            
        except Exception as e:
            print(f"\n❌ Ошибка при применении индексов: {e}")
            db.session.rollback()
            return False

if __name__ == '__main__':
    success = apply_indexes()
    sys.exit(0 if success else 1)