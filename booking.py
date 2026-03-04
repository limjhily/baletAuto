"""
인천공항 T2 발렛 파킹 자동 예약 - 핵심 예약 로직
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)

# 프로젝트 루트 디렉토리
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")


def load_config(config_path="config.json"):
    """설정 파일 로드"""
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def calculate_dates(base_date=None):
    """
    예약 날짜 계산

    자정 12시에 실행되므로 datetime.now()는 이미 다음 날짜.
    예: 3월 3일 밤 12시 = 3월 4일 00:00 → 예약 대상은 5월 3일
    따라서 (오늘 - 1일) + 2개월 = 정확한 예약 날짜
    """
    if base_date is None:
        base_date = datetime.now()
    # 자정 실행 시 날짜가 이미 넘어갔으므로 하루 빼기
    target_base = base_date - timedelta(days=1)
    departure_date = target_base + relativedelta(months=2)
    return departure_date


def select_dropdown(page, dropdown_el, option_text, field_name=""):
    """
    Element UI 드롭다운에서 옵션 선택
    - 이미 원하는 값이 선택되어 있으면 스킵
    - 드롭다운 열고 visible 옵션 클릭
    """
    try:
        # 현재 선택된 값 확인
        current_input = dropdown_el.locator('input.el-input__inner').first
        current_value = current_input.input_value()

        if current_value == option_text:
            logger.info(f"[{field_name}] '{option_text}' 이미 선택됨 → 스킵")
            return

        # 드롭다운 클릭해서 열기
        dropdown_el.click()
        page.wait_for_timeout(800)

        # 드롭다운 팝업은 body 하단에 렌더링됨 (Element UI 특성)
        # visible한 드롭다운 패널에서 옵션 찾기
        dropdown_panel = page.locator('.el-select-dropdown:visible').last
        option = dropdown_panel.locator(f'.el-select-dropdown__item:has-text("{option_text}")')

        if option.count() > 0:
            option.first.click()
            page.wait_for_timeout(500)
            logger.info(f"[{field_name}] '{option_text}' 선택 완료")
        else:
            # 스크롤이 필요한 긴 리스트일 수 있음
            # 모든 옵션을 순회하며 텍스트 매칭
            all_options = dropdown_panel.locator('.el-select-dropdown__item')
            found = False
            for i in range(all_options.count()):
                opt = all_options.nth(i)
                text = opt.text_content().strip()
                if text == option_text:
                    opt.scroll_into_view_if_needed()
                    page.wait_for_timeout(200)
                    opt.click()
                    page.wait_for_timeout(500)
                    logger.info(f"[{field_name}] '{option_text}' 선택 완료 (스크롤)")
                    found = True
                    break
            if not found:
                raise Exception(f"옵션 '{option_text}'을 찾을 수 없습니다")

    except Exception as e:
        logger.error(f"[{field_name}] '{option_text}' 선택 실패: {e}")
        # 열린 드롭다운 닫기
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        raise


MONTH_MAP = {
    'January': 1, 'February': 2, 'March': 3, 'April': 4,
    'May': 5, 'June': 6, 'July': 7, 'August': 8,
    'September': 9, 'October': 10, 'November': 11, 'December': 12
}


def select_date(page, date_input, target_date, field_name=""):
    """Element UI 날짜 선택기에서 날짜 선택"""
    try:
        # 날짜 입력 필드 클릭 → 달력 열기
        date_input.click()
        page.wait_for_timeout(800)

        target_year = target_date.year
        target_month = target_date.month
        target_day = target_date.day

        # 달력이 표시될 때까지 대기
        date_picker = page.locator('.el-picker-panel:visible').first
        date_picker.wait_for(state="visible", timeout=3000)

        # 현재 달력에 표시된 연/월 확인 후 이동
        max_clicks = 12
        for _ in range(max_clicks):
            # 헤더에서 연도, 월 읽기 (형식: "2026 " "March")
            header_labels = date_picker.locator('.el-date-picker__header-label')
            header_texts = header_labels.all_text_contents()

            current_year = None
            current_month = None

            for text in header_texts:
                text = text.strip()
                # 연도 파싱 (순수 숫자)
                if text.isdigit():
                    current_year = int(text)
                # 영문 월 파싱
                elif text in MONTH_MAP:
                    current_month = MONTH_MAP[text]
                # 한글 형식 (년/월) fallback
                elif '년' in text:
                    current_year = int(text.replace('년', '').strip())
                elif '월' in text:
                    current_month = int(text.replace('월', '').strip())

            # 마지막 fallback: 숫자만 추출
            if current_year is None or current_month is None:
                header_str = " ".join(header_texts)
                nums = re.findall(r'\d+', header_str)
                if len(nums) >= 1 and current_year is None:
                    current_year = int(nums[0])
                if len(nums) >= 2 and current_month is None:
                    current_month = int(nums[1])

            logger.info(f"[{field_name}] 달력: {current_year}년 {current_month}월 → 목표: {target_year}년 {target_month}월")

            if current_year == target_year and current_month == target_month:
                break

            # 앞으로/뒤로 이동 (aria-label 기반)
            target_total = target_year * 12 + target_month
            current_total = current_year * 12 + current_month

            if target_total > current_total:
                next_btn = date_picker.locator('button[aria-label="Next Month"]')
                next_btn.click()
            else:
                prev_btn = date_picker.locator('button[aria-label="Previous Month"]')
                prev_btn.click()

            page.wait_for_timeout(400)

        # 해당 날짜 클릭 - 먼저 available 셀에서 찾기
        day_cells = date_picker.locator('table.el-date-table td.available')
        found = False
        for i in range(day_cells.count()):
            cell = day_cells.nth(i)
            span = cell.locator('span')
            span_text = span.text_content().strip()
            if span_text == str(target_day):
                cell.click()
                page.wait_for_timeout(500)
                logger.info(f"[{field_name}] {target_date.strftime('%Y-%m-%d')} 선택 완료")
                found = True
                break

        if not found:
            # disabled 셀에 해당 날짜가 있는지 확인 (아직 오픈 안 된 날짜)
            disabled_cells = date_picker.locator('table.el-date-table td.disabled')
            for i in range(disabled_cells.count()):
                span_text = disabled_cells.nth(i).locator('span').text_content().strip()
                if span_text == str(target_day):
                    raise Exception(
                        f"날짜 {target_day}일이 비활성화(disabled) 상태입니다. "
                        f"자정 이후 예약 가능합니다."
                    )
            raise Exception(f"날짜 {target_day}일을 달력에서 찾을 수 없습니다")

    except Exception as e:
        logger.error(f"[{field_name}] 날짜 선택 실패: {e}")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        raise


def set_time_field(page, time_input, time_value, field_name=""):
    """시간 입력 필드에 값 설정"""
    try:
        time_input.click(click_count=3)  # 기존 값 전체 선택
        page.wait_for_timeout(200)
        time_input.fill(time_value)
        page.wait_for_timeout(200)
        page.keyboard.press("Tab")  # 포커스 이동으로 값 확정
        page.wait_for_timeout(300)
        logger.info(f"[{field_name}] '{time_value}' 입력 완료")
    except Exception as e:
        logger.error(f"[{field_name}] 시간 입력 실패: {e}")
        raise


def run_booking(config, departure_date, dry_run=False, skip_dates=False):
    """
    예약 실행 메인 함수

    Args:
        skip_dates: True면 날짜/시간 선택을 스킵 (예약이 꽉 찬 경우 테스트용)

    Returns:
        bool: 예약 성공 여부
    """
    arrival_date = departure_date + timedelta(days=config["arrival_days_offset"])

    logger.info("=" * 60)
    logger.info(f"예약 시작: 출발 {departure_date.strftime('%Y-%m-%d')} {config['departure_time']}")
    logger.info(f"         도착 {arrival_date.strftime('%Y-%m-%d')} {config['arrival_time']}")
    if dry_run:
        logger.info("⚠️  드라이런 모드 - 실제 등록하지 않음")
    logger.info("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=not dry_run,  # 드라이런이면 브라우저 표시
            args=['--no-sandbox']
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ko-KR"
        )
        page = context.new_page()

        try:
            # ===== 1. 페이지 접속 =====
            logger.info("예약 페이지 접속 중...")
            page.goto(config["booking_url"], wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)
            logger.info("예약 페이지 로딩 완료")

            # ===== 입력 필드 / 드롭다운 / 체크박스 참조 =====
            inputs = page.locator('input.el-input__inner')
            dropdowns = page.locator('.el-select')
            checkboxes = page.locator('.el-checkbox')

            # ===== 2. 성명 (input[0]) =====
            inputs.nth(0).fill(config["name"])
            logger.info(f"성명: {config['name']}")

            # ===== 3. 휴대전화 (input[1]) =====
            inputs.nth(1).fill(config["phone"])
            logger.info(f"휴대전화: {config['phone']}")

            page.wait_for_timeout(300)

            # ===== 4. 상주 직원 체크 (checkbox[0]) =====
            if config["is_resident_staff"]:
                resident_cb = checkboxes.nth(0)
                if 'is-checked' not in (resident_cb.get_attribute('class') or ''):
                    resident_cb.click()
                    logger.info("상주 직원: 체크")
                else:
                    logger.info("상주 직원: 이미 체크됨")

            page.wait_for_timeout(300)

            # ===== 5. 서비스 유형 (dropdown[0]) - 기본값 '일반' =====
            select_dropdown(page, dropdowns.nth(0), config["service_type"], "서비스 유형")

            page.wait_for_timeout(300)

            # ===== 6. 차량번호 (input[4]) =====
            inputs.nth(4).fill(config["car_number"])
            logger.info(f"차량번호: {config['car_number']}")

            # ===== 7. 차량 모델 (input[5]) =====
            inputs.nth(5).fill(config["car_model"])
            logger.info(f"차량 모델: {config['car_model']}")

            page.wait_for_timeout(300)

            # ===== 8. 차량 브랜드 (dropdown[2]) =====
            select_dropdown(page, dropdowns.nth(2), config["car_brand"], "차량 브랜드")

            page.wait_for_timeout(300)

            # ===== 9. 색상 (dropdown[3]) =====
            select_dropdown(page, dropdowns.nth(3), config["car_color"], "색상")

            page.wait_for_timeout(300)

            # ===== 10. 할인 유형 (dropdown[4]) - 기본값 '일반' =====
            select_dropdown(page, dropdowns.nth(4), config["discount_type"], "할인 유형")

            page.wait_for_timeout(300)

            # ===== 11~14. 출발/도착 일시 + 시간 =====
            if skip_dates:
                logger.info("⏭️ 날짜/시간 선택 스킵 (skip_dates=True)")
            else:
                date_inputs = page.locator('input[placeholder="년도-월-일"]')
                time_inputs = page.locator('.el-date-editor--time-select input.el-input__inner')

                # 출발 날짜
                select_date(page, date_inputs.nth(0), departure_date, "출발 일시")
                page.wait_for_timeout(500)

                # 출발 시간
                set_time_field(page, time_inputs.nth(0), config["departure_time"], "출발 시간")
                page.wait_for_timeout(300)

                # 도착 날짜
                select_date(page, date_inputs.nth(1), arrival_date, "도착 일시")
                page.wait_for_timeout(500)

                # 도착 시간
                set_time_field(page, time_inputs.nth(1), config["arrival_time"], "도착 시간")
                page.wait_for_timeout(300)

            # ===== 15. 출발 항공편 (dropdown[5]) =====
            select_dropdown(page, dropdowns.nth(5), config["departure_airline"], "출발 항공편")

            page.wait_for_timeout(300)

            # ===== 16. 도착 항공편 (있으면) =====
            if dropdowns.count() > 6:
                select_dropdown(page, dropdowns.nth(6), config["arrival_airline"], "도착 항공편")
                page.wait_for_timeout(300)

            # ===== 17. 페이지 하단 스크롤 =====
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(800)

            # ===== 18. 전체 약관 동의 =====
            # "위 약관에 모두 동의합니다" 체크박스 찾기
            agree_all = page.locator('.el-checkbox').filter(has_text="위 약관에 모두 동의합니다")
            if agree_all.count() > 0:
                if 'is-checked' not in (agree_all.first.get_attribute('class') or ''):
                    agree_all.first.click()
                    page.wait_for_timeout(800)
                    logger.info("전체 약관 동의 체크 완료")
            else:
                # 개별 약관 체크
                logger.info("전체 동의 체크박스를 찾을 수 없어 개별 동의 시도")
                for i in range(2, checkboxes.count()):
                    cb = checkboxes.nth(i)
                    if 'is-checked' not in (cb.get_attribute('class') or ''):
                        cb.click()
                        page.wait_for_timeout(300)
                logger.info("개별 약관 동의 체크 완료")

            page.wait_for_timeout(500)

            # ===== 드라이런 모드 =====
            if dry_run:
                # 스크린샷 저장
                os.makedirs(LOG_DIR, exist_ok=True)
                screenshot_path = os.path.join(LOG_DIR, f"dryrun_{departure_date.strftime('%Y%m%d')}.png")
                page.screenshot(path=screenshot_path, full_page=True)
                logger.info(f"🔍 드라이런 완료! 스크린샷: {screenshot_path}")
                logger.info("   30초간 브라우저를 유지합니다. 직접 확인해 주세요.")
                page.wait_for_timeout(30000)
                browser.close()
                return True

            # ===== 19. 등록하기 클릭 =====
            register_btn = page.locator('button.el-button--primary').filter(has_text="등록하기")
            register_btn.click()
            logger.info("등록하기 클릭")

            page.wait_for_timeout(2000)

            # ===== 20. "발렛 예약" 확인 팝업 → 확인 클릭 =====
            try:
                # Element UI MessageBox의 확인 버튼
                popup_confirm = page.locator('.el-message-box__btns .el-button--primary')
                popup_confirm.wait_for(state="visible", timeout=5000)
                popup_confirm.click()
                logger.info("발렛 예약 확인 팝업 → 확인 클릭")
            except:
                # 대체: visible한 '확인' 버튼 찾기
                alt_confirm = page.locator('button:visible').filter(has_text="확인").last
                if alt_confirm.count() > 0:
                    alt_confirm.click()
                    logger.info("확인 팝업 클릭 (대체)")

            page.wait_for_timeout(3000)

            # ===== 21. 예약 검증 =====
            success = verify_booking(page, config, departure_date)
            browser.close()
            return success

        except Exception as e:
            logger.error(f"예약 실패: {e}")
            try:
                os.makedirs(LOG_DIR, exist_ok=True)
                screenshot_path = os.path.join(LOG_DIR, f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                page.screenshot(path=screenshot_path)
                logger.info(f"에러 스크린샷: {screenshot_path}")
            except:
                pass
            browser.close()
            return False


def verify_booking(page, config, departure_date):
    """예약 확인 페이지에서 예약 성공 여부 검증"""
    try:
        logger.info("예약 확인 페이지로 이동...")
        page.goto(config["booking_list_url"], wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        # 차량번호, 휴대폰번호 입력
        inputs = page.locator('input')
        input_count = inputs.count()

        # 차량번호 입력 (첫 번째 input)
        for i in range(input_count):
            inp = inputs.nth(i)
            if inp.is_visible():
                inp.fill(config["car_number"])
                break

        # 휴대폰번호 입력 (두 번째 visible input)
        visible_count = 0
        for i in range(input_count):
            inp = inputs.nth(i)
            if inp.is_visible():
                visible_count += 1
                if visible_count == 2:
                    inp.fill(config["phone"])
                    break

        page.wait_for_timeout(300)

        # 확인 버튼 클릭
        confirm_btn = page.locator('button').filter(has_text="확인").first
        confirm_btn.click()
        page.wait_for_timeout(3000)

        # 출국일 확인
        target_date_str = departure_date.strftime('%Y-%m-%d')
        page_text = page.text_content('body') or ""

        if target_date_str in page_text:
            logger.info(f"✅ 예약 확인 성공! 출국일: {target_date_str}")
            os.makedirs(LOG_DIR, exist_ok=True)
            screenshot_path = os.path.join(LOG_DIR, f"success_{target_date_str}.png")
            page.screenshot(path=screenshot_path)
            logger.info(f"확인 스크린샷: {screenshot_path}")
            return True
        else:
            logger.warning(f"⚠️ 예약 리스트에서 {target_date_str}을 찾을 수 없음")
            os.makedirs(LOG_DIR, exist_ok=True)
            screenshot_path = os.path.join(LOG_DIR, f"verify_fail_{target_date_str}.png")
            page.screenshot(path=screenshot_path)
            return False

    except Exception as e:
        logger.error(f"예약 확인 실패: {e}")
        return False
