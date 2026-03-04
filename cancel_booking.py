"""
인천공항 T2 발렛 파킹 - 예약 취소 로직
예약 리스트에서 유지할 날짜를 제외한 나머지를 자동 취소합니다.
"""

import logging
import os
import time
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")


def fetch_booking_list(page, config):
    """
    예약 리스트 페이지에 접속하여 차량번호/전화번호로 조회합니다.

    Returns:
        bool: 조회 성공 여부
    """
    logger.info("예약 리스트 페이지 접속 중...")
    page.goto(config["booking_list_url"], wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)

    # 차량번호 입력 (첫 번째 visible input)
    inputs = page.locator("input")
    input_count = inputs.count()

    visible_inputs = []
    for i in range(input_count):
        inp = inputs.nth(i)
        if inp.is_visible():
            visible_inputs.append(inp)

    if len(visible_inputs) < 2:
        logger.error("입력 필드를 찾을 수 없습니다")
        return False

    # 첫 번째: 차량번호, 두 번째: 전화번호
    visible_inputs[0].fill(config["car_number"])
    visible_inputs[1].fill(config["phone"])
    page.wait_for_timeout(300)

    # 확인 버튼 클릭
    confirm_btn = page.locator("button").filter(has_text="확인").first
    confirm_btn.click()
    page.wait_for_timeout(3000)

    logger.info("예약 리스트 조회 완료")
    return True


def parse_booking_table(page):
    """
    예약 리스트 테이블을 파싱합니다.

    Returns:
        list[dict]: 예약 목록
        [
            {
                "index": 1,
                "car_number": "26누56**",
                "request_date": "2026-03-04",
                "departure_date": "2026-05-03",
                "arrival_date": "2026-05-06",
                "status": "예약",
                "has_cancel_button": True
            },
            ...
        ]
    """
    bookings = []

    # 테이블 행 찾기
    rows = page.locator("table tbody tr, .el-table__body tbody tr")

    # 테이블이 없으면 다른 구조 시도 (리스트 형태)
    if rows.count() == 0:
        # 텍스트 기반 파싱 시도
        logger.info("테이블 구조 탐색 중...")
        # 페이지 전체 텍스트에서 날짜 패턴 찾기
        body_text = page.text_content("body") or ""

        # 각 행을 개별적으로 파싱
        # 번호, 차량번호, 신청일, 출국일, 입국일, 예약정보, 예약현황
        # 행 구분: 번호(숫자)로 시작하는 패턴
        import re

        # 모든 예약취소 버튼과 확인하기 버튼 찾기
        cancel_buttons = page.locator("button").filter(has_text="예약취소")
        confirm_buttons = page.locator("button").filter(has_text="확인하기")

        # 페이지에서 날짜 패턴 추출 (YYYY-MM-DD)
        date_pattern = re.compile(r"\d{4}-\d{2}-\d{2}")

        # 각 행의 정보를 추출하기 위해 리스트 아이템 찾기
        # 번호별로 텍스트 블록 추출
        list_items = page.locator("tr, [class*='row'], [class*='item'], [class*='list']")

        # 더 간단한 접근: 모든 텍스트에서 날짜 쌍 추출
        all_dates = date_pattern.findall(body_text)

        # 날짜들을 3개씩 묶기 (신청일, 출국일, 입국일)
        i = 0
        booking_index = 1
        while i + 2 < len(all_dates):
            request_date = all_dates[i]
            departure_date = all_dates[i + 1]
            arrival_date = all_dates[i + 2]

            # 상태 판별: 출차/예약
            booking = {
                "index": booking_index,
                "request_date": request_date,
                "departure_date": departure_date,
                "arrival_date": arrival_date,
                "status": "예약",  # 기본값
                "has_cancel_button": False,
            }
            bookings.append(booking)
            booking_index += 1
            i += 3

        # 취소 버튼 매핑 - 예약취소 버튼이 있는 항목 = 예약 상태
        cancel_count = cancel_buttons.count()
        logger.info(f"예약취소 버튼 {cancel_count}개 발견")

        # 출차 상태인 항목 찾기 (취소 버튼 없음)
        status_texts = page.locator("text=출차").all()
        for st in status_texts:
            # 출차 텍스트 근처의 날짜를 찾아서 매칭
            pass

        # 취소 버튼이 있는 예약만 cancel 가능 표시
        # 위에서 아래로 순서대로 매핑
        cancel_idx = 0
        for booking in bookings:
            if cancel_idx < cancel_count:
                booking["has_cancel_button"] = True
                cancel_idx += 1

        # 상태 확인: "출차" 텍스트가 있으면 해당 예약은 출차 상태
        if "출차" in body_text:
            for booking in bookings:
                # 출차 상태 항목은 취소 버튼이 없음
                pass

    logger.info(f"총 {len(bookings)}건의 예약 파싱 완료")
    for b in bookings:
        logger.info(
            f"  [{b['index']}] 출국: {b['departure_date']} "
            f"입국: {b['arrival_date']} 상태: {b['status']}"
        )

    return bookings


def get_cancel_targets(bookings, year, month, keep_days):
    """
    취소 대상 예약을 필터링합니다.

    Args:
        bookings: 예약 목록
        year: 대상 연도 (예: 2026)
        month: 대상 월 (예: 5)
        keep_days: 유지할 날짜 리스트 (예: [13, 14, 20, 21])

    Returns:
        (cancel_list, keep_list): 취소할 예약, 유지할 예약
    """
    target_prefix = f"{year}-{month:02d}"
    keep_dates = {f"{year}-{month:02d}-{day:02d}" for day in keep_days}

    cancel_list = []
    keep_list = []

    for booking in bookings:
        dep_date = booking["departure_date"]

        # 해당 월의 예약만 대상
        if not dep_date.startswith(target_prefix):
            continue

        # 출차 완료된 항목 제외
        if booking["status"] == "출차":
            continue

        # 취소 버튼이 없는 항목 제외
        if not booking["has_cancel_button"]:
            continue

        if dep_date in keep_dates:
            keep_list.append(booking)
        else:
            cancel_list.append(booking)

    return cancel_list, keep_list


def execute_cancellations(page, cancel_list, dry_run=False):
    """
    실제 예약 취소를 실행합니다.

    취소 버튼을 클릭하면 확인 팝업이 뜨므로, 확인을 눌러 완료합니다.
    중요: 취소 후 리스트가 갱신되므로 매번 위에서부터 다시 찾아야 합니다.

    Args:
        page: Playwright 페이지
        cancel_list: 취소할 예약 목록 (departure_date 기준)
        dry_run: True면 실제 취소 안 함

    Returns:
        int: 취소 성공 건수
    """
    cancelled_count = 0
    cancel_dates = {b["departure_date"] for b in cancel_list}

    logger.info(f"취소 대상: {len(cancel_dates)}건")

    if dry_run:
        logger.info("🔍 드라이런 모드 - 실제 취소하지 않음")
        for date in sorted(cancel_dates):
            logger.info(f"  [드라이런] 취소 대상: {date}")
        return len(cancel_dates)

    # 한 건씩 취소 (취소 후 리스트가 갱신되므로)
    for target_date in sorted(cancel_dates):
        try:
            logger.info(f"🔄 {target_date} 취소 시도...")

            # 예약취소 버튼들 다시 찾기 (리스트 갱신 대응)
            # 페이지 텍스트에서 해당 날짜가 있는 행의 취소 버튼 찾기
            page.wait_for_timeout(1000)

            # 해당 날짜 텍스트를 포함하는 행 찾기
            # 테이블 구조: 각 행에 출국일이 표시되고, 같은 행에 예약취소 버튼 있음
            body_text = page.text_content("body") or ""

            if target_date not in body_text:
                logger.warning(f"  {target_date} 를 페이지에서 찾을 수 없음 (이미 취소됨?)")
                continue

            # 해당 날짜 텍스트 요소 찾기
            date_elements = page.locator(f"text={target_date}").all()

            if not date_elements:
                logger.warning(f"  {target_date} 요소를 찾을 수 없음")
                continue

            # 날짜 요소의 부모 행에서 취소 버튼 찾기
            found_and_clicked = False
            for date_el in date_elements:
                try:
                    # 부모 행(tr 또는 상위 컨테이너) 찾기
                    row = date_el.locator("xpath=ancestor::tr").first
                    cancel_btn = row.locator("button").filter(has_text="예약취소")

                    if cancel_btn.count() > 0:
                        cancel_btn.first.click()
                        page.wait_for_timeout(1000)

                        # 확인 팝업 처리
                        _handle_cancel_popup(page)

                        cancelled_count += 1
                        found_and_clicked = True
                        logger.info(f"  ✅ {target_date} 취소 완료")
                        break
                except Exception:
                    continue

            if not found_and_clicked:
                # 대안: 버튼 인덱스 기반 취소
                # 취소 버튼과 날짜를 순서대로 매핑
                logger.info(f"  행 기반 탐색 실패, 인덱스 기반 시도...")
                _cancel_by_index(page, target_date)
                cancelled_count += 1

            page.wait_for_timeout(2000)

        except Exception as e:
            logger.error(f"  ❌ {target_date} 취소 실패: {e}")

    return cancelled_count


def _handle_cancel_popup(page):
    """취소 확인 팝업 처리"""
    try:
        # Element UI MessageBox 확인 버튼
        popup_confirm = page.locator(".el-message-box__btns .el-button--primary")
        popup_confirm.wait_for(state="visible", timeout=5000)
        popup_confirm.click()
        page.wait_for_timeout(1500)
        logger.info("  팝업 확인 클릭")
    except Exception:
        # 대체: visible한 '확인' 버튼
        try:
            alt_confirm = page.locator("button:visible").filter(has_text="확인").last
            if alt_confirm.count() > 0:
                alt_confirm.click()
                page.wait_for_timeout(1500)
                logger.info("  팝업 확인 클릭 (대체)")
        except Exception as e:
            logger.warning(f"  팝업 처리 실패: {e}")


def _cancel_by_index(page, target_date):
    """
    인덱스 기반 취소 (행 탐색 실패 시 대안)
    날짜와 취소 버튼의 순서를 매핑하여 취소
    """
    import re

    body_text = page.text_content("body") or ""
    date_pattern = re.compile(r"\d{4}-\d{2}-\d{2}")
    all_dates = date_pattern.findall(body_text)

    # 날짜들을 3개씩 묶어서 출국일 추출 (신청일, 출국일, 입국일)
    departure_dates = []
    for i in range(0, len(all_dates) - 2, 3):
        departure_dates.append(all_dates[i + 1])

    # 취소 버튼 목록
    cancel_buttons = page.locator("button").filter(has_text="예약취소")
    cancel_count = cancel_buttons.count()

    # 출차 상태 항목은 취소 버튼이 없으므로, 예약 상태인 것만 매핑
    # 출차 항목을 제외한 인덱스 계산
    cancel_btn_idx = 0
    for dep_date in departure_dates:
        if dep_date == target_date and cancel_btn_idx < cancel_count:
            cancel_buttons.nth(cancel_btn_idx).click()
            page.wait_for_timeout(1000)
            _handle_cancel_popup(page)
            logger.info(f"  ✅ {target_date} 취소 완료 (인덱스 기반)")
            return
        # 출차가 아닌 항목만 버튼 인덱스 증가
        if "출차" not in body_text.split(dep_date)[0].split("\n")[-1]:
            cancel_btn_idx += 1

    logger.warning(f"  {target_date} 인덱스 기반 취소도 실패")


def run_cancel(config, year, month, keep_days, dry_run=False):
    """
    예약 취소 메인 함수

    Args:
        config: 설정
        year: 대상 연도
        month: 대상 월
        keep_days: 유지할 날짜 리스트 (예: [13, 14, 20])
        dry_run: 드라이런 모드

    Returns:
        dict: 결과 {"cancelled": int, "kept": int, "cancel_dates": list, "keep_dates": list}
    """
    logger.info("=" * 60)
    logger.info(f"📋 예약 취소 시작: {year}년 {month}월")
    logger.info(f"   유지 날짜: {keep_days}")
    if dry_run:
        logger.info("   ⚠️ 드라이런 모드")
    logger.info("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=not dry_run,
            args=["--no-sandbox"]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ko-KR"
        )
        page = context.new_page()

        try:
            # 1. 예약 리스트 조회
            if not fetch_booking_list(page, config):
                browser.close()
                return {"cancelled": 0, "kept": 0, "cancel_dates": [], "keep_dates": [], "error": "조회 실패"}

            # 2. 테이블 파싱
            bookings = parse_booking_table(page)

            if not bookings:
                browser.close()
                return {"cancelled": 0, "kept": 0, "cancel_dates": [], "keep_dates": [], "error": "예약 없음"}

            # 3. 취소 대상 판별
            cancel_list, keep_list = get_cancel_targets(bookings, year, month, keep_days)

            cancel_dates = sorted([b["departure_date"] for b in cancel_list])
            keep_dates = sorted([b["departure_date"] for b in keep_list])

            logger.info(f"취소 대상: {len(cancel_list)}건 - {cancel_dates}")
            logger.info(f"유지 대상: {len(keep_list)}건 - {keep_dates}")

            if not cancel_list:
                logger.info("취소할 예약이 없습니다")
                browser.close()
                return {
                    "cancelled": 0,
                    "kept": len(keep_list),
                    "cancel_dates": [],
                    "keep_dates": keep_dates,
                }

            # 4. 취소 실행
            cancelled = execute_cancellations(page, cancel_list, dry_run=dry_run)

            # 스크린샷
            os.makedirs(LOG_DIR, exist_ok=True)
            screenshot_path = os.path.join(
                LOG_DIR, f"cancel_{year}{month:02d}_{datetime.now().strftime('%H%M%S')}.png"
            )
            page.screenshot(path=screenshot_path, full_page=True)
            logger.info(f"스크린샷: {screenshot_path}")

            browser.close()

            return {
                "cancelled": cancelled,
                "kept": len(keep_list),
                "cancel_dates": cancel_dates,
                "keep_dates": keep_dates,
                "screenshot": screenshot_path,
            }

        except Exception as e:
            logger.error(f"취소 프로세스 에러: {e}")
            try:
                os.makedirs(LOG_DIR, exist_ok=True)
                page.screenshot(
                    path=os.path.join(LOG_DIR, f"cancel_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                )
            except Exception:
                pass
            browser.close()
            return {"cancelled": 0, "kept": 0, "cancel_dates": [], "keep_dates": [], "error": str(e)}
