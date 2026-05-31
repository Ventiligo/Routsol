#!/usr/bin/env python3
"""
Скрипт для исправления проблемных профилей
"""

import os
from dotenv import load_dotenv
load_dotenv()

from app import app, db, calculate_profile_scores, calculate_restrictions
from models import User, PsychologicalProfile, UserAnswer

def fix_zero_profiles():
    """Исправляет профили с нулевыми значениями"""
    with app.app_context():
        print("🔧 Исправление проблемных профилей")
        print("=" * 50)
        
        # Находим профили с нулевыми значениями
        zero_profiles = PsychologicalProfile.query.filter(
            PsychologicalProfile.extraversion == 0,
            PsychologicalProfile.openness == 0,
            PsychologicalProfile.sensation_seeking == 0,
            PsychologicalProfile.conscientiousness == 0,
            PsychologicalProfile.proactivity == 0,
            PsychologicalProfile.neuroticism == 0
        ).all()
        
        print(f"❌ Найдено {len(zero_profiles)} профилей с нулевыми значениями")
        
        for profile in zero_profiles:
            user = User.query.get(profile.user_id)
            print(f"\n🔧 Исправляем профиль пользователя: {user.username} (ID: {user.id})")
            
            # Ищем завершенные ответы с данными
            valid_answers = UserAnswer.query.filter_by(
                user_id=user.id, 
                completed=True
            ).filter(
                UserAnswer.answers_data.isnot(None)
            ).all()
            
            # Ищем ответы с реальными данными
            valid_answer = None
            for answer in valid_answers:
                if answer.answers_data and len(answer.answers_data) > 0:
                    valid_answer = answer
                    break
            
            if valid_answer and valid_answer.answers_data:
                print(f"   ✅ Найдены валидные ответы с {len(valid_answer.answers_data)} вопросами")
                
                # Пересчитываем профиль
                scores = calculate_profile_scores(valid_answer.answers_data)
                restrictions = calculate_restrictions(valid_answer.answers_data)
                
                print(f"   📊 Новые баллы: {scores}")
                
                # Обновляем профиль
                profile.extraversion = scores['extraversion']
                profile.openness = scores['openness']
                profile.sensation_seeking = scores['sensation_seeking']
                profile.conscientiousness = scores['conscientiousness']
                profile.proactivity = scores['proactivity']
                profile.neuroticism = scores['neuroticism']
                profile.no_alcohol = restrictions['no_alcohol']
                profile.physical_limits = restrictions['physical_limits']
                profile.low_budget = restrictions['low_budget']
                
                db.session.commit()
                print(f"   ✅ Профиль обновлен!")
                
            else:
                print(f"   ❌ Не найдены валидные ответы для пересчета")
                
                # Удаляем пустые записи ответов
                empty_answers = UserAnswer.query.filter_by(
                    user_id=user.id
                ).filter(
                    UserAnswer.answers_data.is_(None)
                ).all()
                
                # Также проверяем пустые словари вручную
                all_answers = UserAnswer.query.filter_by(user_id=user.id).all()
                for answer in all_answers:
                    if not answer.answers_data or len(answer.answers_data) == 0:
                        empty_answers.append(answer)
                
                if empty_answers:
                    print(f"   🗑️  Удаляем {len(empty_answers)} пустых записей ответов")
                    for empty in empty_answers:
                        db.session.delete(empty)
                    db.session.commit()

def create_test_answers(username):
    """Создает тестовые ответы для пользователя"""
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if not user:
            print(f"❌ Пользователь {username} не найден")
            return
        
        print(f"🧪 Создаем тестовые ответы для {username}")
        
        # Создаем тестовые ответы (средние значения)
        test_answers = {}
        for i in range(1, 22):  # 21 вопрос
            test_answers[str(i)] = "3"  # средний балл
        
        # Удаляем старые незавершенные ответы
        old_answers = UserAnswer.query.filter_by(user_id=user.id, completed=False).all()
        for old in old_answers:
            db.session.delete(old)
        
        # Создаем новые ответы
        new_answers = UserAnswer(
            user_id=user.id,
            answers_data=test_answers,
            completed=True
        )
        db.session.add(new_answers)
        
        # Пересчитываем профиль
        scores = calculate_profile_scores(test_answers)
        restrictions = calculate_restrictions(test_answers)
        
        profile = PsychologicalProfile.query.filter_by(user_id=user.id).first()
        if not profile:
            profile = PsychologicalProfile(user_id=user.id)
            db.session.add(profile)
        
        profile.extraversion = scores['extraversion']
        profile.openness = scores['openness']
        profile.sensation_seeking = scores['sensation_seeking']
        profile.conscientiousness = scores['conscientiousness']
        profile.proactivity = scores['proactivity']
        profile.neuroticism = scores['neuroticism']
        profile.no_alcohol = restrictions['no_alcohol']
        profile.physical_limits = restrictions['physical_limits']
        profile.low_budget = restrictions['low_budget']
        
        db.session.commit()
        
        print(f"✅ Тестовые ответы созданы, профиль обновлен: {scores}")

if __name__ == "__main__":
    print("Выберите действие:")
    print("1. Исправить профили с нулевыми значениями")
    print("2. Создать тестовые ответы для пользователя")
    
    choice = input("Введите номер (1 или 2): ").strip()
    
    if choice == "1":
        fix_zero_profiles()
    elif choice == "2":
        username = input("Введите имя пользователя: ").strip()
        if username:
            create_test_answers(username)
    else:
        print("Неверный выбор")