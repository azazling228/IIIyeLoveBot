FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && mkdir -p /app/data

COPY bot.py database.py miniapp.py ./
COPY miniapp ./miniapp

EXPOSE 8080

CMD ["python", "bot.py"]
