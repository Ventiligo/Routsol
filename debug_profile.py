#!/usr/bin/env python3
"""
Скрипт для диагностики проблемы с профилем пользователя
"""

from app import app, db, calculate_profile_scores, calculate_restrictions
from models import User, PsychologicalProfile, UserAnswer, Question

def debug_user_profile(username):
    """Диагностирует профиль конкретного пользователя"""
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if not user:
            print(f"❌ Пользователь '{username}' не найден")
            return
        
        print(f"👤 Пользователь: {user.username} (ID: {user.id})")
        
        # Проверяем ответы
        answers = UserAnswer.query.filter_by(user_id=user.id).all()
        print(f"📝 Найдено ответов: {len(answers)}")
        
        for answer in answers:
            print(f"   - Завершено: {answer.completed}")
            print(f"   - Данные: {answer.answers_data}")
            
            if answer.answers_data:
                # Пересчитываем баллы
                scores = calculate_profile_scores(answer.answers_data)
                restrictions = calculate_restrictions(answer.answers_data)
                print(f"   - Пересчитанные баллы: {scores}")
                print(f"   - Ограничения: {restrictions}")
        
        # Проверяем профиль
        profile = PsychologicalProfile.query.filter_by(user_id=user.id).first()
        if profile:
            print(f"🧠 Профиль найден:")
            print(f"   - Экстраверсия: {profile.extraversion}")
            print(f"   - Открытость: {profile.openness}")
            print(f"   - Поиск ощущений: {profile.sensation_seeking}")
            print(f"   - Сознательность: {profile.conscientiousness}")
            print(f"   - Проактивность: {profile.proactivity}")
            print(f"   - Невротизм: {profile.neuroticism}")
        else:
            print("❌ Профиль не найден")

def debug_questions():
    """Проверяет вопросы в базе данных"""
    with app.app_context():
        questions = Question.query.order_by(Question.order).all()
        print(f"❓ Всего вопросов: {len(questions)}")
        
        scales = {}
        for q in questions:
            if q.scale not in scales:
                scales[q.scale] = 0
            scales[q.scale] += 1
        
        print("📊 Вопросы по шкалам:")
        for scale, count in scales.items():
            print(f"   - {scale}: {count} вопросов")

def test_calculate_function():
    """Тестирует функцию подсчета баллов"""
    with app.app_context():
        # Тестовые ответы (все по 5 баллов)
        test_answers = {}
        questions = Question.query.all()
        for q in questions:
            test_answers[str(q.question_id)] = "5"
        
        print("🧪 Тест функции подсчета с максимальными баллами:")
        print(f"   - Тестовые ответы: {len(test_answers)} вопросов по 5 баллов")
        
        scores = calculate_profile_scores(test_answers)
        print(f"   - Результат: {scores}")
        
        # Ожидаемый результат: каждая шкала должна быть 15 (5 * 3)
        expected = {scale: 15 for scale in scores.keys()}
        print(f"   - Ожидалось: {expected}")

if __name__ == "__main__":
    print("🔍 Диагностика профиля пользователя")
    print("=" * 50)
    
    debug_questions()
    print()
    
    test_calculate_function()
    print()
    
    # Введите имя пользователя для диагностики
    username = input("Введите имя пользователя для диагностики: ").strip()
    if username:
        debug_user_profile(username)