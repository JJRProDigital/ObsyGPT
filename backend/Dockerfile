FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Browser tools (browser_navigate & co.): Playwright + Chromium with the
# system libraries Chromium needs on slim Debian images.
RUN pip install --no-cache-dir playwright && \
    playwright install --with-deps chromium

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
