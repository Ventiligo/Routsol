# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import json
import secrets
import hashlib
import time

db = SQLAlchemy()

class User(db.Model):
    """Основная таблица пользователей"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.BigInteger, unique=True, nullable=True)

    # Авторизация
    username = db.Column(db.String(80), unique=True, nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(256), nullable=True)
    password_salt = db.Column(db.String(32), nullable=True)  # Соль для пароля
    
    # Демографические данные
    age = db.Column(db.Integer, nullable=True)
    gender = db.Column(db.String(20), nullable=True)  # male, female, other, unspecified
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    psychological_profile = db.relationship('PsychologicalProfile', backref='user', uselist=False)
    answers = db.relationship('UserAnswer', backref='user', lazy='dynamic')
    states = db.relationship('UserState', backref='user', lazy='dynamic', order_by='UserState.created_at.desc()')
    
    def set_password(self, password):
        """Безопасное хеширование пароля с солью"""
        # Проверка сложности пароля
        if len(password) < 8:
            raise ValueError("Пароль должен быть не менее 8 символов")
        
        # Генерация соли
        salt = secrets.token_hex(16)
        # Хеширование пароля с солью
        password_with_salt = password + salt
        self.password_hash = generate_password_hash(password_with_salt)
        self.password_salt = salt  # Нужно добавить поле в модель

    def check_password(self, password):
        """Проверка пароля с защитой от timing attack"""
        if not self.password_hash or not self.password_salt:
            return False
        
        # Постоянное время выполнения для защиты от timing attack
        start_time = time.time()
        
        # Восстанавливаем оригинальный пароль с солью
        password_with_salt = password + self.password_salt
        result = check_password_hash(self.password_hash, password_with_salt)
        
        # Искусственная задержка для постоянного времени выполнения
        elapsed = time.time() - start_time
        if elapsed < 0.1:  # 100ms минимальное время
            time.sleep(0.1 - elapsed)
        
        return result

    def __repr__(self):
        return f'<User {self.id} {self.username}>'
    
    def get_latest_state(self):
        """Получает последнее состояние пользователя"""
        return self.states.first()

    def get_friends(self):
        """Возвращает список друзей"""
        sent = FriendRequest.query.filter_by(sender_id=self.id, status='accepted').all()
        received = FriendRequest.query.filter_by(receiver_id=self.id, status='accepted').all()
        friend_ids = [r.receiver_id for r in sent] + [r.sender_id for r in received]
        return User.query.filter(User.id.in_(friend_ids)).all()

    def is_friend_with(self, other_user_id):
        return FriendRequest.query.filter(
            ((FriendRequest.sender_id == self.id) & (FriendRequest.receiver_id == other_user_id) |
             (FriendRequest.sender_id == other_user_id) & (FriendRequest.receiver_id == self.id)),
            FriendRequest.status == 'accepted'
        ).first() is not None

    def friend_request_status(self, other_user_id):
        req = FriendRequest.query.filter(
            ((FriendRequest.sender_id == self.id) & (FriendRequest.receiver_id == other_user_id)) |
            ((FriendRequest.sender_id == other_user_id) & (FriendRequest.receiver_id == self.id))
        ).first()
        if not req:
            return None
        return req
    
    def get_likes(self):
        """Возвращает все лайки пользователя"""
        return UserLike.query.filter_by(user_id=self.id).all()
    
    def get_likes_by_type(self, object_type):
        """Возвращает лайки пользователя по типу объекта"""
        return UserLike.query.filter_by(user_id=self.id, object_type=object_type).all()
    
    def get_like_for_object(self, object_type, object_id):
        """Возвращает реакцию пользователя на конкретный объект"""
        return UserLike.query.filter_by(
            user_id=self.id, 
            object_type=object_type, 
            object_id=object_id
        ).first()
    
    def set_like(self, object_type, object_id, reaction, object_name=None, object_type_detail=None):
        """Устанавливает реакцию на объект (upsert). Если reaction='neutral', удаляет запись."""
        from sqlalchemy.exc import IntegrityError
        
        like = self.get_like_for_object(object_type, object_id)
        
        if like:
            if reaction == 'neutral':
                # Удаляем запись при нейтральной реакции
                db.session.delete(like)
                db.session.commit()
                return None
            # Обновляем существующую реакцию
            like.reaction = reaction
            like.object_name = object_name or like.object_name
            like.object_type_detail = object_type_detail or like.object_type_detail
            db.session.commit()
            return like
        
        # Если реакция neutral и записи нет - ничего не делаем
        if reaction == 'neutral':
            return None
        
        # Пытаемся создать новую реакцию
        like = UserLike(
            user_id=self.id,
            object_type=object_type,
            object_id=object_id,
            reaction=reaction,
            object_name=object_name,
            object_type_detail=object_type_detail
        )
        db.session.add(like)
        
        try:
            db.session.commit()
            return like
        except IntegrityError:
            # Если запись уже существует (race condition), откатываем и получаем её
            db.session.rollback()
            like = self.get_like_for_object(object_type, object_id)
            if like:
                if reaction == 'neutral':
                    db.session.delete(like)
                    db.session.commit()
                    return None
                like.reaction = reaction
                like.object_name = object_name or like.object_name
                like.object_type_detail = object_type_detail or like.object_type_detail
                db.session.commit()
            return like
    
    def remove_like(self, object_type, object_id):
        """Удаляет реакцию на объект"""
        like = self.get_like_for_object(object_type, object_id)
        if like:
            db.session.delete(like)
            db.session.commit()
            return True
        return False


# ============= НОВЫЙ КЛАСС: UserState =============
class UserState(db.Model):
    """Текущее состояние пользователя (усталость, настроение)"""
    __tablename__ = 'user_states'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Уровень усталости (1-10 или текстом)
    fatigue_level = db.Column(db.String(20), nullable=False)  # 'high', 'medium', 'low' или текстом
    fatigue_value = db.Column(db.Integer, nullable=True)  # числовое значение 1-10
    
    # Координаты пользователя
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    address = db.Column(db.String(500), nullable=True)
    
    # Дополнительный контекст
    mood = db.Column(db.String(50), nullable=True)
    time_of_day = db.Column(db.String(20), nullable=True)  # morning, afternoon, evening, night
    with_company = db.Column(db.String(50), nullable=True)

    # Погода
    weather_temp = db.Column(db.Float, nullable=True)        # температура °C
    weather_code = db.Column(db.Integer, nullable=True)      # WMO weather code
    weather_desc = db.Column(db.String(100), nullable=True)  # текстовое описание
    weather_icon = db.Column(db.String(10), nullable=True)   # эмодзи иконка
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Связь с найденными местами
    places = db.relationship('Place', backref='user_state', lazy='dynamic')
    
    def __repr__(self):
        return f'<State user={self.user_id} fatigue={self.fatigue_level}>'
    
    def to_dict(self):
        return {
            'fatigue_level': self.fatigue_level,
            'fatigue_value': self.fatigue_value,
            'mood': self.mood,
            'time_of_day': self.time_of_day,
            'with_company': self.with_company,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'address': self.address,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class PsychologicalProfile(db.Model):
    """Психологический профиль пользователя (баллы по шкалам)"""
    __tablename__ = 'psychological_profiles'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    
    # Баллы по шкалам (3-15)
    extraversion = db.Column(db.Integer, nullable=True)
    openness = db.Column(db.Integer, nullable=True)
    sensation_seeking = db.Column(db.Integer, nullable=True)
    conscientiousness = db.Column(db.Integer, nullable=True)
    proactivity = db.Column(db.Integer, nullable=True)
    neuroticism = db.Column(db.Integer, nullable=True)

    # Ограничения (булевы флаги, выводятся из ответов на вопросы)
    no_alcohol = db.Column(db.Boolean, default=False)       # не употребляет алкоголь
    low_budget = db.Column(db.Boolean, default=False)       # ограниченный бюджет
    physical_limits = db.Column(db.Boolean, default=False)  # физические ограничения

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'extraversion': self.extraversion,
            'openness': self.openness,
            'sensation_seeking': self.sensation_seeking,
            'conscientiousness': self.conscientiousness,
            'proactivity': self.proactivity,
            'neuroticism': self.neuroticism,
            'no_alcohol': self.no_alcohol,
            'low_budget': self.low_budget,
            'physical_limits': self.physical_limits,
        }
    
    def get_level(self, scale_name):
        score = getattr(self, scale_name)
        if not score:
            return None
        if score >= 11:
            return 'high'
        elif score >= 7:
            return 'medium'
        else:
            return 'low'
    
    def __repr__(self):
        return f'<Profile user={self.user_id}>'


class UserAnswer(db.Model):
    """Сырые ответы пользователя на вопросы (в JSON)"""
    __tablename__ = 'user_answers'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # JSON поле со всеми ответами
    answers_data = db.Column(db.JSON, nullable=False)
    
    # Метаданные
    session_id = db.Column(db.String(100), nullable=True)
    completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def get_answer_for_question(self, question_id):
        return self.answers_data.get(str(question_id))
    
    def __repr__(self):
        return f'<Answer user={self.user_id} completed={self.completed}>'


class Question(db.Model):
    """Вопросы анкеты (загружаются из JSON)"""
    __tablename__ = 'questions'
    
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, unique=True, nullable=False)
    text = db.Column(db.String(500), nullable=False)
    scale = db.Column(db.String(50), nullable=False)  # extraversion, openness, etc.
    order = db.Column(db.Integer, nullable=False)
    
    # Варианты ответов хранятся как JSON
    options = db.Column(db.JSON, nullable=False, default={
        "1": "Совершенно не про меня",
        "2": "Скорее не про меня",
        "3": "Нейтрально / иногда бывает",
        "4": "Скорее про меня",
        "5": "Полностью про меня"
    })
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Q{self.question_id}: {self.scale}>'


# Функция для инициализации вопросов
def init_questions():
    """Заполняет таблицу вопросов из заранее определённого списка"""
    questions_data = [
        # Экстраверсия (3 вопроса)
        {"id": 1, "text": "Я люблю вечерами встречаться с друзьями в шумных местах.", "scale": "extraversion", "order": 1},
        {"id": 2, "text": "Предпочитаю провести выходной в компании, а не один.", "scale": "extraversion", "order": 2},
        {"id": 3, "text": "Когда устал, мне нужно живое общение, чтобы зарядиться.", "scale": "extraversion", "order": 3},
        
        # Открытость опыту (3 вопроса)
        {"id": 4, "text": "Хочу попробовать новое кафе с необычной кухней, даже если отзывы смешанные.", "scale": "openness", "order": 4},
        {"id": 5, "text": "В парке интереснее исследовать неизведанные тропинки, чем ходить по главной аллее.", "scale": "openness", "order": 5},
        {"id": 6, "text": "Готов выбрать фильм по рекомендации, даже если жанр незнаком.", "scale": "openness", "order": 6},
        
        # Поиск ощущений (3 вопроса)
        {"id": 7, "text": "Ищу места с адреналином: квесты, веревочные парки или ночные прогулки.", "scale": "sensation_seeking", "order": 7},
        {"id": 8, "text": "На предложение экстремальной активности (скалолазание, картинг) соглашусь без раздумий.", "scale": "sensation_seeking", "order": 8},
        {"id": 9, "text": "Скучно повторять одни и те же кафе — тянет в новое и необычное.", "scale": "sensation_seeking", "order": 9},
        
        # Сознательность (3 вопроса)
        {"id": 10, "text": "Люблю заранее спланировать вечер: куда пойти, что заказать.", "scale": "conscientiousness", "order": 10},
        {"id": 11, "text": "Выбираю активности по расписанию, чтобы не тратить время зря.", "scale": "conscientiousness", "order": 11},
        {"id": 12, "text": "В усталости предпочитаю тихий парк с известными маршрутами.", "scale": "conscientiousness", "order": 12},
        
        # Проактивность (2 вопроса)
        {"id": 13, "text": "Сам организую поход в новое место, а не жду приглашения.", "scale": "proactivity", "order": 13},
        {"id": 14, "text": "Если идея отдыха интересна, беру инициативу и собираю компанию.", "scale": "proactivity", "order": 14},
        
        # Невротизм (потребность в покое) (3 вопроса)
        {"id": 15, "text": "Предпочитаю спокойные места без толпы, чтобы расслабиться.", "scale": "neuroticism", "order": 15},
        {"id": 16, "text": "После тяжелого дня нужен тихий ужин дома или в уютном кафе без шума.", "scale": "neuroticism", "order": 16},
        {"id": 17, "text": "Избегаю шумных вечеринок, когда чувствую усталость.", "scale": "neuroticism", "order": 17},
        
        # Дополнительный вопрос (поиск ощущений)
        {"id": 18, "text": "В настроении для приключений беру такси и еду в случайное место.", "scale": "sensation_seeking", "order": 18},

        # Ограничения (3 вопроса — ответ 1=нет, 5=да)
        {
            "id": 19,
            "text": "Я не употребляю алкоголь (по любой причине: здоровье, убеждения, возраст).",
            "scale": "restrictions",
            "order": 19,
            "options": {"1": "Нет, алкоголь не исключаю", "2": "Скорее нет", "3": "Иногда", "4": "Скорее да", "5": "Да, не употребляю"}
        },
        {
            "id": 20,
            "text": "У меня есть физические ограничения, которые затрудняют активный отдых (травмы, хронические заболевания и т.п.).",
            "scale": "restrictions",
            "order": 20,
            "options": {"1": "Нет ограничений", "2": "Скорее нет", "3": "Незначительные", "4": "Скорее да", "5": "Да, есть ограничения"}
        },
        {
            "id": 21,
            "text": "Мой бюджет на отдых ограничен — предпочитаю бесплатные или недорогие варианты.",
            "scale": "restrictions",
            "order": 21,
            "options": {"1": "Бюджет не ограничен", "2": "Скорее нет", "3": "Умеренно", "4": "Скорее да", "5": "Да, только бесплатное/дешёвое"}
        },
    ]
    
    for q_data in questions_data:
        existing = Question.query.filter_by(question_id=q_data["id"]).first()
        if not existing:
            question = Question(
                question_id=q_data["id"],
                text=q_data["text"],
                scale=q_data["scale"],
                order=q_data["order"],
                options=q_data.get("options", {
                    "1": "Совершенно не про меня",
                    "2": "Скорее не про меня",
                    "3": "Нейтрально / иногда бывает",
                    "4": "Скорее про меня",
                    "5": "Полностью про меня"
                })
            )
            db.session.add(question)
    
    db.session.commit()
    print("✅ Вопросы инициализированы")


# ============= НОВЫЙ КЛАСС: Place =============
class Place(db.Model):
    """Места для отдыха с атрибутами для психологического ранжирования"""
    __tablename__ = 'places'
    
    id = db.Column(db.Integer, primary_key=True)
    state_id = db.Column(db.Integer, db.ForeignKey('user_states.id'), nullable=False)
    
    # Основная информация
    name = db.Column(db.String(300), nullable=False)
    place_type = db.Column(db.String(100), nullable=False)  # cafe, park, gym, cinema, etc.
    address = db.Column(db.String(500), nullable=True)
    
    # Координаты
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    distance = db.Column(db.Float, nullable=True)  # расстояние от пользователя в метрах
    
    # Атрибуты для психологического ранжирования
    avg_price = db.Column(db.String(50), nullable=True)  # low, medium, high
    atmosphere = db.Column(db.String(100), nullable=True)  # quiet, noisy, relaxing, energetic
    capacity = db.Column(db.String(50), nullable=True)  # small, medium, large (для компании)
    activity_level = db.Column(db.String(50), nullable=True)  # passive, moderate, active
    
    # Дополнительные данные
    rating = db.Column(db.Float, nullable=True)
    reviews_count = db.Column(db.Integer, nullable=True)
    description = db.Column(db.Text, nullable=True)
    tags = db.Column(db.JSON, nullable=True)  # массив тегов
    
    # Данные из API
    api_source = db.Column(db.String(50), nullable=True)  # 2gis, yandex
    api_id = db.Column(db.String(200), nullable=True)
    api_data = db.Column(db.JSON, nullable=True)  # полные данные из API
    
    # Ранжирование
    match_score = db.Column(db.Float, nullable=True)  # оценка соответствия профилю (0-100)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Place {self.name} ({self.place_type})>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'type': self.place_type,
            'address': self.address,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'distance': self.distance,
            'avg_price': self.avg_price,
            'atmosphere': self.atmosphere,
            'capacity': self.capacity,
            'activity_level': self.activity_level,
            'rating': self.rating,
            'reviews_count': self.reviews_count,
            'description': self.description,
            'tags': self.tags,
            'match_score': self.match_score
        }
    
    def get_likes_count(self):
        """Возвращает количество лайков для этого места"""
        return UserLike.query.filter_by(
            object_type='place', 
            object_id=str(self.id),
            reaction='like'
        ).count()
    
    def get_dislikes_count(self):
        """Возвращает количество дизлайков для этого места"""
        return UserLike.query.filter_by(
            object_type='place', 
            object_id=str(self.id),
            reaction='dislike'
        ).count()
    
    def get_user_reaction(self, user_id):
        """Возвращает реакцию конкретного пользователя на это место"""
        like = UserLike.query.filter_by(
            user_id=user_id,
            object_type='place',
            object_id=str(self.id)
        ).first()
        return like.reaction if like else 'neutral'



class FriendRequest(db.Model):
    """Запросы в друзья между пользователями"""
    __tablename__ = 'friend_requests'

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, accepted, declined
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_requests')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_requests')

    def __repr__(self):
        return f'<FriendRequest {self.sender_id}->{self.receiver_id} [{self.status}]>'


class ActivityInvite(db.Model):
    """Приглашение другу на активность"""
    __tablename__ = 'activity_invites'

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Тип: 'place' или 'home_activity'
    activity_type = db.Column(db.String(20), nullable=False)
    activity_id = db.Column(db.String(200), nullable=True)   # id места или home activity
    activity_name = db.Column(db.String(300), nullable=False)
    activity_description = db.Column(db.Text, nullable=True)
    activity_icon = db.Column(db.String(50), nullable=True)

    message = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending')  # pending, accepted, declined
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_invites')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_invites')

    def __repr__(self):
        return f'<ActivityInvite {self.sender_id}->{self.receiver_id} [{self.activity_name}]>'


class Meeting(db.Model):
    """Запланированная встреча между пользователями"""
    __tablename__ = 'meetings'

    id = db.Column(db.Integer, primary_key=True)
    organizer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(500), nullable=True)
    scheduled_at = db.Column(db.DateTime, nullable=False)
    activity_type = db.Column(db.String(50), nullable=True)
    activity_icon = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), default='planned')  # planned, cancelled, done
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organizer = db.relationship('User', foreign_keys=[organizer_id], backref='organized_meetings')
    participants = db.relationship('MeetingParticipant', backref='meeting', lazy='dynamic')

    def __repr__(self):
        return f'<Meeting {self.title} at {self.scheduled_at}>'


class MeetingParticipant(db.Model):
    """Участники встречи"""
    __tablename__ = 'meeting_participants'

    id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey('meetings.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), default='invited')  # invited, accepted, declined
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='meeting_participations')


class UserSettings(db.Model):
    """Настройки и приватность пользователя"""
    __tablename__ = 'user_settings'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)

    # Приватность
    show_age            = db.Column(db.Boolean, default=True)   # показывать возраст
    show_email          = db.Column(db.Boolean, default=False)  # показывать email
    show_gender         = db.Column(db.Boolean, default=True)   # показывать пол
    show_profile_scores = db.Column(db.Boolean, default=True)   # показывать шкалы анкеты
    show_restrictions   = db.Column(db.Boolean, default=False)  # показывать ограничения
    allow_friend_requests = db.Column(db.Boolean, default=True) # разрешить запросы в друзья
    
    # Лайки и предпочтения
    show_likes = db.Column(db.Boolean, default=False)  # показывать лайки/дизлайки другим пользователям

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('settings', uselist=False))

    def __repr__(self):
        return f'<UserSettings user={self.user_id}>'
class UserLike(db.Model):
    """Лайки и дизлайки пользователей"""
    __tablename__ = 'user_likes'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Тип объекта: 'place' (место) или 'home_activity' (домашняя активность)
    object_type = db.Column(db.String(20), nullable=False)
    
    # ID объекта (места или домашней активности)
    object_id = db.Column(db.String(200), nullable=False)
    
    # Тип реакции: 'like' (лайк), 'dislike' (дизлайк), 'neutral' (нейтрально)
    reaction = db.Column(db.String(20), nullable=False, default='neutral')
    
    # Дополнительные данные
    object_name = db.Column(db.String(300), nullable=True)  # Название места/активности
    object_type_detail = db.Column(db.String(100), nullable=True)  # Тип места (cafe, park и т.д.)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Уникальный индекс: один пользователь может иметь только одну реакцию на объект
    __table_args__ = (
        db.UniqueConstraint('user_id', 'object_type', 'object_id', name='unique_user_object_reaction'),
    )
    
    user = db.relationship('User', backref='likes')
    
    def __repr__(self):
        return f'<UserLike user={self.user_id} {self.object_type}:{self.object_id} [{self.reaction}]>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'object_type': self.object_type,
            'object_id': self.object_id,
            'reaction': self.reaction,
            'object_name': self.object_name,
            'object_type_detail': self.object_type_detail,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }