FROM python:3.11-slim

# Метаданные
LABEL maintainer="eo-fedorova@mail.ru"
LABEL description="Routsol Web - персональный сервис рекомендаций отдыха"
LABEL version="1.1.0"

# Установка рабочей директории
WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements и установка Python зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копирование всех файлов приложения
COPY . .

# Создание директории для instance (SQLite)
RUN mkdir -p instance

# Открытие порта
EXPOSE 5000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5000/', timeout=5)" || exit 1

# Запуск приложения
CMD ["python", "app.py"]