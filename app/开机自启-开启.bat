@echo off
chcp 936 >nul
title 加入开机自启
cd /d "%~dp0"

set "APPDIR=%~dp0"
set "APPDIR=%APPDIR:~0,-1%"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LNK=%STARTUP%\多平台资源下载工作台.lnk"

powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%LNK%'); $s.TargetPath = $env:SystemRoot + '\System32\wscript.exe'; $s.Arguments = [char]34 + '%APPDIR%\后台启动.vbs' + [char]34; $s.WorkingDirectory = '%APPDIR%'; $s.Description = '多平台资源下载工作台'; $s.Save()"

echo.
if exist "%LNK%" (
  echo 已加入开机自启。
  echo 以后每次开机，下载工作台会在后台自动运行。
  echo 想使用时，双击桌面上的「启动下载工作台.bat」或直接访问：
  echo    http://127.0.0.1:8790
) else (
  echo 添加失败。可以手动把「后台启动.vbs」的快捷方式放进下面这个文件夹：
  echo    %STARTUP%
)
echo.
pause