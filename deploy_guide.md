# Oracle Cloud 서버 배포 가이드

## 서버 접속

```bash
ssh -i C:\Users\ebook\.ssh\oracle_baletauto.key.key ubuntu@168.107.26.196
```

## 현재 완료된 항목
- ✅ Swap 2GB
- ✅ Python 3.10 + venv + pip 패키지 (playwright, requests)
- ✅ Playwright + Chromium 브라우저
- ✅ Git clone (코드 배포)
- ✅ 타임존 Asia/Seoul

## 남은 작업: config.json 생성

서버에 SSH 접속 후 아래 실행:

```bash
cat > ~/baletAuto/config.json << 'EOF'
{
  "name": "이다림",
  "phone": "01031266120",
  "is_resident_staff": true,
  "car_wash": false,
  "service_type": "일반",
  "car_number": "26누5648",
  "car_model": "모델y",
  "car_brand": "테슬라",
  "car_color": "흰색",
  "discount_type": "일반",
  "departure_time": "07:00",
  "arrival_days_offset": 3,
  "arrival_time": "18:00",
  "departure_airline": "대한항공",
  "arrival_airline": "대한항공",
  "booking_url": "https://valet.amanopark.co.kr/booking",
  "booking_list_url": "https://valet.amanopark.co.kr/booking-list",
  "telegram": {
    "bot_token": "8653186098:AAHZdOpq43p2pIH8azUdC0e0u-vbC2cqKk0",
    "chat_id": "8449547453"
  }
}
EOF
```

## 서비스 실행

```bash
cd ~/baletAuto
source venv/bin/activate

# 1. 자동 예약 스케줄러 (백그라운드)
nohup python scheduler.py > ~/scheduler.log 2>&1 &

# 2. 텔레그램 봇 (백그라운드)
nohup python scheduler.py --bot > ~/bot.log 2>&1 &
```

## 로그 확인

```bash
tail -f ~/scheduler.log   # 예약 스케줄러 로그
tail -f ~/bot.log          # 텔레그램 봇 로그
```

## 서비스 중지

```bash
pkill -f "scheduler.py"
```
