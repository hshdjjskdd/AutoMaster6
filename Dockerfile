FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Зависимости ставятся отдельным слоем: при правке кода он берётся из кэша.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY main.py .
COPY app ./app

# Бот работает не от root. Папка data/ хранит базу SQLite и должна лежать на томе,
# иначе данные игроков пропадут вместе с контейнером.
RUN useradd --system --create-home --uid 10001 bot \
    && mkdir -p /app/data \
    && chown -R bot:bot /app/data
USER bot
VOLUME ["/app/data"]

# BOT_TOKEN передаётся переменной окружения (-e BOT_TOKEN=... или env_file), в образ не зашивается.
CMD ["python", "main.py"]
