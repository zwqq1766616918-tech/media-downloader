@echo off
chcp 936 >nul
title 配置向导
cd /d "%~dp0"

set "BUNDLE=%~dp0..\runtime\python\python.exe"
set "PYEXE="
set "PYARGS="

if exist "%BUNDLE%" (
  set "PYEXE=%BUNDLE%"
  set "PYARGS=-E"
)

if not defined PYEXE (
  for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "%ProgramFiles%\Python312\python.exe"
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
  echo [错误] 没有找到可用的 Python（自带运行时或本机安装的都没有）。
  echo   自带运行时缺失时，可安装 Python 3： https://mirrors.huaweicloud.com/python/
  echo.
  pause
  exit /b 1
)

"%PYEXE%" %PYARGS% "配置向导.py"
echo.
pause