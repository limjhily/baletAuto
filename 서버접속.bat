@echo off
chcp 65001 >nul
echo ========================================
echo   Oracle 서버 SSH 접속
echo ========================================
echo.
ssh -i C:\Users\ebook\.ssh\oracle_baletauto.key.key ubuntu@168.107.26.196
pause
