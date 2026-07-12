@echo off
cd /d "%~dp0"

echo ============================================
echo   AI 秋招情报系统 - 启动中...
echo   抓取岗位 - DeepSeek 分析 - 生成报告 - 推送飞书
echo   跑完会自动打开当日报告网页
echo ============================================
echo.

if "%DEEPSEEK_API_KEY%"=="" (
    echo [提醒] 未检测到环境变量 DEEPSEEK_API_KEY，
    echo        本次运行将尝试读取项目 .env；若仍未配置，将无法调用 DeepSeek 分析（岗位仍会抓取入库）。
    echo        设置方法见 CLAUDE.md。
    echo.
)

python main.py

echo.
echo ============================================
echo   运行结束。报告已保存到 reports 目录。
echo ============================================
pause

