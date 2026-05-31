# app_sqlite.py - версия с SQLite для быстрого тестирования
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from functools import wraps
from models import db, User, PsychologicalProfile, UserAnswer, Question, UserState, Place, init_questions, FriendRequest, ActivityInvite, Meeting, MeetingParticipant, UserSettings, UserLike
import json
import os
import secrets
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv
load_dotenv()
from api_integrations import get_place_search_api, NominatimAPI
from ai_ranking import rank_places, get_recommendation_explanation, get_home_activities

# ===================== ПОГОДА =====================

# WMO weather code → (описание, эмодзи, категория)
WEATHER_CODES = {
    0:  ('Ясно', '☀️', 'clear'),
    1:  ('Преимущественно ясно', '🌤️', 'clear'),
    2:  ('Переменная облачность', '⛅', 'cloudy'),
    3:  ('Пасмурно', '☁️', 'cloudy'),
    45: ('Туман', '🌫️', 'fog'),
    48: ('Изморозь', '🌫️', 'fog'),
    51: ('Лёгкая морось', '🌦️', 'rain'),
    53: ('Морось', '🌦️', 'rain'),
    55: ('Сильная морось', '🌧️', 'rain'),
    61: ('Небольшой дождь', '🌦️', 'rain'),
    63: ('Дождь', '🌧️', 'rain'),
    65: ('Сильный дождь', '🌧️', 'rain'),
    71: ('Небольшой снег', '🌨️', 'snow'),
    73: ('Снег', '❄️', 'snow'),
    75: ('Сильный снег', '❄️', 'snow'),
    80: ('Ливень', '🌧️', 'rain'),
    81: ('Сильный ливень', '⛈️', 'storm'),
    82: ('Очень сильный ливень', '⛈️', 'storm'),
    95: ('Гроза', '⛈️', 'storm'),
    96: ('Гроза с градом', '⛈️', 'storm'),
    99: ('Сильная гроза с градом', '⛈️', 'storm'),
}

def fetch_weather(lat, lon):
    """Получает текущую погоду через Open-Meteo API (бесплатно, без ключа)"""
    try:
        url = (
            f'https://api.open-meteo.com/v1/forecast'
            f'?latitude={lat}&longitude={lon}'
            f'&current=temperature_2m,weathercode'
            f'&timezone=auto'
        )
        resp = requests.get(url, timeout=5)
        data = resp.json()
        current = data.get('current', {})
        temp = current.get('temperature_2m')
        code = current.get('weathercode', 0)
        desc, icon, _ = WEATHER_CODES.get(code, ('Неизвестно', '🌡️', 'unknown'))
        return {'temp': temp, 'code': code, 'desc': desc, 'icon': icon}
    except Exception as e:
        print(f'Ошибка получения погоды: {e}')
        return None

app = Flask(__name__)

# Безопасная конфигурация
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', secrets.token_hex(32))
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
app.config['SESSION_COOKIE_HTTPONLY'] = os.getenv('SESSION_COOKIE_HTTPONLY', 'True').lower() == 'true'
app.config['SESSION_COOKIE_SAMESITE'] = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
app.config['REMEMBER_COOKIE_SECURE'] = os.getenv('REMEMBER_COOKIE_SECURE', 'True').lower() == 'true'
app.config['REMEMBER_COOKIE_HTTPONLY'] = os.getenv('REMEMBER_COOKIE_HTTPONLY', 'True').lower() == 'true'

# Защита от CSRF
csrf = CSRFProtect(app)

# Rate limiting
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# Конфигурация базы данных — PostgreSQL
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

if not app.config['SQLALCHEMY_DATABASE_URI']:
    raise ValueError("DATABASE_URL не установлен в .env файле")

# Инициализация SQLAlchemy
db.init_app(app)

# Middleware для безопасных заголовков HTTP
@app.after_request
def add_security_headers(response):
    # Полностью отключаем CSP для отладки
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

# Создание таблиц при первом запуске
with app.app_context():
    db.create_all()
    # Проверяем, есть ли вопросы в БД
    if Question.query.count() == 0:
        init_questions()
        print("✅ База данных инициализирована")

# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================

def login_required(f):
    """Декоратор: требует авторизации"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Войдите в аккаунт, чтобы продолжить', 'info')
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated

def get_current_user():
    """Возвращает текущего авторизованного пользователя или None"""
    uid = session.get('user_id')
    if not uid:
        return None
    return User.query.get(uid)

# Делаем current_user доступным во всех шаблонах
@app.context_processor
def inject_user():
    return {
        'current_user': get_current_user(),
        'yandex_maps_key': os.getenv('YANDEX_MAPS_KEY', '')
    }

def calculate_profile_scores(answers_dict):
    """Вычисляет баллы по шкалам из словаря ответов"""
    scores = {
        'extraversion': 0,
        'openness': 0,
        'sensation_seeking': 0,
        'conscientiousness': 0,
        'proactivity': 0,
        'neuroticism': 0
    }
    
    counts = {scale: 0 for scale in scores.keys()}
    questions = Question.query.all()
    
    for question in questions:
        answer = answers_dict.get(str(question.question_id))
        if answer and answer.isdigit():
            score = int(answer)
            if question.scale in scores:
                scores[question.scale] += score
                counts[question.scale] += 1
    
    for scale in scores:
        if counts[scale] > 0:
            factor = 3 / counts[scale]
            scores[scale] = int(scores[scale] * factor)
    
    return scores


def calculate_restrictions(answers_dict):
    """Вычисляет флаги ограничений из ответов (вопросы 19, 20, 21)"""
    def is_yes(qid):
        val = answers_dict.get(str(qid))
        return val and int(val) >= 4  # 4 или 5 = да

    return {
        'no_alcohol':      is_yes(19),
        'physical_limits': is_yes(20),
        'low_budget':      is_yes(21),
    }

# ===================== МАРШРУТЫ АВТОРИЗАЦИИ =====================

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("10 per hour")
def register():
    if get_current_user():
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')

        # Валидация входных данных
        if not username or len(username) < 3 or len(username) > 30:
            flash('Имя пользователя должно быть от 3 до 30 символов', 'error')
            return render_template('register.html')
        
        if not username.isalnum():
            flash('Имя пользователя должно содержать только буквы и цифры', 'error')
            return render_template('register.html')
        
        if email and not is_valid_email(email):
            flash('Введите корректный email адрес', 'error')
            return render_template('register.html')
        
        if not password or len(password) < 8:
            flash('Пароль должен быть не менее 8 символов', 'error')
            return render_template('register.html')
        
        if password != password2:
            flash('Пароли не совпадают', 'error')
            return render_template('register.html')
        
        # Проверка на существующего пользователя
        if User.query.filter_by(username=username).first():
            flash('Имя пользователя уже занято', 'error')
            return render_template('register.html')
        
        if email and User.query.filter_by(email=email).first():
            flash('Email уже зарегистрирован', 'error')
            return render_template('register.html')

        user = User(username=username, email=email or None)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        # Безопасная сессия
        session['user_id'] = user.id
        session.permanent = True
        
        flash(f'Добро пожаловать, {username}!', 'success')
        return redirect(url_for('index'))
    return render_template('register.html')


def is_valid_email(email):
    """Простая валидация email"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def is_safe_url(target):
    """Проверяет, является ли URL безопасным для перенаправления"""
    from urllib.parse import urlparse, urljoin
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per hour")
def login():
    if get_current_user():
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        # Базовая валидация
        if not username or not password:
            flash('Заполните все поля', 'error')
            return render_template('login.html')
        
        user = User.query.filter_by(username=username).first()
        
        # Задержка при неудачной попытке входа для защиты от брутфорса
        import time
        if not user or not user.check_password(password):
            time.sleep(1)  # Задержка 1 секунда
            flash('Неверное имя пользователя или пароль', 'error')
            return render_template('login.html')
        
        # Безопасная сессия
        session['user_id'] = user.id
        session.permanent = True
        
        flash(f'Добро пожаловать, {user.username}!', 'success')
        next_url = request.args.get('next') or url_for('index')
        
        # Проверка безопасного next URL
        if next_url and not is_safe_url(next_url):
            next_url = url_for('index')
            
        return redirect(next_url)
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Вы вышли из аккаунта', 'info')
    return redirect(url_for('index'))


# ===================== МАРШРУТЫ =====================

@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')

@app.route('/questionnaire')
@login_required
def questionnaire():
    """Страница анкеты"""
    user = get_current_user()
    questions = Question.query.order_by(Question.order).all()
    
    current_answers = UserAnswer.query.filter_by(
        user_id=user.id, 
        completed=False
    ).first()
    
    if current_answers:
        saved_answers = current_answers.answers_data
    else:
        saved_answers = {}
        new_answers = UserAnswer(
            user_id=user.id,
            answers_data={},
            completed=False,
            session_id=session.get('_id', '')
        )
        db.session.add(new_answers)
        db.session.commit()
    
    saved_demographics = {
        'age': user.age,
        'gender': user.gender
    }
    
    questions_json = []
    for q in questions:
        questions_json.append({
            'id': q.question_id,
            'text': q.text,
            'scale': q.scale,
            'order': q.order,
            'options': q.options
        })
    
    return render_template(
        'questionnaire.html', 
        questions=questions_json,
        questions_json=json.dumps(questions_json),
        saved_answers=json.dumps(saved_answers),
        saved_demographics=saved_demographics
    )

@app.route('/api/save_answer', methods=['POST'])
@login_required
def save_answer():
    """Сохраняет ответ на вопрос (AJAX)"""
    try:
        data = request.json
        user = get_current_user()
        
        if not data:
            print("❌ Нет данных в запросе")
            return jsonify({'status': 'error', 'message': 'Нет данных'}), 400
        
        question_id = str(data.get('question_id'))
        answer = data.get('answer')
        
        if not question_id or not answer:
            print(f"❌ Неполные данные: question_id={question_id}, answer={answer}")
            return jsonify({'status': 'error', 'message': 'Неполные данные'}), 400
        
        print(f"💾 Получен запрос: пользователь {user.username}, вопрос {question_id}, ответ {answer}")
        
        current_answers = UserAnswer.query.filter_by(
            user_id=user.id, 
            completed=False
        ).first()
        
        if not current_answers:
            print(f"📝 Создаем новую запись ответов для пользователя {user.id}")
            current_answers = UserAnswer(
                user_id=user.id,
                answers_data={},
                completed=False
            )
            db.session.add(current_answers)
            db.session.flush()  # Получаем ID
        
        # Получаем текущие ответы
        answers = current_answers.answers_data or {}
        old_count = len(answers)
        answers[question_id] = answer
        
        # Важно: создаем новый словарь, чтобы SQLAlchemy увидел изменение
        current_answers.answers_data = dict(answers)
        
        # Явно помечаем поле как измененное
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(current_answers, 'answers_data')
        
        db.session.commit()
        
        print(f"✅ Ответ сохранен: Q{question_id}={answer}, было {old_count} ответов, стало {len(answers)}")
        
        return jsonify({'status': 'ok', 'total_answers': len(answers)})
        
    except Exception as e:
        print(f"❌ Ошибка сохранения ответа: {e}")
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/submit_questionnaire', methods=['POST'])
@login_required
def submit_questionnaire():
    """Завершение анкеты и подсчёт результатов"""
    user = get_current_user()
    
    age = request.form.get('age')
    gender = request.form.get('gender')
    
    if age:
        user.age = int(age)
    if gender:
        user.gender = gender
    
    current_answers = UserAnswer.query.filter_by(
        user_id=user.id, 
        completed=False
    ).first()
    
    if not current_answers:
        print(f"❌ Анкета не найдена для пользователя {user.username} (ID: {user.id})")
        flash('Ошибка: анкета не найдена. Попробуйте пройти анкету заново.', 'error')
        return redirect(url_for('questionnaire'))
    
    print(f"📊 Пользователь {user.username}: ответы = {current_answers.answers_data}")
    
    # Проверяем, что есть достаточно ответов
    answers_count = len(current_answers.answers_data or {})
    expected_count = Question.query.count()
    
    if answers_count < expected_count:
        print(f"❌ Недостаточно ответов: {answers_count}/{expected_count}")
        flash(f'Не все вопросы отвечены ({answers_count} из {expected_count}). Пожалуйста, ответьте на все вопросы.', 'error')
        return redirect(url_for('questionnaire'))
    
    current_answers.completed = True
    scores = calculate_profile_scores(current_answers.answers_data)
    restrictions = calculate_restrictions(current_answers.answers_data)
    
    print(f"📈 Вычисленные баллы: {scores}")
    print(f"🚫 Ограничения: {restrictions}")
    
    # Проверяем, что баллы не нулевые
    total_score = sum(scores.values())
    if total_score == 0:
        print(f"❌ Все баллы равны нулю! Проблема с подсчетом.")
        flash('Ошибка подсчета результатов. Обратитесь к администратору.', 'error')
        return redirect(url_for('questionnaire'))
    
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
    
    print(f"✅ Профиль сохранен для {user.username}: E={profile.extraversion}, O={profile.openness}")
    
    flash('✅ Анкета успешно завершена! Ваш психологический профиль сохранён.', 'success')
    return redirect(url_for('profile'))

@app.route('/profile')
@login_required
def profile():
    """Страница профиля с результатами"""
    user = get_current_user()
    profile = PsychologicalProfile.query.filter_by(user_id=user.id).first()
    
    if not profile:
        flash('Сначала нужно заполнить анкету', 'info')
        return redirect(url_for('questionnaire'))
    
    def interpret_scale(scale_name, score, scale_type='normal'):
        if score is None or score == 0:
            return {'level': 'unknown', 'text': 'Не определено', 'score': 0}
        
        if score >= 11:
            level = 'high'
            text = 'Высокая потребность в покое и тишине' if scale_type == 'neuroticism' else 'Высокий уровень'
        elif score >= 7:
            level = 'medium'
            text = 'Средний уровень'
        else:
            level = 'low'
            text = 'Низкая потребность в покое' if scale_type == 'neuroticism' else 'Низкий уровень'
        
        return {'level': level, 'text': text, 'score': score}
    
    profile_data = {
        'extraversion': interpret_scale('extraversion', profile.extraversion),
        'openness': interpret_scale('openness', profile.openness),
        'sensation_seeking': interpret_scale('sensation_seeking', profile.sensation_seeking),
        'conscientiousness': interpret_scale('conscientiousness', profile.conscientiousness),
        'proactivity': interpret_scale('proactivity', profile.proactivity),
        'neuroticism': interpret_scale('neuroticism', profile.neuroticism, 'neuroticism'),
    }
    
    return render_template('profile.html', profile=profile_data)

@app.route('/api/profile')
@login_required
def api_profile():
    """API для получения профиля в JSON"""
    user = get_current_user()
    profile = PsychologicalProfile.query.filter_by(user_id=user.id).first()
    
    if not profile:
        return jsonify({'error': 'Profile not found'}), 404
    
    return jsonify(profile.to_dict())

@app.route('/ask_state')
@login_required
def ask_state():
    """Страница для ввода текущего состояния"""
    user = get_current_user()
    
    profile = PsychologicalProfile.query.filter_by(user_id=user.id).first()
    if not profile:
        flash('Сначала нужно заполнить анкету', 'info')
        return redirect(url_for('questionnaire'))
    
    return render_template('ask_state.html')

@app.route('/save_state', methods=['POST'])
@login_required
def save_state():
    """Сохраняет текущее состояние пользователя и координаты"""
    user = get_current_user()
    
    if not user or not user.id:
        flash('Ошибка: не удалось найти пользователя', 'error')
        return redirect(url_for('index'))
    
    fatigue = request.form.get('fatigue')
    mood = request.form.get('mood')
    company = request.form.get('company')
    latitude = request.form.get('latitude')
    longitude = request.form.get('longitude')
    address = request.form.get('address', '')
    
    # Проверка обязательных полей
    if not all([fatigue, mood, company, latitude, longitude]):
        flash('Пожалуйста, заполните все поля и укажите местоположение', 'error')
        return redirect(url_for('ask_state'))
    
    state = UserState(
        user_id=user.id,  # теперь user точно не None и имеет id
        fatigue_level=fatigue,
        fatigue_value=fatigue_value_map.get(fatigue, 5),
        mood=mood,
        with_company=company,
        time_of_day=get_time_of_day(),
        latitude=float(latitude) if latitude else None,
        longitude=float(longitude) if longitude else None,
        address=address
    )

    # Получаем погоду по координатам
    if latitude and longitude:
        weather = fetch_weather(float(latitude), float(longitude))
        if weather:
            state.weather_temp = weather['temp']
            state.weather_code = weather['code']
            state.weather_desc = weather['desc']
            state.weather_icon = weather['icon']
    
    db.session.add(state)
    db.session.commit()
    
    if latitude and longitude:
        find_nearby_places(float(latitude), float(longitude), state.id)
    
    flash('✅ Состояние учтено! Подбираем рекомендации...', 'success')
    return redirect(url_for('recommendations'))

@app.route('/recommendations')
@login_required
def recommendations():
    """Страница с рекомендациями мест"""
    user = get_current_user()

    state = user.get_latest_state()

    if not state:
        flash('Сначала нужно указать ваше состояние', 'info')
        return redirect(url_for('ask_state'))

    places = Place.query.filter_by(state_id=state.id).all()
    profile = PsychologicalProfile.query.filter_by(user_id=user.id).first()

    # Определяем режим: высокая усталость → рекомендуем остаться дома
    stay_home = state.fatigue_level == 'high'

    home_activities = []
    if profile:
        home_activities = get_home_activities(profile, state)

    ranked_places = []
    if not stay_home:
        if profile and places:
            # Получаем лайки пользователя для персонализации рекомендаций
            from ai_ranking import get_user_likes_dict
            user_likes = get_user_likes_dict(user)
            
            ranked_places = rank_places(profile, state, places, user_age=user.age, user_likes=user_likes)
            db.session.commit()
            for place in ranked_places[:5]:
                place.explanation = get_recommendation_explanation(profile, state, place)
        else:
            ranked_places = sorted(places, key=lambda p: p.distance)
        # Показываем только топ-5
        ranked_places = ranked_places[:5]

    return render_template('recommendations.html',
                           places=ranked_places,
                           state=state,
                           profile=profile,
                           home_activities=home_activities,
                           stay_home=stay_home)

def get_time_of_day():
    """Определяет время суток"""
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return 'morning'
    elif 12 <= hour < 17:
        return 'afternoon'
    elif 17 <= hour < 22:
        return 'evening'
    else:
        return 'night'

fatigue_value_map = {
    'high': 8,
    'medium': 5,
    'low': 2
}

# ===================== API ИНТЕГРАЦИЯ =====================

def find_nearby_places(latitude, longitude, state_id, radius=2000):
    """Ищет места рядом с указанными координатами"""
    api = get_place_search_api('nominatim')
    
    place_categories = [
        {'type': 'cafe', 'query': 'кафе', 'activity': 'passive'},
        {'type': 'restaurant', 'query': 'ресторан', 'activity': 'passive'},
        {'type': 'park', 'query': 'парк', 'activity': 'moderate'},
        {'type': 'cinema', 'query': 'кинотеатр', 'activity': 'passive'},
        {'type': 'gym', 'query': 'спортзал', 'activity': 'active'},
        {'type': 'museum', 'query': 'музей', 'activity': 'moderate'},
        {'type': 'bar', 'query': 'бар', 'activity': 'moderate'},
        {'type': 'shopping', 'query': 'торговый центр', 'activity': 'moderate'},
    ]
    
    places_found = []
    
    for category in place_categories:
        try:
            results = api.search_places(latitude, longitude, category['query'], radius, limit=5)
            
            for result in results:
                attributes = infer_place_attributes(category['type'], result)
                
                place = Place(
                    state_id=state_id,
                    name=result['name'],
                    place_type=category['type'],
                    address=result['address'],
                    latitude=result['latitude'],
                    longitude=result['longitude'],
                    distance=result['distance'],
                    avg_price=attributes['avg_price'],
                    atmosphere=attributes['atmosphere'],
                    capacity=attributes['capacity'],
                    activity_level=category['activity'],
                    api_source=result['api_source'],
                    api_id=result['api_id'],
                    api_data=result.get('api_data')
                )
                
                db.session.add(place)
                places_found.append(place)
        
        except Exception as e:
            print(f"Ошибка поиска {category['type']}: {e}")
            continue
    
    db.session.commit()
    print(f"✅ Найдено {len(places_found)} мест рядом с пользователем")
    return places_found

def infer_place_attributes(place_type, api_data):
    """Определяет психологические атрибуты места"""
    attributes = {
        'avg_price': 'medium',
        'atmosphere': 'neutral',
        'capacity': 'medium'
    }
    
    if place_type in ['cafe', 'restaurant']:
        attributes['atmosphere'] = 'relaxing'
        attributes['capacity'] = 'small'
        attributes['avg_price'] = 'medium'
    elif place_type == 'park':
        attributes['atmosphere'] = 'quiet'
        attributes['capacity'] = 'large'
        attributes['avg_price'] = 'low'
    elif place_type == 'bar':
        attributes['atmosphere'] = 'noisy'
        attributes['capacity'] = 'medium'
        attributes['avg_price'] = 'medium'
    elif place_type == 'gym':
        attributes['atmosphere'] = 'energetic'
        attributes['capacity'] = 'medium'
        attributes['avg_price'] = 'high'
    elif place_type == 'cinema':
        attributes['atmosphere'] = 'quiet'
        attributes['capacity'] = 'large'
        attributes['avg_price'] = 'medium'
    elif place_type == 'museum':
        attributes['atmosphere'] = 'quiet'
        attributes['capacity'] = 'medium'
        attributes['avg_price'] = 'medium'
    elif place_type == 'shopping':
        attributes['atmosphere'] = 'noisy'
        attributes['capacity'] = 'large'
        attributes['avg_price'] = 'high'
    
    return attributes

@app.route('/place/<int:place_id>')
@login_required
def place_detail(place_id):
    """Страница конкретного места"""
    place = Place.query.get_or_404(place_id)
    user = get_current_user()
    profile = PsychologicalProfile.query.filter_by(user_id=user.id).first()
    state = UserState.query.get(place.state_id)

    explanation = None
    if profile and state:
        explanation = get_recommendation_explanation(profile, state, place)

    # Другие места того же типа из того же состояния
    similar = Place.query.filter(
        Place.state_id == place.state_id,
        Place.place_type == place.place_type,
        Place.id != place.id
    ).limit(4).all()

    return render_template('place_detail.html', place=place, explanation=explanation,
                           state=state, similar=similar)


@app.route('/home-activity/<activity_id>')
@login_required
def home_activity_detail(activity_id):
    """Страница конкретного вида домашнего отдыха"""
    user = get_current_user()
    profile = PsychologicalProfile.query.filter_by(user_id=user.id).first()
    state = user.get_latest_state()

    if not profile or not state:
        flash('Сначала заполните анкету и укажите состояние', 'info')
        return redirect(url_for('ask_state'))

    all_activities = get_home_activities(profile, state)
    activity = next((a for a in all_activities if a['id'] == activity_id), None)

    if not activity:
        flash('Активность не найдена', 'error')
        return redirect(url_for('recommendations'))

    others = [a for a in all_activities if a['id'] != activity_id][:4]

    return render_template('home_activity_detail.html', activity=activity,
                           others=others, state=state)


@app.route('/history')
@login_required
def history():
    """История рекомендаций пользователя"""
    user = get_current_user()
    # Все сессии пользователя, у которых есть места, от новых к старым
    states = (UserState.query
              .filter_by(user_id=user.id)
              .order_by(UserState.created_at.desc())
              .all())

    history_items = []
    for state in states:
        places = Place.query.filter_by(state_id=state.id).order_by(
            Place.match_score.desc().nullslast()
        ).limit(5).all()
        if places:
            history_items.append({'state': state, 'places': places})

    return render_template('history.html', history_items=history_items)


# ===================== СОЦИАЛЬНЫЕ МАРШРУТЫ =====================

@app.route('/social')
@login_required
def social():
    """Главная страница социальной сети"""
    user = get_current_user()
    friends = user.get_friends()
    pending_requests = FriendRequest.query.filter_by(receiver_id=user.id, status='pending').all()
    incoming_invites = ActivityInvite.query.filter_by(receiver_id=user.id, status='pending').order_by(ActivityInvite.created_at.desc()).all()

    # История: все принятые/отклонённые приглашения (входящие и исходящие)
    invite_history = ActivityInvite.query.filter(
        ((ActivityInvite.sender_id == user.id) | (ActivityInvite.receiver_id == user.id)),
        ActivityInvite.status != 'pending'
    ).order_by(ActivityInvite.created_at.desc()).limit(50).all()

    return render_template('social.html', friends=friends,
                           pending_requests=pending_requests,
                           incoming_invites=incoming_invites,
                           invite_history=invite_history,
                           current_user_id=user.id)


@app.route('/social/users')
@login_required
def social_users():
    """Поиск пользователей"""
    user = get_current_user()
    q = request.args.get('q', '').strip()
    users = []
    if q:
        users = User.query.filter(
            User.username.ilike(f'%{q}%'),
            User.id != user.id
        ).limit(20).all()
    return render_template('social_users.html', users=users, query=q)


@app.route('/social/user/<int:uid>')
@login_required
def social_profile(uid):
    """Профиль другого пользователя"""
    user = get_current_user()
    target = User.query.get_or_404(uid)
    req = user.friend_request_status(uid)
    friends = target.get_friends()
    privacy = target.settings
    return render_template('social_profile.html', target=target, req=req,
                           friends=friends, privacy=privacy)


@app.route('/social/friend_request/<int:uid>', methods=['POST'])
@login_required
def send_friend_request(uid):
    user = get_current_user()
    if uid == user.id:
        return jsonify({'error': 'Cannot add yourself'}), 400
    existing = user.friend_request_status(uid)
    if existing:
        return jsonify({'error': 'Request already exists'}), 400
    req = FriendRequest(sender_id=user.id, receiver_id=uid)
    db.session.add(req)
    db.session.commit()
    return jsonify({'status': 'sent'})


@app.route('/social/friend_request/<int:req_id>/respond', methods=['POST'])
@login_required
def respond_friend_request(req_id):
    user = get_current_user()
    req = FriendRequest.query.get_or_404(req_id)
    if req.receiver_id != user.id:
        return jsonify({'error': 'Forbidden'}), 403
    action = request.json.get('action')
    if action == 'accept':
        req.status = 'accepted'
    elif action == 'decline':
        req.status = 'declined'
    db.session.commit()
    return jsonify({'status': req.status})


@app.route('/social/invite', methods=['POST'])
@login_required
def send_activity_invite():
    user = get_current_user()
    data = request.json
    receiver_id = data.get('receiver_id')
    if not receiver_id:
        return jsonify({'error': 'No receiver'}), 400
    invite = ActivityInvite(
        sender_id=user.id,
        receiver_id=receiver_id,
        activity_type=data.get('activity_type', 'home_activity'),
        activity_id=str(data.get('activity_id', '')),
        activity_name=data.get('activity_name', ''),
        activity_description=data.get('activity_description', ''),
        activity_icon=data.get('activity_icon', 'fa-star'),
        message=data.get('message', '')
    )
    db.session.add(invite)
    db.session.commit()
    return jsonify({'status': 'sent', 'invite_id': invite.id})


@app.route('/social/invite/<int:invite_id>/respond', methods=['POST'])
@login_required
def respond_invite(invite_id):
    user = get_current_user()
    invite = ActivityInvite.query.get_or_404(invite_id)
    if invite.receiver_id != user.id:
        return jsonify({'error': 'Forbidden'}), 403
    action = request.json.get('action')
    if action in ('accept', 'decline'):
        invite.status = 'accepted' if action == 'accept' else 'declined'
        db.session.commit()
    return jsonify({'status': invite.status})


@app.route('/social/calendar')
@login_required
def calendar():
    return redirect(url_for('social'))

@app.route('/social/meeting/new', methods=['GET', 'POST'])
@login_required
def new_meeting():
    return redirect(url_for('social'))

@app.route('/social/meeting/<int:meeting_id>')
@login_required
def meeting_detail(meeting_id):
    return redirect(url_for('social'))

@app.route('/social/meeting/<int:meeting_id>/respond', methods=['POST'])
@login_required
def respond_meeting(meeting_id):
    return redirect(url_for('social'))


@app.route('/api/social/notifications')
@login_required
def social_notifications():
    user = get_current_user()
    pending_requests = FriendRequest.query.filter_by(receiver_id=user.id, status='pending').count()
    pending_invites = ActivityInvite.query.filter_by(receiver_id=user.id, status='pending').count()
    total = pending_requests + pending_invites
    return jsonify({'total': total, 'requests': pending_requests, 'invites': pending_invites})


@app.route('/api/friends')
@login_required
def api_friends():
    user = get_current_user()
    friends = user.get_friends()
    return jsonify({'friends': [{'id': f.id, 'username': f.username} for f in friends]})


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    user = get_current_user()
    s = user.settings
    if not s:
        s = UserSettings(user_id=user.id)
        db.session.add(s)
        db.session.commit()

    if request.method == 'POST':
        s.show_age              = 'show_age'              in request.form
        s.show_email            = 'show_email'            in request.form
        s.show_gender           = 'show_gender'           in request.form
        s.show_profile_scores   = 'show_profile_scores'   in request.form
        s.show_restrictions     = 'show_restrictions'     in request.form
        s.show_likes            = 'show_likes'            in request.form
        s.allow_friend_requests = 'allow_friend_requests' in request.form
        db.session.commit()
        flash('Настройки сохранены', 'success')
        return redirect(url_for('settings'))

    return render_template('settings.html', s=s, user=user)


# ===================== API ДЛЯ ЛАЙКОВ =====================

@app.route('/api/like', methods=['POST'])
@login_required
@limiter.limit("100 per hour")
def api_like():
    """API для установки лайка/дизлайка"""
    user = get_current_user()
    data = request.json
    
    # Валидация входных данных
    object_type = data.get('object_type')  # 'place' или 'home_activity'
    object_id = data.get('object_id')
    reaction = data.get('reaction')  # 'like', 'dislike', 'neutral'
    object_name = data.get('object_name')
    object_type_detail = data.get('object_type_detail')
    
    if not all([object_type, object_id, reaction]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Валидация типов
    if object_type not in ['place', 'home_activity']:
        return jsonify({'error': 'Invalid object type'}), 400
    
    if reaction not in ['like', 'dislike', 'neutral']:
        return jsonify({'error': 'Invalid reaction'}), 400
    
    # Валидация object_id (должен быть числом или строкой)
    try:
        if isinstance(object_id, str):
            # Проверяем, что это число в строке
            int(object_id)
        elif not isinstance(object_id, (int, str)):
            return jsonify({'error': 'Invalid object ID'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid object ID format'}), 400
    
    # Защита от XSS в object_name
    if object_name and len(object_name) > 200:
        return jsonify({'error': 'Object name too long'}), 400
    
    try:
        like = user.set_like(
            object_type=object_type,
            object_id=object_id,
            reaction=reaction,
            object_name=object_name,
            object_type_detail=object_type_detail
        )
        
        # Получаем обновлённые счётчики
        likes_count = UserLike.query.filter_by(
            object_type=object_type,
            object_id=object_id,
            reaction='like'
        ).count()
        
        dislikes_count = UserLike.query.filter_by(
            object_type=object_type,
            object_id=object_id,
            reaction='dislike'
        ).count()
        
        return jsonify({
            'status': 'success',
            'like': like.to_dict() if like else None,
            'counts': {
                'likes': likes_count,
                'dislikes': dislikes_count
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/like/remove', methods=['POST'])
@login_required
def api_remove_like():
    """API для удаления реакции"""
    user = get_current_user()
    data = request.json
    
    object_type = data.get('object_type')
    object_id = data.get('object_id')
    
    if not all([object_type, object_id]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    try:
        removed = user.remove_like(object_type, object_id)
        
        if removed:
            return jsonify({'status': 'success', 'message': 'Reaction removed'})
        else:
            return jsonify({'status': 'error', 'message': 'Reaction not found'}), 404
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/like/stats/<object_type>/<object_id>')
@login_required
def api_like_stats(object_type, object_id):
    """API для получения статистики лайков"""
    try:
        likes_count = UserLike.query.filter_by(
            object_type=object_type,
            object_id=object_id,
            reaction='like'
        ).count()
        
        dislikes_count = UserLike.query.filter_by(
            object_type=object_type,
            object_id=object_id,
            reaction='dislike'
        ).count()
        
        user = get_current_user()
        user_reaction = 'neutral'
        if user:
            like = user.get_like_for_object(object_type, object_id)
            if like:
                user_reaction = like.reaction
        
        return jsonify({
            'likes': likes_count,
            'dislikes': dislikes_count,
            'user_reaction': user_reaction,
            'total': likes_count + dislikes_count
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/likes')
@login_required
def api_user_likes():
    """API для получения всех лайков текущего пользователя"""
    user = get_current_user()
    
    try:
        likes = user.get_likes()
        likes_data = [like.to_dict() for like in likes]
        
        # Группируем по типу объекта
        grouped = {
            'places': [],
            'home_activities': []
        }
        
        for like in likes_data:
            if like['object_type'] == 'place':
                grouped['places'].append(like)
            elif like['object_type'] == 'home_activity':
                grouped['home_activities'].append(like)
        
        return jsonify({
            'total': len(likes_data),
            'grouped': grouped,
            'all': likes_data
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/<int:user_id>/likes')
@login_required
def api_user_public_likes(user_id):
    """API для получения публичных лайков другого пользователя"""
    current_user = get_current_user()
    target_user = User.query.get_or_404(user_id)
    
    # Проверяем настройки приватности
    settings = target_user.settings
    if not settings or not settings.show_likes:
        return jsonify({
            'error': 'Пользователь не показывает свои предпочтения',
            'show_likes': False
        }), 403
    
    try:
        likes = target_user.get_likes()
        likes_data = [like.to_dict() for like in likes]
        
        # Группируем по типу объекта
        grouped = {
            'places': [],
            'home_activities': []
        }
        
        for like in likes_data:
            if like['object_type'] == 'place':
                grouped['places'].append(like)
            elif like['object_type'] == 'home_activity':
                grouped['home_activities'].append(like)
        
        return jsonify({
            'total': len(likes_data),
            'grouped': grouped,
            'all': likes_data,
            'show_likes': True,
            'username': target_user.username
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ===================== ЗАПУСК =====================
if __name__ == '__main__':
    print('=' * 60)
    print('Запуск Routsol Web Server')
    print('База данных: PostgreSQL')
    print('=' * 60)
    app.run(debug=True, host='0.0.0.0', port=5000)
