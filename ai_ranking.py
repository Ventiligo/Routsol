"""
Модуль для ранжирования мест на основе психологического профиля
Использует эвристический алгоритм (rule-based система)
"""

_WEATHER_CATS = {
    0: 'clear', 1: 'clear', 2: 'cloudy', 3: 'cloudy',
    45: 'fog', 48: 'fog',
    51: 'rain', 53: 'rain', 55: 'rain',
    61: 'rain', 63: 'rain', 65: 'rain',
    71: 'snow', 73: 'snow', 75: 'snow',
    80: 'rain', 81: 'storm', 82: 'storm',
    95: 'storm', 96: 'storm', 99: 'storm',
}

def _weather_category(code):
    if code is None:
        return None
    return _WEATHER_CATS.get(int(code), 'cloudy')

def get_user_likes_dict(user):
    """
    Получает словарь лайков пользователя для использования в рекомендациях
    
    Args:
        user: User - объект пользователя
    
    Returns:
        dict: {
            'places': {'place_id': 'like/dislike'},
            'place_types': {'cafe': count_likes, 'park': count_likes},
            'home_activities': {'activity_id': 'like/dislike'}
        }
    """
    from models import UserLike
    
    likes_dict = {
        'places': {},
        'place_types': {},
        'home_activities': {}
    }
    
    if not user:
        return likes_dict
    
    # Получаем все лайки пользователя
    user_likes = UserLike.query.filter_by(user_id=user.id).all()
    
    for like in user_likes:
        if like.object_type == 'place':
            likes_dict['places'][like.object_id] = like.reaction
            
            # Считаем лайки по типу места
            if like.object_type_detail and like.reaction == 'like':
                if like.object_type_detail not in likes_dict['place_types']:
                    likes_dict['place_types'][like.object_type_detail] = 0
                likes_dict['place_types'][like.object_type_detail] += 1
        
        elif like.object_type == 'home_activity':
            likes_dict['home_activities'][like.object_id] = like.reaction
    
    return likes_dict

def calculate_place_score(profile, state, place, user_age=None):
    """
    Вычисляет оценку соответствия места психологическому профилю и состоянию.
    Учитывает возраст пользователя и ограничения из профиля.
    """
    score = 50.0

    # ── Усталость ──────────────────────────────────────────────────────────────
    if state.fatigue_level == 'high':
        if place.atmosphere in ['quiet', 'relaxing']:
            score += 20
        if place.activity_level == 'passive':
            score += 15
        if place.atmosphere in ['noisy', 'energetic']:
            score -= 20
    elif state.fatigue_level == 'low':
        if place.activity_level == 'active':
            score += 15
        if place.atmosphere == 'energetic':
            score += 10

    # ── Экстраверсия ───────────────────────────────────────────────────────────
    if profile.extraversion >= 11:
        if place.capacity in ['medium', 'large']:
            score += 10
        if place.place_type in ['bar', 'cafe', 'restaurant']:
            score += 5
    elif profile.extraversion <= 6:
        if place.capacity == 'small':
            score += 10
        if place.atmosphere == 'quiet':
            score += 10
        if place.place_type == 'park':
            score += 5

    # ── Поиск ощущений ─────────────────────────────────────────────────────────
    if profile.sensation_seeking >= 11:
        if place.activity_level == 'active':
            score += 15
        if place.place_type in ['gym', 'shopping']:
            score += 5

    # ── Невротизм ──────────────────────────────────────────────────────────────
    if profile.neuroticism >= 11:
        if place.atmosphere in ['quiet', 'relaxing']:
            score += 15
        if place.atmosphere == 'noisy':
            score -= 15

    # ── Открытость ─────────────────────────────────────────────────────────────
    if profile.openness >= 11:
        if place.place_type in ['museum', 'cinema']:
            score += 10

    # ── Компания ───────────────────────────────────────────────────────────────
    if state.with_company == 'alone':
        if place.capacity == 'small':
            score += 5
        if place.atmosphere == 'quiet':
            score += 5
    elif state.with_company in ['friends', 'family']:
        if place.capacity in ['medium', 'large']:
            score += 10

    # ── Настроение → места ─────────────────────────────────────────────────────
    mood = getattr(state, 'mood', None)
    if mood == 'sad':
        # Грусть — уютные тихие места, кафе
        if place.place_type in ('cafe', 'park'):
            score += 12
        if place.atmosphere in ('quiet', 'relaxing'):
            score += 8
        if place.atmosphere == 'noisy':
            score -= 10
    elif mood == 'angry':
        # Злость — физическая активность помогает
        if place.place_type == 'gym':
            score += 18
        if place.activity_level == 'active':
            score += 12
        if place.atmosphere == 'noisy':
            score -= 8
    elif mood == 'anxious':
        # Тревога — спокойные места
        if place.atmosphere in ('quiet', 'relaxing'):
            score += 15
        if place.place_type == 'park':
            score += 10
        if place.atmosphere in ('noisy', 'energetic'):
            score -= 15
    elif mood == 'bored':
        # Скука — что-то новое и активное
        if place.place_type in ('cinema', 'museum', 'shopping'):
            score += 12
        if place.activity_level in ('active', 'moderate'):
            score += 8
    elif mood == 'excited':
        # Воодушевление — активные места
        if place.activity_level == 'active':
            score += 12
        if place.place_type in ('bar', 'gym', 'shopping'):
            score += 8
    elif mood == 'happy':
        # Радость — любые социальные места
        if place.place_type in ('cafe', 'restaurant', 'bar', 'park'):
            score += 8

    # ── Расстояние ─────────────────────────────────────────────────────────────
    if place.distance < 500:
        score += 10
    elif place.distance < 1000:
        score += 5
    elif place.distance > 2000:
        score -= 5

    # ── Погода ─────────────────────────────────────────────────────────────────
    weather_cat = _weather_category(getattr(state, 'weather_code', None))
    if weather_cat in ('rain', 'storm', 'snow'):
        # Плохая погода — закрытые места лучше
        if place.place_type in ('cafe', 'cinema', 'museum', 'shopping', 'restaurant'):
            score += 15
        if place.place_type in ('park', 'gym'):
            score -= 10
    elif weather_cat == 'clear':
        # Хорошая погода — парки и прогулки
        if place.place_type == 'park':
            score += 12
        if place.place_type in ('cafe', 'restaurant'):
            score += 5

    # ── Время суток ────────────────────────────────────────────────────────────
    tod = getattr(state, 'time_of_day', None)
    if tod == 'night':
        if place.place_type in ('park',):
            score -= 15
        if place.place_type in ('bar', 'cafe'):
            score += 8
    elif tod == 'morning':
        if place.place_type == 'cafe':
            score += 8
        if place.place_type == 'bar':
            score -= 10
    elif tod == 'evening':
        if place.place_type in ('bar', 'cinema', 'restaurant'):
            score += 8

    # ── Бюджет ─────────────────────────────────────────────────────────────────
    if getattr(profile, 'low_budget', False):
        if place.avg_price == 'low':
            score += 15
        elif place.avg_price == 'medium':
            score += 5

    # ── Возраст ────────────────────────────────────────────────────────────────
    if user_age:
        if user_age < 18:
            # Молодёжи больше подходят парки, кино, кафе
            if place.place_type in ['park', 'cinema', 'cafe']:
                score += 8
        elif user_age >= 60:
            # Пожилым — спокойные места, парки, музеи
            if place.place_type in ['park', 'museum', 'cafe']:
                score += 8
            if place.activity_level == 'passive':
                score += 10
            if place.activity_level == 'active':
                score -= 10

    score = max(0, min(100, score))
    return score


def rank_places(profile, state, places, user_age=None, user_likes=None):
    """
    Ранжирует список мест по соответствию профилю, состоянию, возрасту и ограничениям.
    Места, запрещённые по возрасту или ограничениям, исключаются полностью.
    Учитывает лайки/дизлайки пользователя (пользовательские предпочтения).
    
    Args:
        profile: PsychologicalProfile
        state: UserState
        places: list of Place
        user_age: int (optional)
        user_likes: dict вида {'place_type': {'place_name': 'like/dislike'}} (optional)
    """
    # Типы мест, запрещённые для несовершеннолетних (до 18)
    ADULT_ONLY_TYPES = {'bar'}
    # Типы мест, не подходящие при физических ограничениях
    PHYSICAL_TYPES = {'gym'}
    # Типы мест с высокими ценами
    EXPENSIVE_TYPES = {'restaurant', 'gym', 'shopping'}

    result = []
    for place in places:
        # Фильтр по возрасту
        if user_age and user_age < 18 and place.place_type in ADULT_ONLY_TYPES:
            continue
        # Фильтр по физическим ограничениям
        if getattr(profile, 'physical_limits', False) and place.place_type in PHYSICAL_TYPES:
            continue
        # Фильтр по бюджету — исключаем дорогие места
        if getattr(profile, 'low_budget', False) and place.avg_price == 'high':
            continue
        # Фильтр по алкоголю
        if getattr(profile, 'no_alcohol', False) and place.place_type == 'bar':
            continue

        place.match_score = calculate_place_score(profile, state, place, user_age=user_age)
        
        # ── УЧЁТ ЛАЙКОВ/ДИЗЛАЙКОВ ─────────────────────────────────────────────
        if user_likes:
            # Проверяем, есть ли реакция на это конкретное место
            place_key = str(place.id)
            if place_key in user_likes.get('places', {}):
                reaction = user_likes['places'][place_key]
                if reaction == 'dislike':
                    # Если пользователь дизлайкнул это место, сильно понижаем рейтинг
                    place.match_score -= 30
                elif reaction == 'like':
                    # Если пользователь лайкнул, немного повышаем рейтинг (предпочтение)
                    place.match_score += 5
            
            # Учитываем предпочтения по типу места
            place_type_likes = user_likes.get('place_types', {}).get(place.place_type, 0)
            # Если пользователь часто лайкает места этого типа, добавляем баллы
            if place_type_likes > 0:
                place.match_score += min(place_type_likes * 2, 10)  # максимум +10
        
        result.append(place)

    result.sort(key=lambda p: p.match_score or 0, reverse=True)
    return result


def get_recommendation_explanation(profile, state, place):
    """
    Генерирует текстовое объяснение, почему место рекомендовано
    
    Args:
        profile: PsychologicalProfile
        state: UserState
        place: Place
    
    Returns:
        str: объяснение рекомендации
    """
    reasons = []
    
    # Анализируем факторы
    if state.fatigue_level == 'high' and place.atmosphere in ['quiet', 'relaxing']:
        reasons.append("спокойная атмосфера подходит для отдыха")
    
    if profile.extraversion >= 11 and place.capacity in ['medium', 'large']:
        reasons.append("подходит для общения")
    
    if profile.extraversion <= 6 and place.atmosphere == 'quiet':
        reasons.append("тихое место для уединения")
    
    if profile.sensation_seeking >= 11 and place.activity_level == 'active':
        reasons.append("активный отдых для любителей ощущений")
    
    if profile.neuroticism >= 11 and place.atmosphere == 'quiet':
        reasons.append("спокойная обстановка для расслабления")
    
    if place.distance < 500:
        reasons.append("очень близко к вам")
    
    if not reasons:
        reasons.append("соответствует вашим предпочтениям")
    
    return "Рекомендуем, потому что: " + ", ".join(reasons)


# Пример использования для будущей интеграции с нейросетью
def prepare_features_for_ml(profile, state, place):
    """
    Подготавливает признаки для машинного обучения
    
    Returns:
        dict: словарь с признаками для ML модели
    """
    # Кодируем категориальные переменные
    atmosphere_map = {'quiet': 0, 'relaxing': 1, 'neutral': 2, 'noisy': 3, 'energetic': 4}
    activity_map = {'passive': 0, 'moderate': 1, 'active': 2}
    price_map = {'low': 0, 'medium': 1, 'high': 2}
    capacity_map = {'small': 0, 'medium': 1, 'large': 2}
    fatigue_map = {'low': 0, 'medium': 1, 'high': 2}
    
    features = {
        # Профиль пользователя
        'extraversion': profile.extraversion / 15.0,  # Нормализация 0-1
        'openness': profile.openness / 15.0,
        'sensation_seeking': profile.sensation_seeking / 15.0,
        'conscientiousness': profile.conscientiousness / 15.0,
        'proactivity': profile.proactivity / 15.0,
        'neuroticism': profile.neuroticism / 15.0,
        
        # Состояние
        'fatigue': fatigue_map.get(state.fatigue_level, 1) / 2.0,
        'is_alone': 1 if state.with_company == 'alone' else 0,
        'is_with_friends': 1 if state.with_company == 'friends' else 0,
        
        # Атрибуты места
        'atmosphere': atmosphere_map.get(place.atmosphere, 2) / 4.0,
        'activity_level': activity_map.get(place.activity_level, 1) / 2.0,
        'price': price_map.get(place.avg_price, 1) / 2.0,
        'capacity': capacity_map.get(place.capacity, 1) / 2.0,
        'distance': min(place.distance / 3000.0, 1.0),  # Нормализация до 3км
        
        # Тип места (one-hot encoding)
        'is_cafe': 1 if place.place_type == 'cafe' else 0,
        'is_park': 1 if place.place_type == 'park' else 0,
        'is_gym': 1 if place.place_type == 'gym' else 0,
        'is_cinema': 1 if place.place_type == 'cinema' else 0,
        'is_museum': 1 if place.place_type == 'museum' else 0,
        'is_bar': 1 if place.place_type == 'bar' else 0,
    }
    
    return features


def get_home_activities(profile, state):
    """
    Генерирует список домашних развлечений на основе профиля и состояния.
    Возвращает топ-3 наиболее подходящих активности.

    Поле company у каждой активности:
        'alone'   — только для одного
        'any'     — подходит для любой компании
        'social'  — лучше с кем-то (друзья, семья, партнёр)
        'friends' — с друзьями
        'family'  — с семьёй
        'partner' — с партнёром

    Returns:
        list[dict]: список из 3 активностей с полями title, description, icon, score, company
    """
    candidates = [
        # ── ОДИНОЧНЫЕ ──────────────────────────────────────────────────────────
        {
            'id': 'meditation',
            'title': 'Медитация или дыхательные практики',
            'description': 'Снимет напряжение и восстановит силы за 10–20 минут.',
            'icon': '🧘',
            'company': 'alone',
            'tags': {'fatigue': ['high', 'medium'], 'mood': ['tired', 'calm', 'anxious', 'angry', 'sad'],
                     'neuroticism_high': True, 'extraversion_low': True},
        },
        {
            'id': 'book',
            'title': 'Почитать книгу',
            'description': 'Тихий вечер с хорошей книгой — идеально для восстановления.',
            'icon': '📚',
            'company': 'alone',
            'tags': {'fatigue': ['high', 'medium'], 'extraversion_low': True, 'openness_high': True,
                     'mood': ['calm', 'thoughtful', 'sad', 'bored']},
        },
        {
            'id': 'journaling',
            'title': 'Ведение дневника или планирование',
            'description': 'Запишите мысли, составьте план — это помогает структурировать день.',
            'icon': '📝',
            'company': 'alone',
            'tags': {'fatigue': ['medium', 'high'], 'conscientiousness_high': True,
                     'mood': ['thoughtful', 'calm', 'sad', 'anxious']},
        },
        {
            'id': 'bath',
            'title': 'Расслабляющая ванна',
            'description': 'Тёплая ванна с ароматическими маслами — быстрый способ снять стресс.',
            'icon': '🛁',
            'company': 'alone',
            'tags': {'fatigue': ['high'], 'neuroticism_high': True, 'mood': ['tired', 'calm', 'anxious', 'angry']},
        },
        {
            'id': 'drawing',
            'title': 'Рисование или творчество',
            'description': 'Выразите себя через рисунок, скетч или любое творчество.',
            'icon': '🎨',
            'company': 'alone',
            'tags': {'fatigue': ['medium', 'high'], 'openness_high': True,
                     'mood': ['thoughtful', 'calm', 'sad', 'bored', 'angry']},
        },
        {
            'id': 'online_learning',
            'title': 'Онлайн-курс или обучающее видео',
            'description': 'Узнайте что-то новое — от языков до программирования.',
            'icon': '💻',
            'company': 'alone',
            'tags': {'fatigue': ['low', 'medium'], 'openness_high': True,
                     'conscientiousness_high': True, 'mood': ['thoughtful', 'adventurous', 'bored', 'excited']},
        },
        {
            'id': 'home_workout',
            'title': 'Домашняя тренировка',
            'description': 'Зарядитесь энергией с коротким интенсивным комплексом упражнений.',
            'icon': '💪',
            'company': 'alone',
            'tags': {'fatigue': ['low'], 'sensation_seeking_high': True,
                     'proactivity_high': True, 'mood': ['happy', 'adventurous', 'angry', 'excited', 'bored']},
        },
        {
            'id': 'yoga',
            'title': 'Лёгкая йога или растяжка',
            'description': 'Мягкие упражнения снимут мышечное напряжение без нагрузки.',
            'icon': '🤸',
            'company': 'alone',
            'tags': {'fatigue': ['medium', 'high'], 'neuroticism_high': True,
                     'proactivity_high': True},
        },
        {
            'id': 'podcast',
            'title': 'Послушать подкаст',
            'description': 'Интересный подкаст на любимую тему — отличный фоновый отдых.',
            'icon': '🎙️',
            'company': 'alone',
            'tags': {'fatigue': ['high', 'medium'], 'openness_high': True,
                     'mood': ['calm', 'thoughtful', 'tired', 'bored', 'sad']},
        },
        {
            'id': 'photography',
            'title': 'Разобрать фотографии или создать альбом',
            'description': 'Пересмотрите воспоминания и создайте красивый фотоальбом.',
            'icon': '📷',
            'company': 'alone',
            'tags': {'fatigue': ['medium', 'high'], 'openness_high': True,
                     'conscientiousness_high': True, 'mood': ['calm', 'thoughtful', 'sad']},
        },
        {
            'id': 'declutter',
            'title': 'Навести порядок или переставить мебель',
            'description': 'Небольшая уборка или перестановка освежает пространство и голову.',
            'icon': '🧹',
            'company': 'alone',
            'tags': {'fatigue': ['low', 'medium'], 'conscientiousness_high': True,
                     'proactivity_high': True, 'mood': ['happy', 'adventurous', 'angry', 'bored']},
        },
        {
            'id': 'stretching',
            'title': 'Лёгкая прогулка по квартире или балкону',
            'description': 'Даже 10 минут движения дома улучшают самочувствие.',
            'icon': '🚶',
            'company': 'alone',
            'tags': {'fatigue': ['high', 'medium'], 'neuroticism_high': True,
                     'mood': ['tired', 'calm', 'anxious', 'sad']},
        },

        # ── С ПАРТНЁРОМ ────────────────────────────────────────────────────────
        {
            'id': 'movie_partner',
            'title': 'Посмотреть фильм вдвоём',
            'description': 'Уютный вечер с партнёром и любимым фильмом.',
            'icon': '🎬',
            'company': 'partner',
            'tags': {'fatigue': ['high', 'medium'], 'openness_high': True,
                     'mood': ['calm', 'happy', 'tired']},
        },
        {
            'id': 'cooking_partner',
            'title': 'Приготовить ужин вместе',
            'description': 'Совместная готовка — романтично и вкусно.',
            'icon': '🍝',
            'company': 'partner',
            'tags': {'fatigue': ['low', 'medium'], 'conscientiousness_high': True,
                     'mood': ['happy', 'adventurous', 'calm']},
        },
        {
            'id': 'board_game_partner',
            'title': 'Настольная игра на двоих',
            'description': 'Шахматы, карты или любая настолка — весело и без экрана.',
            'icon': '♟️',
            'company': 'partner',
            'tags': {'fatigue': ['low', 'medium'], 'sensation_seeking_high': True,
                     'mood': ['happy', 'adventurous']},
        },
        {
            'id': 'spa_partner',
            'title': 'Домашний спа-вечер',
            'description': 'Маски, ванна, свечи — устройте спа прямо дома.',
            'icon': '🕯️',
            'company': 'partner',
            'tags': {'fatigue': ['high'], 'neuroticism_high': True,
                     'mood': ['tired', 'calm']},
        },

        # ── С ДРУЗЬЯМИ ─────────────────────────────────────────────────────────
        {
            'id': 'board_games_online',
            'title': 'Онлайн-игры с друзьями',
            'description': 'Сыграйте в онлайн-настолку или кооперативную игру с компанией.',
            'icon': '🎲',
            'company': 'friends',
            'tags': {'fatigue': ['low', 'medium'], 'extraversion_high': True,
                     'sensation_seeking_high': True, 'mood': ['happy', 'adventurous']},
        },
        {
            'id': 'call_friends',
            'title': 'Видеозвонок с друзьями',
            'description': 'Живое общение поднимает настроение даже на расстоянии.',
            'icon': '📞',
            'company': 'friends',
            'tags': {'fatigue': ['medium', 'high'], 'extraversion_high': True,
                     'mood': ['happy', 'calm', 'tired']},
        },
        {
            'id': 'watch_party',
            'title': 'Watch-party — смотреть фильм вместе онлайн',
            'description': 'Синхронный просмотр с друзьями через Discord или Teleparty.',
            'icon': '🍿',
            'company': 'friends',
            'tags': {'fatigue': ['high', 'medium'], 'extraversion_high': True,
                     'openness_high': True, 'mood': ['happy', 'calm']},
        },
        {
            'id': 'quiz_friends',
            'title': 'Онлайн-викторина с друзьями',
            'description': 'Kahoot, Quizlet или своя викторина — весело и познавательно.',
            'icon': '🧠',
            'company': 'friends',
            'tags': {'fatigue': ['low', 'medium'], 'openness_high': True,
                     'extraversion_high': True, 'mood': ['happy', 'adventurous']},
        },
        {
            'id': 'cooking_friends',
            'title': 'Готовить вместе и устроить ужин',
            'description': 'Каждый готовит своё блюдо — и устраиваете общий стол.',
            'icon': '🥘',
            'company': 'friends',
            'tags': {'fatigue': ['low', 'medium'], 'extraversion_high': True,
                     'conscientiousness_high': True, 'mood': ['happy', 'adventurous']},
        },

        # ── С СЕМЬЁЙ ───────────────────────────────────────────────────────────
        {
            'id': 'family_movie',
            'title': 'Семейный киновечер',
            'description': 'Выберите фильм для всей семьи и устройтесь поудобнее.',
            'icon': '🎥',
            'company': 'family',
            'tags': {'fatigue': ['high', 'medium'], 'openness_high': True,
                     'mood': ['calm', 'happy', 'tired']},
        },
        {
            'id': 'family_cooking',
            'title': 'Готовить вместе с семьёй',
            'description': 'Совместная готовка сближает — испеките пиццу или торт.',
            'icon': '🍕',
            'company': 'family',
            'tags': {'fatigue': ['low', 'medium'], 'conscientiousness_high': True,
                     'mood': ['happy', 'calm']},
        },
        {
            'id': 'family_games',
            'title': 'Настольные игры всей семьёй',
            'description': 'Монополия, Уно, Активити — классика для любого возраста.',
            'icon': '🎯',
            'company': 'family',
            'tags': {'fatigue': ['low', 'medium'], 'extraversion_high': True,
                     'sensation_seeking_high': True, 'mood': ['happy', 'adventurous']},
        },
        {
            'id': 'family_craft',
            'title': 'Совместное творчество с семьёй',
            'description': 'Рисование, лепка, поделки — весело для детей и взрослых.',
            'icon': '✂️',
            'company': 'family',
            'tags': {'fatigue': ['medium', 'high'], 'openness_high': True,
                     'mood': ['calm', 'happy', 'thoughtful']},
        },

        # ── ЛЮБАЯ КОМПАНИЯ ─────────────────────────────────────────────────────
        {
            'id': 'music',
            'title': 'Послушать музыку',
            'description': 'Создайте плейлист под настроение — один или с компанией.',
            'icon': '🎵',
            'company': 'any',
            'tags': {'fatigue': ['high', 'medium', 'low'], 'mood': ['calm', 'happy', 'tired', 'sad', 'bored']},
        },
        {
            'id': 'cooking',
            'title': 'Приготовить что-то вкусное',
            'description': 'Кулинария — отличный способ переключиться и порадовать себя.',
            'icon': '🍳',
            'company': 'any',
            'tags': {'fatigue': ['low', 'medium'], 'conscientiousness_high': True,
                     'mood': ['happy', 'adventurous']},
        },
        {
            'id': 'games',
            'title': 'Поиграть в видеоигры',
            'description': 'Одиночные или совместные игры — хороший способ расслабиться.',
            'icon': '🎮',
            'company': 'any',
            'tags': {'fatigue': ['low', 'medium'], 'sensation_seeking_high': True,
                     'mood': ['happy', 'adventurous']},
        },
    ]

    fatigue = state.fatigue_level
    mood = state.mood
    company = state.with_company  # alone, partner, friends, family, skip, None

    # Маппинг company из состояния на поле company активности
    company_match = {
        'alone':   ['alone', 'any'],
        'partner': ['partner', 'any'],
        'friends': ['friends', 'any'],
        'family':  ['family', 'any'],
        'skip':    ['alone', 'any'],
        None:      ['alone', 'any'],
    }
    allowed_companies = company_match.get(company, ['alone', 'any'])

    # Активности, требующие физической активности — исключаем при ограничениях
    PHYSICAL_ACTIVITIES = {'home_workout', 'yoga', 'stretching'}

    scored = []
    for act in candidates:
        # Фильтр по компании
        if act['company'] not in allowed_companies:
            continue
        # Фильтр по физическим ограничениям
        if getattr(profile, 'physical_limits', False) and act['id'] in PHYSICAL_ACTIVITIES:
            continue

        score = 40.0
        tags = act['tags']

        if fatigue in tags.get('fatigue', []):
            score += 25
        if mood and mood in tags.get('mood', []):
            score += 15
        if act['company'] == company:
            score += 10  # точное совпадение компании

        # Погода: при плохой погоде домашние активности получают бонус
        weather_cat = _weather_category(getattr(state, 'weather_code', None))
        if weather_cat in ('rain', 'storm', 'snow'):
            score += 12

        if profile.neuroticism >= 11 and tags.get('neuroticism_high'):
            score += 10
        if profile.extraversion >= 11 and tags.get('extraversion_high'):
            score += 10
        if profile.extraversion <= 6 and tags.get('extraversion_low'):
            score += 10
        if profile.openness >= 11 and tags.get('openness_high'):
            score += 10
        if profile.sensation_seeking >= 11 and tags.get('sensation_seeking_high'):
            score += 10
        if profile.conscientiousness >= 11 and tags.get('conscientiousness_high'):
            score += 10
        if profile.proactivity >= 11 and tags.get('proactivity_high'):
            score += 10

        scored.append({**act, 'score': min(100, score)})

    scored.sort(key=lambda x: x['score'], reverse=True)
    return scored[:3]


# Заглушка для будущей нейросети
def neural_network_rank(profile, state, places):
    """
    Будущая функция для ранжирования через нейросеть
    
    Можно использовать:
    - TensorFlow/Keras для обучения модели
    - PyTorch для deep learning
    - Scikit-learn для простых ML моделей
    
    Модель будет обучаться на данных:
    - Психологический профиль
    - Состояние пользователя
    - Атрибуты мест
    - Обратная связь (какие места пользователь выбрал)
    """
    # TODO: Загрузить обученную модель
    # model = load_model('routsol_ranking_model.h5')
    
    # TODO: Подготовить признаки
    # features = [prepare_features_for_ml(profile, state, place) for place in places]
    
    # TODO: Получить предсказания
    # predictions = model.predict(features)
    
    # Пока используем эвристическое ранжирование
    return rank_places(profile, state, places)
