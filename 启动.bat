@echo off
setlocal
cd /d "%~dp0"

set "PY="

py -3 -c "import streamlit" >nul 2>nul
if not errorlevel 1 set "PY=py -3"

if not defined PY (
  python -c "import streamlit" >nul 2>nul
  if not errorlevel 1 set "PY=python"
)

if not defined PY (
  echo.
  echo 当前 Python 没有安装 streamlit，正在安装依赖，第一次会慢一点...
  py -3 -m pip install -r requirements.txt
  if not errorlevel 1 set "PY=py -3"
)

if not defined PY (
  echo.
  echo 还是不行，请手动执行：
  echo     py -3 -m pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

echo 使用解释器: %PY%

if not exist "data\shop.db" (
  echo 数据库不存在，正在重建...
  %PY% scripts\build_db.py
)

echo.
echo 启动中，服务就绪后浏览器会自动打开 http://localhost:8501
echo 店主 boss / 123456      店员 clerk / 123456
echo 关掉这个窗口就停止服务。
echo.

%PY% -m streamlit run app.py --server.port 8501 --server.headless false
pause
