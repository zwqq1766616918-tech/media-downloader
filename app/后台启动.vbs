' 后台静默启动下载工作台（不弹黑窗口、不自动开浏览器）
Option Explicit
Dim sh, fso, here
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = here
sh.Environment("PROCESS")("MD_NO_BROWSER") = "1"
sh.Run """" & here & "\启动下载工作台.bat"" auto", 0, False