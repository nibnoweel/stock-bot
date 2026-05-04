# 📈 KRX 주식 스캐너 텔레그램 봇

KOSPI/KOSDAQ 전 종목을 스캔하여 조건에 맞는 종목을 텔레그램으로 알려주는 봇입니다.

---

## 🔍 스캔 조건

| # | 조건 |
|---|------|
| 1 | 전일 대비 **거래량 2배 이상** |
| 2 | 전일 대비 **2% 이상 상승** |
| 3 | **200일 이동평균선 3% 이상 위** (5일 연속) |
| 4 | **윗꼬리 < 몸통** AND **윗꼬리 < 아랫꼬리** |

---

## 🚀 설치 및 실행

### 1. 패키지 설치
```bash
pip install -r requirements.txt
```

### 2. 텔레그램 봇 토큰 발급
1. 텔레그램에서 **@BotFather** 검색
2. `/newbot` 명령어로 봇 생성
3. 발급받은 **토큰** 복사

### 3. 채팅 ID 확인
- **개인**: 텔레그램에서 **@userinfobot** 에 `/start`
- **그룹/채널**: 봇을 추가한 뒤 `https://api.telegram.org/bot<TOKEN>/getUpdates` 에서 확인

### 4. config.py 수정
```python
TELEGRAM_TOKEN = "1234567890:ABCdefGhIJKlmNOPqrsTUVwxyz"
CHAT_ID = "123456789"

# 스캔 시간 설정 (KST 기준)
SCAN_TIMES = [
    "08:30",   # 장 시작 전
    "15:35",   # 장 마감 직후
]
```

### 5. 봇 실행
```bash
python bot.py
```

---

## 📌 명령어

| 명령어 | 설명 |
|--------|------|
| `/start` | 봇 소개 |
| `/scan` | 즉시 스캔 실행 |
| `/status` | 봇 상태 및 스캔 시간 확인 |
| `/help` | 도움말 |

---

## 📁 파일 구조

```
stock_bot/
├── bot.py           # 텔레그램 봇 메인
├── scanner.py       # KRX 스캐너 (조건 필터링)
├── config.py        # 설정 (토큰, 채팅ID, 시간)
├── requirements.txt # 패키지 목록
└── README.md
```

---

## ⚠️ 주의사항

- **pykrx**는 한국투자증권 API 없이 KRX 데이터를 수집합니다 (무료)
- 전 종목(약 2,500개) 스캔은 **10~20분** 소요될 수 있습니다
- 장 마감 후 데이터가 완전히 업데이트되는 시간을 고려해 **15:35 이후** 스캔을 권장합니다
- 서버에서 장기 운영 시 `nohup python bot.py &` 또는 `systemd` 서비스 등록 권장

---

## 🖥️ 서버 백그라운드 실행 (선택사항)

```bash
# 백그라운드 실행
nohup python bot.py > bot.log 2>&1 &

# 로그 확인
tail -f bot.log
```
