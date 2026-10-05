@echo off
chcp 936 >nul
title 取消开机自启
cd /d "%~dp0"

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LNK=%STARTUP%\多平台资源下载工作台.lnk"

if exist "%LNK%" (
  del /f /q "%LNK%"
  echo 已取消开机自启。
) else (
  echo 本来就没有设置开机自启，无需取消。
)
echo.
pause