FROM python:3.11-slim

# 한글 폰트 + 필요 시스템 패키지 설치
RUN apt-get update && apt-get install -y \
    fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir setuptools && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
