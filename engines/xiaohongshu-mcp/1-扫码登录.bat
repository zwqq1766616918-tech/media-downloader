@echo off
chcp 936 >nul
cd /d "%~dp0"

REM 登录临时目录固定到技能目录下，避免系统清理导致登录态丢失
for %%I in ("%~dp0..\..") do set "BASE=%%~fI"
set "TEMP=%BASE%\runtime\temp"
set "TMP=%TEMP%"
if not exist "%TEMP%" mkdir "%TEMP%"

echo ============================================
echo   小红书扫码登录
echo ============================================
echo.
echo   稍后会弹出浏览器窗口，请用小红书 App 扫码登录。
echo   登录数据保存在：%TEMP%\rod
echo   登录成功后关闭浏览器窗口即可。
echo.
xiaohongshu-login-windows-amd64.exe
echo.
pause