@echo off
cd /d "%~dp0"

echo ============================================
echo   AI 秋招情报系统 - 投递管理模式
echo   起本地服务，可录入/更新投递记录（写回数据库）
echo   浏览器会自动打开 http://localhost:5000
echo   改完投递记录后，记得 commit data/jobs.db
echo   关闭此窗口即停止服务
echo ============================================
echo.

python webapp.py

echo.
pause
