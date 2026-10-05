@echo off
chcp 936 >nul
title 安装浏览器（抖音需要）
cd /d "%~dp0"

echo ============================================
echo   检查浏览器
echo ============================================
echo.

set "BROWSER="
if not defined BROWSER if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set "BROWSER=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "BROWSER=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "BROWSER=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER if exist "%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe" set "BROWSER=%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"
if not defined BROWSER if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "BROWSER=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not defined BROWSER if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "BROWSER=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"

if not defined BROWSER (
  for /f "delims=" %%F in ('dir /b /s "%~dp0..\browser\chrome.exe" 2^>nul') do if not defined BROWSER set "BROWSER=%%F"
)
if not defined BROWSER (
  for /f "delims=" %%F in ('dir /b /s "%~dp0..\browser\msedge.exe" 2^>nul') do if not defined BROWSER set "BROWSER=%%F"
)

if defined BROWSER (
  echo [√] 已经检测到浏览器，无需再装：
  echo     %BROWSER%
  echo.
  echo 抖音可以直接用了。回到下载工作台页面，状态灯会自动变绿。
  echo.
  pause
  exit /b 0
)

echo [×] 这台电脑上没找到 Chrome 或 Edge。
echo     抖音下载需要一个真实浏览器（用来生成签名、保存登录态）。
echo     本包不再自带浏览器内核（那样要多占 400 多 MB），改成用你自己装的。
echo.
echo 下面三种办法任选一种，推荐第 1 种：
echo.
echo   1) 先用 Edge —— Win10 / Win11 基本都自带
echo      点开始菜单，搜索 Edge，能打开就直接用。
echo      然后回来重新双击本脚本，让它确认一下就行。
echo.
echo   2) 装官方 Chrome 离线包（安装时不需要联网）
echo      下面会自动帮你打开下载页，选「下载 Chrome」即可。
echo.
echo   3) 便携版（免安装、解压即用，国内直连最快）
echo      打开： https://registry.npmmirror.com/binary.html?path=chrome-for-testing/
echo      进 win64 目录，下载 chrome-win64.zip，解压后把整个 chrome-win64
echo      文件夹放到这个位置：
echo          %~dp0..\browser\
echo      放好后再重新双击本脚本，就能自动认出来。
echo.

start "" "https://www.google.cn/chrome/?standalone=1&platform=win64"

echo 装完 / 放好之后，重新双击本脚本验证一次即可。
echo.
pause