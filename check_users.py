#!/usr/bin/env python3
"""
Скрипт для проверки пользователей в базе данных
"""

from app import app, db
from models import User, PsychologicalProfile, UserAnswer

def check_users():
    """Проверяет всех пользователей в базе данных"""
    with app.app_context():
        users = User.query.all()
        print(f"👥 Всего пользователей: {len(users)}")
        
        for user in users:
            print(f"\n👤 Пользователь: {user.username} (ID: {user.id})")
            
            # Проверяем ответы
            answers = UserAnswer.query.filter_by(user_id=user.id).all()
            print(f"   📝 Ответов: {len(answers)}")
            
            for i, answer in enumerate(answers):
                print(f"      #{i+1}: Завершено={answer.completed}, Ответов={len(answer.answers_data or {})}")
                if answer.answers_data:
                    print(f"           Данные: {answer.answers_data}")
            
            # Проверяем профиль
            profile = PsychologicalProfile.query.filter_by(user_id=user.id).first()
            if profile:
                print(f"   🧠 Профиль: E={profile.extraversion}, O={profile.openness}, S={profile.sensation_seeking}")
                print(f"           C={profile.conscientiousness}, P={profile.proactivity}, N={profile.neuroticism}")
            else:
                print("   ❌ Профиль отсутствует")

if __name__ == "__main__":
    check_users()