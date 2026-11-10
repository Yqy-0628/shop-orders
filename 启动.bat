@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo 找不到 python 命令。
  echo 请先装 Python，或者在系统设置里把 Python 加进 PATH。
  echo.
  pause
  exit /b 1
)

if not exist "data\shop.db" (
  echo 数据库不存在，正在重建...
  python scripts\build_db.py
)

echo.
echo 启动中，浏览器会自动打开 http://localhost:8501
echo 账号 boss / 123456（店主）　clerk / 123456（店员）
echo 关掉这个窗口就停止服务。
echo.

start "" http://localhost:8501
python -m streamlit run app.py --server.port 8501 --server.headless true
pause
