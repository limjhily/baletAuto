"""
인천공항 T2 발렛 파킹 자동 예약 - 스케줄러 + 텔레그램 알림
매일 자정에 2개월 뒤 날짜를 자동 예약합니다.

사용법:
    python scheduler.py              # 매일 자정 자동 예약
    python scheduler.py --dry-run    # 드라이런 (즉시 실행, 등록 안 함)
    python scheduler.py --test-now   # 즉시 실행 테스트 (실제 등록)
"""

import argparse
import json
import logging
import os
import sys
import time
import requests
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from booking import load_config, calculate_dates, run_booking

# ============================================================
# 로깅 설정
# ============================================================
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(LOG_DIR, f"booking_{datetime.now().strftime('%Y%m%d')}.log"),
            encoding="utf-8"
        ),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


# ============================================================
# 텔레그램 알림
# ============================================================
def send_telegram(config, message):
    """텔레그램 메시지 전송"""
    try:
        token = config["telegram"]["bot_token"]
        chat_id = config["telegram"]["chat_id"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, data=data, timeout=10)
        if response.status_code == 200:
            logger.info("텔레그램 알림 전송 성공")
        else:
            logger.error(f"텔레그램 전송 실패: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"텔레그램 전송 에러: {e}")


def send_telegram_photo(config, photo_path, caption=""):
    """텔레그램 사진 전송"""
    try:
        token = config["telegram"]["bot_token"]
        chat_id = config["telegram"]["chat_id"]
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        with open(photo_path, "rb") as photo:
            data = {"chat_id": chat_id, "caption": caption}
            files = {"photo": photo}
            response = requests.post(url, data=data, files=files, timeout=30)
        if response.status_code == 200:
            logger.info(f"텔레그램 사진 전송 성공: {photo_path}")
        else:
            logger.error(f"텔레그램 사진 전송 실패: {response.status_code}")
    except Exception as e:
        logger.error(f"텔레그램 사진 전송 에러: {e}")


# ============================================================
# 예약 실행
# ============================================================
def execute_booking(config, dry_run=False, max_retries=3, override_date=None, skip_dates=False):
    """예약 실행 + 재시도 + 텔레그램 알림"""
    if override_date:
        departure_date = override_date
    else:
        departure_date = calculate_dates()
    arrival_date = departure_date + timedelta(days=config["arrival_days_offset"])

    logger.info(f"🎯 목표 예약: 출발 {departure_date.strftime('%Y-%m-%d')} → 도착 {arrival_date.strftime('%Y-%m-%d')}")

    # 예약 시도마다의 마지막 실패 원인을 저장
    last_error_msg = "알 수 없는 에러"
    last_screenshot = None

    for attempt in range(1, max_retries + 1):
        logger.info(f"📝 예약 시도 {attempt}/{max_retries}")

        try:
            result = run_booking(config, departure_date, dry_run=dry_run, skip_dates=skip_dates)
            
            # 하위 호환성 (혹시 True/False 반환되는 경우 대비)
            if isinstance(result, bool):
                success = result
                err_text = None
                shot_path = None
            else:
                success = result.get("success", False)
                err_text = result.get("error")
                shot_path = result.get("screenshot")
            
            if err_text:
                last_error_msg = err_text
            if shot_path:
                last_screenshot = shot_path

            if success:
                msg = (
                    f"✅ <b>발렛파킹 예약 성공!</b>\n\n"
                    f"📅 출발: {departure_date.strftime('%Y-%m-%d')} {config['departure_time']}\n"
                    f"📅 도착: {arrival_date.strftime('%Y-%m-%d')} {config['arrival_time']}\n"
                    f"🚗 차량: {config['car_brand']} {config['car_model']} ({config['car_number']})\n"
                    f"✈️ 항공편: {config['departure_airline']}\n"
                    f"⏰ 예약시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                if dry_run:
                    msg = f"🔍 <b>[드라이런] 예약 테스트 완료</b>\n\n{msg}"

                send_telegram(config, msg)

                # 성공 스크린샷이 있으면 전송
                if shot_path and os.path.exists(shot_path):
                    send_telegram_photo(config, shot_path, "예약 확인 스크린샷")
                else:
                    screenshot = os.path.join(LOG_DIR, f"success_{departure_date.strftime('%Y-%m-%d')}.png")
                    if os.path.exists(screenshot):
                        send_telegram_photo(config, screenshot, "예약 확인 스크린샷")

                return True
            else:
                logger.warning(f"예약 시도 {attempt} 실패: {err_text}")
                if attempt < max_retries:
                    logger.info(f"5초 후 재시도...")
                    time.sleep(5)

        except Exception as e:
            logger.error(f"예약 시도 {attempt} 에러: {e}")
            last_error_msg = f"예외 발생: {str(e)}"
            if attempt < max_retries:
                logger.info(f"5초 후 재시도...")
                time.sleep(5)

    # 모든 시도 실패
    fail_msg = (
        f"❌ <b>발렛파킹 예약 실패!</b>\n\n"
        f"📅 목표 출발일: {departure_date.strftime('%Y-%m-%d')}\n"
        f"⚠️ {max_retries}회 시도 모두 실패\n\n"
        f"<b>[실패 원인]</b>\n{last_error_msg}\n\n"
        f"⏰ 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    send_telegram(config, fail_msg)
    
    if last_screenshot and os.path.exists(last_screenshot):
        send_telegram_photo(config, last_screenshot, "실패 스크린샷")
        
    return False


# ============================================================
# 자정 스케줄러
# ============================================================
def wait_until_midnight():
    """자정(00:00:00)까지 대기"""
    now = datetime.now()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    wait_seconds = (tomorrow - now).total_seconds()

    logger.info(f"⏳ 다음 자정까지 {wait_seconds:.0f}초 ({wait_seconds/3600:.1f}시간) 대기")
    logger.info(f"   다음 실행: {tomorrow.strftime('%Y-%m-%d %H:%M:%S')}")

    # 자정 5초 전까지 대기
    while True:
        now = datetime.now()
        remaining = (tomorrow - now).total_seconds()

        if remaining <= 5:
            break

        # 남은 시간에 따라 체크 간격 조절
        if remaining > 3600:
            time.sleep(600)  # 1시간 이상: 10분마다
        elif remaining > 300:
            time.sleep(60)   # 5분 이상: 1분마다
        elif remaining > 30:
            time.sleep(10)   # 30초 이상: 10초마다
        else:
            time.sleep(1)    # 30초 이하: 1초마다

    # 정확히 자정까지 밀리초 단위 대기
    while datetime.now() < tomorrow:
        time.sleep(0.01)

    logger.info(f"🕛 자정 도달: {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')}")


def run_scheduler(config, dry_run=False):
    """메인 스케줄러 루프"""
    logger.info("=" * 60)
    logger.info("🚗 발렛파킹 자동 예약 스케줄러 시작")
    logger.info(f"   예약자: {config['name']} ({config['phone']})")
    logger.info(f"   차량: {config['car_brand']} {config['car_model']} ({config['car_number']})")
    logger.info("=" * 60)

    # 시작 알림
    start_msg = (
        f"🚗 <b>발렛파킹 자동 예약 스케줄러 시작</b>\n\n"
        f"👤 {config['name']}\n"
        f"📱 {config['phone']}\n"
        f"🚙 {config['car_brand']} {config['car_model']} ({config['car_number']})\n"
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    send_telegram(config, start_msg)

    while True:
        try:
            # 자정까지 대기
            wait_until_midnight()

            # 예약 실행
            execute_booking(config, dry_run=dry_run)

        except KeyboardInterrupt:
            logger.info("스케줄러 종료 (사용자 중단)")
            send_telegram(config, "⏹ <b>발렛파킹 스케줄러 종료</b> (사용자 중단)")
            break

        except Exception as e:
            logger.error(f"스케줄러 에러: {e}")
            send_telegram(config, f"⚠️ <b>스케줄러 에러</b>\n{str(e)}")
            # 1분 후 재시도
            time.sleep(60)


# ============================================================
# 메인
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="인천공항 T2 발렛파킹 자동 예약")
    parser.add_argument("--dry-run", action="store_true",
                        help="드라이런 모드 (폼 입력만 하고 등록 안 함)")
    parser.add_argument("--test-now", action="store_true",
                        help="즉시 실행 테스트 (자정 대기 안 함)")
    parser.add_argument("--skip-dates", action="store_true",
                        help="날짜/시간 선택 스킵 (예약 꽉 참 테스트용)")
    parser.add_argument("--test-date", type=str, default=None,
                        help="테스트용 출발 날짜 (예: 2026-05-02)")
    parser.add_argument("--config", default="config.json",
                        help="설정 파일 경로 (기본: config.json)")
    parser.add_argument("--bot", action="store_true",
                        help="텔레그램 봇 모드 (메시지 대기)")
    parser.add_argument("--cancel", action="store_true",
                        help="예약 취소 모드")
    parser.add_argument("--month", type=int, default=None,
                        help="취소 대상 월 (예: 5)")
    parser.add_argument("--keep", type=str, default=None,
                        help="유지할 날짜 (쉼표 구분, 예: 13,14,20,21)")
    args = parser.parse_args()

    # 설정 로드
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.config)
    config = load_config(config_path)

    if args.bot:
        # 텔레그램 봇 모드
        logger.info("🤖 텔레그램 봇 모드")
        from telegram_bot import run_bot
        run_bot(config)

    elif args.cancel:
        # CLI 취소 모드
        if not args.month or not args.keep:
            print("사용법: python scheduler.py --cancel --month 5 --keep 13,14,20,21")
            sys.exit(1)

        year = datetime.now().year
        month = args.month
        keep_days = [int(d.strip()) for d in args.keep.split(",")]

        logger.info(f"📋 CLI 취소 모드: {year}년 {month}월")
        logger.info(f"   유지 날짜: {keep_days}")

        from cancel_booking import run_cancel
        result = run_cancel(config, year, month, keep_days, dry_run=args.dry_run)

        if result.get("error"):
            logger.error(f"취소 실패: {result['error']}")
        else:
            logger.info(f"취소 완료: {result['cancelled']}건 취소, {result['kept']}건 유지")

    elif args.test_now or args.dry_run:
        # 즉시 실행 모드
        logger.info("⚡ 즉시 실행 모드")
        if args.test_date:
            # 특정 날짜로 테스트
            from datetime import datetime as dt
            departure_date = dt.strptime(args.test_date, "%Y-%m-%d")
            execute_booking(config, dry_run=args.dry_run, override_date=departure_date, skip_dates=args.skip_dates)
        else:
            execute_booking(config, dry_run=args.dry_run, skip_dates=args.skip_dates)
    else:
        # 스케줄러 모드 (매일 자정 실행)
        run_scheduler(config)


if __name__ == "__main__":
    main()
