@echo off
chcp 936 >nul
setlocal
cd /d "%~dp0"

set "EXT=%~dp0扩展_Get-cookies.txt-LOCALLY_v0.7.2"

echo ============================================
echo   Get cookies.txt LOCALLY 扩展安装助手
echo ============================================
echo.

if not exist "%EXT%\manifest.json" (
  echo [错误] 没有找到扩展文件夹：
  echo   %EXT%
  echo 请确认本 bat 和「扩展_Get-cookies.txt-LOCALLY_v0.7.2」文件夹在同一个目录里。
  echo.
  pause
  exit /b 1
)

echo [1/3] 已把扩展文件夹路径复制到剪贴板：
echo   %EXT%
powershell -NoProfile -Command "Set-Clipboard -Value '%EXT%'" >nul 2>&1

echo.
echo [2/3] 正在打开 Chrome 扩展管理页 ...
set "CHROME="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set "CHROME=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"

if defined CHROME (
  start "" "%CHROME%" "chrome://extensions"
) else (
  echo [提示] 没找到 Chrome，请手动打开浏览器并访问 chrome://extensions
)

echo.
echo [3/3] 接下来在 Chrome 里操作：
echo   1. 打开页面右上角的「开发者模式」
echo   2. 点左上角「加载已解压的扩展程序」
echo   3. 在文件夹选择框的地址栏粘贴（Ctrl+V）刚复制的路径，回车
echo   4. 选中该文件夹，列表出现 Get cookies.txt LOCALLY 就成功了
echo.
echo 更详细的图文步骤见同目录的「使用说明.md」。
echo.
pause