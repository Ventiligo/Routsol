#!/usr/bin/env python
"""
Скрипт для создания нового пользователя
"""
import sys
from app import app, db
from models import User, UserSettings

def create_user(username, password, email=None):
    """Создает нового пользователя"""
    with app.app_context():
        # Проверка существования
        existing = User.query.filter_by(username=username).first()
        if existing:
            print(f"❌ Пользователь '{username}' уже существует!")
            return False
        
        if email:
            existing_email = User.query.filter_by(email=email).first()
            if existing_email:
                print(f"❌ Email '{email}' уже используется!")
                return False
        
        try:
            # Создание пользователя
            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            
            # Создание настроек по умолчанию
            settings = UserSettings(user_id=user.id)
            db.session.add(settings)
            
            db.session.commit()
            
            print(f"✅ Пользователь '{username}' успешно создан!")
            print(f"   ID: {user.id}")
            print(f"   Username: {user.username}")
            if email:
                print(f"   Email: {user.email}")
            print(f"\n🔑 Данные для входа:")
            print(f"   Логин: {username}")
            print(f"   Пароль: {password}")
            
            return True
        except Exception as e:
            print(f"❌ Ошибка при создании пользователя: {e}")
            db.session.rollback()
            return False

def main():
    """Главная функция"""
    print("=" * 60)
    print("👤 Создание нового пользователя Routsol Web")
    print("=" * 60)
    
    if len(sys.argv) < 3:
        print("\n📖 Использование:")
        print(f"   python {sys.argv[0]} <username> <password> [email]")
        print("\nПримеры:")
        print(f"   python {sys.argv[0]} testuser password123")
        print(f"   python {sys.argv[0]} testuser password123 test@example.com")
        sys.exit(1)
    
    username = sys.argv[1]
    password = sys.argv[2]
    email = sys.argv[3] if len(sys.argv) > 3 else None
    
    # Валидация
    if len(username) < 3:
        print("❌ Имя пользователя должно быть не менее 3 символов!")
        sys.exit(1)
    
    if len(password) < 8:
        print("❌ Пароль должен быть не менее 8 символов!")
        sys.exit(1)
    
    success = create_user(username, password, email)
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
