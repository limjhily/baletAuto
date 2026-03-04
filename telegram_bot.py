"""
인천공항 T2 발렛 파킹 - 텔레그램 봇
텔레그램으로 유지할 날짜를 보내면 나머지 예약을 자동 취소합니다.

메시지 형식:
    2026.05
    13
    14
    20
    21

봇 응답:
    1) 유지/취소 목록 확인 요청
    2) "확인" 입력 시 실제 취소 실행
    3) 결과 보고
"""

import json
import logging
import os
import re
import time
import requests
from datetime import datetime

from booking import load_config
from cancel_booking import run_cancel

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")


class TelegramBot:
    """텔레그램 봇 (Long Polling 방식)"""

    def __init__(self, config):
        self.config = config
        self.token = config["telegram"]["bot_token"]
        self.chat_id = config["telegram"]["chat_id"]
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.offset = 0

        # 대기 중인 취소 작업 (확인 전)
        self.pending_cancel = None

    def send_message(self, text):
        """메시지 전송"""
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
            }
            response = requests.post(url, data=data, timeout=10)
            if response.status_code != 200:
                logger.error(f"메시지 전송 실패: {response.status_code}")
        except Exception as e:
            logger.error(f"메시지 전송 에러: {e}")

    def send_photo(self, photo_path, caption=""):
        """사진 전송"""
        try:
            url = f"{self.base_url}/sendPhoto"
            with open(photo_path, "rb") as photo:
                data = {"chat_id": self.chat_id, "caption": caption}
                files = {"photo": photo}
                requests.post(url, data=data, files=files, timeout=30)
        except Exception as e:
            logger.error(f"사진 전송 에러: {e}")

    def get_updates(self):
        """새 메시지 가져오기 (Long Polling)"""
        try:
            url = f"{self.base_url}/getUpdates"
            params = {
                "offset": self.offset,
                "timeout": 30,
            }
            response = requests.get(url, params=params, timeout=35)
            if response.status_code == 200:
                data = response.json()
                if data.get("ok") and data.get("result"):
                    return data["result"]
            return []
        except requests.exceptions.Timeout:
            return []
        except Exception as e:
            logger.error(f"업데이트 가져오기 에러: {e}")
            return []

    def parse_keep_dates_message(self, text):
        """
        유지 날짜 메시지 파싱

        형식:
            2026.05
            13
            14
            20

        Returns:
            (year, month, days) 또는 None
        """
        lines = text.strip().split("\n")
        lines = [line.strip() for line in lines if line.strip()]

        if len(lines) < 2:
            return None

        # 첫 줄: 연도.월 (예: 2026.05)
        first_line = lines[0]
        match = re.match(r"(\d{4})[.\-/](\d{1,2})", first_line)
        if not match:
            return None

        year = int(match.group(1))
        month = int(match.group(2))

        # 나머지 줄: 날짜 (숫자만)
        days = []
        for line in lines[1:]:
            line = line.strip()
            if line.isdigit():
                day = int(line)
                if 1 <= day <= 31:
                    days.append(day)

        if not days:
            return None

        return year, month, days

    def handle_message(self, message):
        """메시지 처리"""
        text = message.get("text", "").strip()
        chat_id = str(message.get("chat", {}).get("id", ""))

        # 본인 채팅만 처리
        if chat_id != self.chat_id:
            logger.info(f"무시된 메시지 (chat_id 불일치): {chat_id}")
            return

        logger.info(f"수신 메시지: {text}")

        # ===== 명령어 처리 =====

        # 1. "help" - 도움말
        if text.lower() == "help" or text == "도움말":
            self._handle_help()
            return

        # 2. "조회" - 예약 리스트 조회
        if text == "조회":
            self._handle_query()
            return

        # 3. "확인" - 대기 중인 취소 실행
        if text == "확인":
            self._handle_confirm()
            return

        # 4. "취소" - 대기 중인 취소 작업 중단
        if text == "취소":
            self._handle_abort()
            return

        # 5. 유지 날짜 메시지 파싱 시도
        parsed = self.parse_keep_dates_message(text)
        if parsed:
            year, month, days = parsed
            self._handle_keep_dates(year, month, days)
            return

        # 인식 불가
        # (무관한 메시지는 무시)

    def _handle_help(self):
        """도움말 표시"""
        help_text = (
            "📖 <b>발렛파킹 취소 봇 사용법</b>\n"
            "━━━━━━━━━━━━━━━\n\n"
            "<b>📌 예약 유지 날짜 입력</b>\n"
            "첫줄에 연도.월, 다음 줄부터 유지할 날짜를 한 줄씩 입력\n\n"
            "<b>입력 예시:</b>\n"
            "<code>2026.05\n"
            "13\n"
            "14\n"
            "20\n"
            "21\n"
            "25\n"
            "26\n"
            "30\n"
            "31</code>\n\n"
            "→ 5월 13,14,20,21,25,26,30,31일만 유지\n"
            "→ 나머지 5월 예약은 전부 취소\n\n"
            "━━━━━━━━━━━━━━━\n"
            "<b>📋 명령어 목록</b>\n\n"
            "<b>help</b>  도움말 (이 메시지)\n"
            "<b>조회</b>    현재 예약 리스트 확인\n"
            "<b>확인</b>    취소 최종 실행\n"
            "<b>취소</b>    대기 중인 취소 작업 중단\n\n"
            "━━━━━━━━━━━━━━━\n"
            "<b>💡 사용 순서</b>\n"
            "1. 유지할 날짜 전송\n"
            "2. 봇이 유지/취소 목록 표시\n"
            "3. <b>확인</b> 입력 → 취소 실행"
        )
        self.send_message(help_text)

    def _handle_query(self):
        """조회 명령 처리"""
        self.send_message("🔍 예약 리스트 조회 중...")

        try:
            from cancel_booking import fetch_booking_list, parse_booking_table
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
                context = browser.new_context(
                    viewport={"width": 1280, "height": 900}, locale="ko-KR"
                )
                page = context.new_page()

                if fetch_booking_list(page, self.config):
                    bookings = parse_booking_table(page)

                    if bookings:
                        lines = ["📋 <b>현재 예약 리스트</b>\n"]
                        for b in bookings:
                            status_icon = "🟢" if b["status"] == "예약" else "⚪"
                            lines.append(
                                f"{status_icon} {b['departure_date']} ~ {b['arrival_date']} ({b['status']})"
                            )
                        lines.append(f"\n총 {len(bookings)}건")
                        self.send_message("\n".join(lines))
                    else:
                        self.send_message("예약이 없습니다.")

                    # 스크린샷 전송
                    os.makedirs(LOG_DIR, exist_ok=True)
                    screenshot = os.path.join(LOG_DIR, "query_result.png")
                    page.screenshot(path=screenshot, full_page=True)
                    self.send_photo(screenshot, "예약 리스트")
                else:
                    self.send_message("❌ 예약 리스트 조회 실패")

                browser.close()

        except Exception as e:
            logger.error(f"조회 에러: {e}")
            self.send_message(f"❌ 조회 에러: {str(e)}")

    def _handle_keep_dates(self, year, month, days):
        """유지 날짜 수신 → 확인 요청"""
        days_sorted = sorted(days)
        month_str = f"{year}년 {month}월"
        keep_str = ", ".join([f"{month}/{d}" for d in days_sorted])

        # 대기 상태 저장
        self.pending_cancel = {
            "year": year,
            "month": month,
            "keep_days": days_sorted,
        }

        # 예약 리스트를 미리 확인하여 취소 대상 개수 파악
        try:
            from cancel_booking import fetch_booking_list, parse_booking_table, get_cancel_targets
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
                context = browser.new_context(
                    viewport={"width": 1280, "height": 900}, locale="ko-KR"
                )
                page = context.new_page()

                cancel_dates = []
                keep_dates_actual = []

                if fetch_booking_list(page, self.config):
                    bookings = parse_booking_table(page)
                    cancel_list, keep_list = get_cancel_targets(bookings, year, month, days_sorted)
                    cancel_dates = sorted([b["departure_date"] for b in cancel_list])
                    keep_dates_actual = sorted([b["departure_date"] for b in keep_list])

                browser.close()

            # 확인 메시지 구성
            lines = [
                f"📋 <b>{month_str} 예약 취소 확인</b>\n",
                f"✅ <b>유지할 날짜:</b> {keep_str}",
            ]

            if keep_dates_actual:
                lines.append(
                    f"   (현재 예약 중: {', '.join([d.split('-')[2].lstrip('0') + '일' for d in keep_dates_actual])})"
                )

            if cancel_dates:
                cancel_str = ", ".join(
                    [d.split("-")[2].lstrip("0") + "일" for d in cancel_dates]
                )
                lines.append(f"\n❌ <b>취소 대상:</b> {cancel_str} ({len(cancel_dates)}건)")
            else:
                lines.append("\n✨ 취소할 예약이 없습니다!")

            lines.append('\n취소를 진행하려면 <b>"확인"</b> 을 입력해주세요.')
            lines.append('"취소"를 입력하면 작업을 중단합니다.')

            self.send_message("\n".join(lines))

        except Exception as e:
            logger.error(f"예약 확인 에러: {e}")
            # 에러 시에도 기본 확인 메시지 전송
            lines = [
                f"📋 <b>{month_str} 예약 취소 확인</b>\n",
                f"✅ <b>유지할 날짜:</b> {keep_str}",
                f"\n⚠️ 예약 리스트 미리보기 실패: {str(e)}",
                '\n취소를 진행하려면 <b>"확인"</b> 을 입력해주세요.',
            ]
            self.send_message("\n".join(lines))

    def _handle_confirm(self):
        """확인 → 실제 취소 실행"""
        if not self.pending_cancel:
            self.send_message("⚠️ 대기 중인 취소 작업이 없습니다.")
            return

        year = self.pending_cancel["year"]
        month = self.pending_cancel["month"]
        keep_days = self.pending_cancel["keep_days"]

        self.send_message(f"🔄 {year}년 {month}월 예약 취소 진행 중...")

        # 취소 실행
        result = run_cancel(self.config, year, month, keep_days, dry_run=False)

        # 결과 메시지
        if result.get("error"):
            self.send_message(f"❌ 취소 실패: {result['error']}")
        else:
            lines = [
                f"✅ <b>{year}년 {month}월 예약 취소 완료!</b>\n",
                f"❌ 취소: {result['cancelled']}건",
                f"✅ 유지: {result['kept']}건",
            ]

            if result["cancel_dates"]:
                cancel_str = ", ".join(
                    [d.split("-")[2].lstrip("0") + "일" for d in result["cancel_dates"]]
                )
                lines.append(f"\n취소된 날짜: {cancel_str}")

            if result["keep_dates"]:
                keep_str = ", ".join(
                    [d.split("-")[2].lstrip("0") + "일" for d in result["keep_dates"]]
                )
                lines.append(f"유지된 날짜: {keep_str}")

            lines.append(f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self.send_message("\n".join(lines))

            # 스크린샷 전송
            if result.get("screenshot") and os.path.exists(result["screenshot"]):
                self.send_photo(result["screenshot"], "취소 후 예약 리스트")

        # 대기 상태 초기화
        self.pending_cancel = None

    def _handle_abort(self):
        """취소 작업 중단"""
        if self.pending_cancel:
            self.pending_cancel = None
            self.send_message("⏹ 취소 작업이 중단되었습니다.")
        else:
            self.send_message("대기 중인 작업이 없습니다.")

    def run(self):
        """봇 실행 (Long Polling)"""
        logger.info("🤖 텔레그램 봇 시작")
        self.send_message(
            "🤖 <b>발렛파킹 취소 봇 시작</b>\n\n"
            "명령어:\n"
            '• 유지할 날짜 전송 (첫줄: 연도.월)\n'
            '• "조회" - 예약 리스트 확인\n'
            '• "확인" - 취소 실행\n'
            '• "취소" - 작업 중단'
        )

        while True:
            try:
                updates = self.get_updates()

                for update in updates:
                    self.offset = update["update_id"] + 1

                    if "message" in update and "text" in update["message"]:
                        self.handle_message(update["message"])

            except KeyboardInterrupt:
                logger.info("봇 종료 (사용자 중단)")
                self.send_message("⏹ <b>봇 종료</b>")
                break
            except Exception as e:
                logger.error(f"봇 에러: {e}")
                time.sleep(5)


def run_bot(config):
    """봇 실행 진입점"""
    bot = TelegramBot(config)
    bot.run()
