#!/usr/bin/env python3
"""
Скрипт для проверки данных в PostgreSQL базе
"""

import os
from dotenv import load_dotenv
load_dotenv()

from app import app, db
from models import User, PsychologicalProfile, UserAnswer, Question

def check_database():
    """Проверяет содержимое базы данных"""
    with app.app_context():
        print("🔍 Проверка базы данных PostgreSQL")
        print("=" * 50)
        
        # Проверяем пользователей
        users = User.query.all()
        print(f"👥 Всего пользователей: {len(users)}")
        
        if users:
            for user in users:
                print(f"\n👤 Пользователь: {user.username} (ID: {user.id})")
                print(f"   Возраст: {user.age}, Пол: {user.gender}")
                
                # Проверяем ответы
                answers = UserAnswer.query.filter_by(user_id=user.id).all()
                print(f"   📝 Ответов: {len(answers)}")
                
                for i, answer in enumerate(answers):
                    completed = "✅" if answer.completed else "❌"
                    answers_count = len(answer.answers_data or {})
                    print(f"      #{i+1}: {completed} Завершено, {answers_count} ответов")
                    
                    if answer.answers_data and len(answer.answers_data) > 0:
                        print(f"           Примеры ответов: {dict(list(answer.answers_data.items())[:3])}")
                
                # Проверяем профиль
                profile = PsychologicalProfile.query.filter_by(user_id=user.id).first()
                if profile:
                    print(f"   🧠 Профиль найден:")
                    print(f"      Экстраверсия: {profile.extraversion}")
                    print(f"      Открытость: {profile.openness}")
                    print(f"      Поиск ощущений: {profile.sensation_seeking}")
                    print(f"      Сознательность: {profile.conscientiousness}")
                    print(f"      Проактивность: {profile.proactivity}")
                    print(f"      Невротизм: {profile.neuroticism}")
                else:
                    print("   ❌ Профиль отсутствует")
        
        # Проверяем вопросы
        questions = Question.query.all()
        print(f"\n❓ Всего вопросов: {len(questions)}")
        
        if questions:
            scales = {}
            for q in questions:
                if q.scale not in scales:
                    scales[q.scale] = 0
                scales[q.scale] += 1
            
            print("📊 Вопросы по шкалам:")
            for scale, count in scales.items():
                print(f"   - {scale}: {count} вопросов")

if __name__ == "__main__":
    check_database()