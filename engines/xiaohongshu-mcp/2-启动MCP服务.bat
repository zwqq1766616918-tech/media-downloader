@echo off
chcp 936 >nul
cd /d "%~dp0"

REM 与登录脚本共用同一个临时目录，才能复用已保存的登录态
for %%I in ("%~dp0..\..") do set "BASE=%%~fI"
set "TEMP=%BASE%\runtime\temp"
set "TMP=%TEMP%"
if not exist "%TEMP%" mkdir "%TEMP%"

echo ============================================
echo   xiaohongshu-mcp 服务（端口 18060）
echo ============================================
echo.
echo   登录数据目录：%TEMP%\rod
echo   关闭此窗口即停止服务
echo.
xiaohongshu-mcp-windows-amd64.exe
echo.
pause