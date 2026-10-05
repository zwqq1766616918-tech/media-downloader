@echo off
chcp 936 >nul
title MediaCrawler - 小红书作者主页采集
cd /d "%~dp0"

set "PY=%~dp0..\..\runtime\python311\python.exe"
if not exist "%PY%" (
  echo [错误] 没找到自带运行时：%PY%
  echo        请先在技能目录下运行 tools\打包-抖音补充包.py 完成打包。
  pause
  exit /b 1
)

rem 抖音需要一个真实浏览器（本包不带内核）：优先用本机已装的 Chrome / Edge
set "MC_BROWSER_PATH="
if not defined MC_BROWSER_PATH if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set "MC_BROWSER_PATH=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
if not defined MC_BROWSER_PATH if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "MC_BROWSER_PATH=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined MC_BROWSER_PATH if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "MC_BROWSER_PATH=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined MC_BROWSER_PATH if exist "%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe" set "MC_BROWSER_PATH=%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"
if not defined MC_BROWSER_PATH if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "MC_BROWSER_PATH=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not defined MC_BROWSER_PATH if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "MC_BROWSER_PATH=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not defined MC_BROWSER_PATH (
  for /f "delims=" %%F in ('dir /b /s "%~dp0..\..\browser\chrome.exe" 2^>nul') do if not defined MC_BROWSER_PATH set "MC_BROWSER_PATH=%%F"
)

if not defined MC_BROWSER_PATH (
  echo.
  echo [提示] 没找到 Chrome / Edge。抖音需要一个浏览器才能跑。
  echo        请先双击技能目录下的  app\安装浏览器.bat  按引导安装。
  echo.
  pause
  exit /b 1
)

echo ============================================
echo   MediaCrawler - 小红书作者主页采集
echo ============================================
echo.
echo 用法：把小红书作者链接粘贴进来，然后回车。
echo 示例：https://www.xiaohongshu.com/user/profile/xxxxxxxx?xsec_token=xxxx&xsec_source=pc_user
echo.
set /p TARGET=请粘贴链接后回车：

if "%TARGET%"=="" (
    echo.
    echo [退出] 没有输入链接。
    pause
    exit /b
)

echo.
echo [提示] 首次使用会弹出浏览器，请用对应 App 扫码登录。
echo        扫码后若出现滑块或手机号验证，请手动完成。
echo        登录成功后会自动开始采集，请勿关闭窗口。
echo.

"%PY%" main.py --platform xhs --lt qrcode --type creator --creator_id "%TARGET%" --crawler_max_notes_count 50 --get_media yes --get_comment no --save_data_option jsonl

echo.
echo 采集结束。数据保存在 data 目录下。
pause
