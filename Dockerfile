FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    fonts-nanum \
    tzdata \
    && ln -sf /usr/share/zoneinfo/Asia/Seoul /etc/localtime \
    && echo "Asia/Seoul" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


COPY . .

ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Seoul

CMD ["python", "-u", "bot.py"]