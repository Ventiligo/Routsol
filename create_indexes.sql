-- Индексы для оптимизации производительности Routsol Web
-- Запустите этот файл после создания таблиц для улучшения производительности

-- ===== USERS =====
-- Индекс для быстрого поиска по username (используется при логине)
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- Индекс для поиска по email
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Индекс для поиска по telegram_id (если используется Telegram-бот)
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);

-- ===== USER_STATES =====
-- Индекс для быстрого получения последнего состояния пользователя
CREATE INDEX IF NOT EXISTS idx_user_states_user_created ON user_states(user_id, created_at DESC);

-- Индекс для поиска по координатам (для геопространственных запросов)
CREATE INDEX IF NOT EXISTS idx_user_states_location ON user_states(latitude, longitude);

-- ===== PLACES =====
-- Индекс для получения мест по состоянию
CREATE INDEX IF NOT EXISTS idx_places_state_id ON places(state_id);

-- Индекс для сортировки по match_score
CREATE INDEX IF NOT EXISTS idx_places_state_score ON places(state_id, match_score DESC);

-- Индекс для фильтрации по типу места
CREATE INDEX IF NOT EXISTS idx_places_type ON places(place_type);

-- Индекс для поиска по координатам
CREATE INDEX IF NOT EXISTS idx_places_location ON places(latitude, longitude);

-- ===== PSYCHOLOGICAL_PROFILES =====
-- Индекс для быстрого получения профиля пользователя
CREATE INDEX IF NOT EXISTS idx_psych_profiles_user_id ON psychological_profiles(user_id);

-- ===== USER_ANSWERS =====
-- Индекс для получения ответов пользователя
CREATE INDEX IF NOT EXISTS idx_user_answers_user_id ON user_answers(user_id);

-- Индекс для поиска незавершенных анкет
CREATE INDEX IF NOT EXISTS idx_user_answers_completed ON user_answers(user_id, completed);

-- ===== FRIEND_REQUESTS =====
-- Индекс для получения входящих запросов
CREATE INDEX IF NOT EXISTS idx_friend_requests_receiver ON friend_requests(receiver_id, status);

-- Индекс для получения исходящих запросов
CREATE INDEX IF NOT EXISTS idx_friend_requests_sender ON friend_requests(sender_id, status);

-- Композитный индекс для проверки существующей связи
CREATE INDEX IF NOT EXISTS idx_friend_requests_pair ON friend_requests(sender_id, receiver_id);

-- ===== ACTIVITY_INVITES =====
-- Индекс для получения входящих приглашений
CREATE INDEX IF NOT EXISTS idx_activity_invites_receiver ON activity_invites(receiver_id, status, created_at DESC);

-- Индекс для получения исходящих приглашений
CREATE INDEX IF NOT EXISTS idx_activity_invites_sender ON activity_invites(sender_id, status, created_at DESC);

-- ===== USER_LIKES =====
-- Индекс для получения лайков пользователя
CREATE INDEX IF NOT EXISTS idx_user_likes_user_id ON user_likes(user_id, created_at DESC);

-- Индекс для получения лайков объекта
CREATE INDEX IF NOT EXISTS idx_user_likes_object ON user_likes(object_type, object_id, reaction);

-- Композитный индекс для проверки существующего лайка
CREATE INDEX IF NOT EXISTS idx_user_likes_user_object ON user_likes(user_id, object_type, object_id);

-- ===== USER_SETTINGS =====
-- Индекс для быстрого получения настроек пользователя
CREATE INDEX IF NOT EXISTS idx_user_settings_user_id ON user_settings(user_id);

-- ===== QUESTIONS =====
-- Индекс для сортировки вопросов по порядку
CREATE INDEX IF NOT EXISTS idx_questions_order ON questions("order");

-- Индекс для фильтрации по шкале
CREATE INDEX IF NOT EXISTS idx_questions_scale ON questions(scale);

-- ===== MEETINGS (если используется) =====
-- Индекс для получения встреч организатора
CREATE INDEX IF NOT EXISTS idx_meetings_organizer ON meetings(organizer_id, scheduled_at DESC);

-- ===== MEETING_PARTICIPANTS (если используется) =====
-- Индекс для получения участников встречи
CREATE INDEX IF NOT EXISTS idx_meeting_participants_meeting ON meeting_participants(meeting_id);

-- Индекс для получения встреч пользователя
CREATE INDEX IF NOT EXISTS idx_meeting_participants_user ON meeting_participants(user_id, status);

-- ===== СТАТИСТИКА =====
-- Обновление статистики для оптимизатора запросов
ANALYZE users;
ANALYZE user_states;
ANALYZE places;
ANALYZE psychological_profiles;
ANALYZE user_answers;
ANALYZE friend_requests;
ANALYZE activity_invites;
ANALYZE user_likes;
ANALYZE user_settings;
ANALYZE questions;

-- Вывод информации об индексах
SELECT 
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;