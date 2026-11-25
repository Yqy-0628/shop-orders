@echo off
chcp 65001 >nul
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
  echo 当前 Python 没有安装 streamlit，正在安装依赖，装完会自动再启动一次...
  py -3 -m pip install -r requirements.txt
  if not errorlevel 1 set "PY=py -3"
)

if not defined PY (
  echo.
  echo 仍然不行，请手动执行：
  echo     py -3 -m pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

echo 使用解释器: %PY%

if not exist "data\shop.db" (
  echo 数据库不存在，正在用脚本重建...
  %PY% scripts\build_db.py
)

echo.
echo 正在启动，浏览器会自动打开 http://localhost:8501
echo 店长 boss / 123456      店员 clerk / 123456
echo 关掉这个窗口即停止服务
echo.

%PY% -m streamlit run app.py --server.port 8501 --server.headless false
pause
