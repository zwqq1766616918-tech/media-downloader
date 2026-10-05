@echo off
chcp 936 >nul
title 多平台资源下载工作台
cd /d "%~dp0"

if /i "%~1"=="auto" (set "NOPAUSE=1") else (set "NOPAUSE=")

REM 1) 优先用技能自带的便携 Python（用户电脑上不用装任何东西）
set "BUNDLE=%~dp0..\runtime\python\python.exe"
set "PYEXE="
set "PYARGS="
set "PYNOTE="

if exist "%BUNDLE%" (
  set "PYEXE=%BUNDLE%"
  set "PYARGS=-E"
  set "PYNOTE=自带运行时"
)

REM 2) 没有自带运行时，才回头找本机装的 Python
if not defined PYEXE (
  for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "%ProgramFiles%\Python312\python.exe"
    "%ProgramFiles%\Python311\python.exe"
    "C:\Python312\python.exe"
  ) do (
    if not defined PYEXE if exist %%P set "PYEXE=%%~P"
  )
)
if not defined PYEXE (
  where py >nul 2>&1 && set "PYEXE=py" && set "PYARGS=-3"
)
if not defined PYEXE (
  where python >nul 2>&1 && set "PYEXE=python"
)

if not defined PYEXE (
  echo.
  echo [错误] 既没有找到自带的 runtime\python，也没有找到本机安装的 Python。
  echo.
  echo 请确认解压时保留了完整的 runtime 文件夹；若确实没有自带运行时，
  echo 再自行安装 Python 3（安装时务必勾选 Add Python to PATH）：
  echo   国内镜像下载地址： https://mirrors.huaweicloud.com/python/
  echo.
  if not defined NOPAUSE pause
  exit /b 1
)

echo 使用 Python：%PYEXE%  %PYNOTE%

if not exist "..\config.json" (
  echo.
  echo 检测到还没配置过，先运行一次配置向导...
  echo.
  "%PYEXE%" %PYARGS% "配置向导.py"
  if errorlevel 1 (
    echo 配置向导没有正常结束。
    if not defined NOPAUSE pause
    exit /b 1
  )
)

"%PYEXE%" %PYARGS% "下载工作台.py"
if not defined NOPAUSE pause