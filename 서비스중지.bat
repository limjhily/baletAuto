@echo off
chcp 65001 >nul
echo ========================================
echo   서비스 중지 (로컬 테스트용)
echo ========================================
echo.
echo 서버의 스케줄러 + 봇을 중지합니다.
echo.
ssh -i C:\Users\ebook\.ssh\oracle_baletauto.key.key ubuntu@168.107.26.196 "curl -s -X POST 'https://api.telegram.org/bot8653186098:AAHZdOpq43p2pIH8azUdC0e0u-vbC2cqKk0/sendMessage' -d 'chat_id=8449547453' --data-urlencode 'text=⏹ 서비스 중지됨 (로컬 테스트 모드)' > /dev/null && sudo systemctl stop balet-scheduler balet-bot && echo 서비스 중지 완료!"
echo.
echo ========================================
echo   로컬에서 테스트하세요:
echo   python scheduler.py --bot
echo ========================================
pause
