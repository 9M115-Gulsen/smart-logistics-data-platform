FROM python:3.11-slim

# Устанавливаем системные зависимости (включая psql)
RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*

# Сразу ставим питоновские библиотеки, чтобы не ждать при каждом запуске
RUN pip install --no-cache-dir psycopg[binary] pandas scikit-learn sqlalchemy catboost

WORKDIR /app
