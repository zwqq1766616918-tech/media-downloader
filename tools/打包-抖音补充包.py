# -*- coding: utf-8 -*-
"""把本机已装好的 MediaCrawler 打包成 media-downloader 的「抖音补充包」。

为什么单独打包：
    抖音走 MediaCrawler，它的依赖是 Python 3.11 编译的（技能自带运行时是 3.12，
    二进制扩展不通用），加起来约 600 MB。所以不放进主包 —— 装不装都不影响其它五个平台。

浏览器内核不打包：
    抖音需要一个真实浏览器来生成请求签名、保存扫码登录态。以前是把 Playwright 的
    Chromium 内核（约 400MB）一起塞进包里，现在改成用**用户本机已装的 Chrome / Edge**
    （MediaCrawler 侧读环境变量 MC_BROWSER_PATH），所以包里不再带内核。
    用户没装浏览器时，引导他双击 app\\安装浏览器.bat 即可。

用法（在技能目录下执行）：
    python tools/打包-抖音补充包.py                 # 自动找 MediaCrawler 并打包
    python tools/打包-抖音补充包.py --src <目录>     # 指定 MediaCrawler 目录
    python tools/打包-抖音补充包.py --dry-run        # 只统计体积，不复制
    python tools/打包-抖音补充包.py --launchers      # 只重写启动脚本（不需要本机 MediaCrawler）
    python tools/打包-抖音补充包.py --clean          # 删掉已打包的抖音补充包

产出（技能目录内）：
    engines/mediacrawler/          MediaCrawler 源码 + 启动脚本
    runtime/python311/             便携 Python 3.11（跑 MediaCrawler 用）
    runtime/pkgs/mediacrawler/     MediaCrawler 的依赖

打包完再跑一次「配置向导」，抖音就会自动接上。

隐私：会剔除 data / browser_data / cache / __pycache__ / .venv 等运行产物，
      不会把下载内容、浏览器登录态带进包里。
"""
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)

ENGINES_DIR = os.path.join(SKILL_DIR, "engines")
MC_DEST = os.path.join(ENGINES_DIR, "mediacrawler")
PY311_DEST = os.path.join(SKILL_DIR, "runtime", "python311")
PKG_DEST = os.path.join(SKILL_DIR, "runtime", "pkgs", "mediacrawler")
# 老版本补充包里放过的 Playwright 内核；现在不再打包，只用于 --clean 清理
BROWSERS_DEST = os.path.join(SKILL_DIR, "playwright-browsers")

# 源码里不打包的**顶层**目录（运行产物 / 个人数据 / 无关文档）
# 注意两点：
#   1. 只按顶层排除 —— webui/src/components/data 这类嵌套同名目录要保留
#   2. 别把源码包当产物排除 —— 比如 cache/ 里是 abs_cache.py，是代码不是缓存
SRC_SKIP_TOP = {
    ".venv", "data", "browser_data", ".git", ".github",
    "test", "tests", "docs", "webui", "node_modules", "logs",
}
# site-packages 里不打包的顶层目录
PKG_SKIP_TOP = {"__pycache__", "pip", "setuptools", "wheel", "_distutils_hack", "pkg_resources"}

SITECUSTOMIZE = '''# -*- coding: utf-8 -*-
"""抖音补充包引导：把 runtime/pkgs/mediacrawler 作为附加 site 目录加载。"""
import os
import site

_HERE = os.path.dirname(os.path.abspath(__file__))
_RUNTIME = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
for _name in ("mediacrawler",):
    _dir = os.path.join(_RUNTIME, "pkgs", _name)
    if os.path.isdir(_dir):
        site.addsitedir(_dir)
'''

# MediaCrawler 自带的两个 bat 依赖 uv（用户机器上没有），打包时重写成用自带运行时。
# 浏览器用用户本机已装的 Chrome / Edge（本包不带内核），找不到就提示去装。
LAUNCHER = '''@echo off
chcp 936 >nul
title MediaCrawler - {title}
cd /d "%~dp0"

set "PY=%~dp0..\\..\\runtime\\python311\\python.exe"
if not exist "%PY%" (
  echo [错误] 没找到自带运行时：%PY%
  echo        请先在技能目录下运行 tools\\打包-抖音补充包.py 完成打包。
  pause
  exit /b 1
)

rem 抖音需要一个真实浏览器（本包不带内核）：优先用本机已装的 Chrome / Edge
set "MC_BROWSER_PATH="
if not defined MC_BROWSER_PATH if exist "%LOCALAPPDATA%\\Google\\Chrome\\Application\\chrome.exe" set "MC_BROWSER_PATH=%LOCALAPPDATA%\\Google\\Chrome\\Application\\chrome.exe"
if not defined MC_BROWSER_PATH if exist "%ProgramFiles%\\Google\\Chrome\\Application\\chrome.exe" set "MC_BROWSER_PATH=%ProgramFiles%\\Google\\Chrome\\Application\\chrome.exe"
if not defined MC_BROWSER_PATH if exist "%ProgramFiles(x86)%\\Google\\Chrome\\Application\\chrome.exe" set "MC_BROWSER_PATH=%ProgramFiles(x86)%\\Google\\Chrome\\Application\\chrome.exe"
if not defined MC_BROWSER_PATH if exist "%LOCALAPPDATA%\\Microsoft\\Edge\\Application\\msedge.exe" set "MC_BROWSER_PATH=%LOCALAPPDATA%\\Microsoft\\Edge\\Application\\msedge.exe"
if not defined MC_BROWSER_PATH if exist "%ProgramFiles%\\Microsoft\\Edge\\Application\\msedge.exe" set "MC_BROWSER_PATH=%ProgramFiles%\\Microsoft\\Edge\\Application\\msedge.exe"
if not defined MC_BROWSER_PATH if exist "%ProgramFiles(x86)%\\Microsoft\\Edge\\Application\\msedge.exe" set "MC_BROWSER_PATH=%ProgramFiles(x86)%\\Microsoft\\Edge\\Application\\msedge.exe"
if not defined MC_BROWSER_PATH (
  for /f "delims=" %%F in ('dir /b /s "%~dp0..\\..\\browser\\chrome.exe" 2^>nul') do if not defined MC_BROWSER_PATH set "MC_BROWSER_PATH=%%F"
)

if not defined MC_BROWSER_PATH (
  echo.
  echo [提示] 没找到 Chrome / Edge。抖音需要一个浏览器才能跑。
  echo        请先双击技能目录下的  app\\安装浏览器.bat  按引导安装。
  echo.
  pause
  exit /b 1
)

rem 抖音签名脚本要一个 JS 运行时；Playwright 驱动里自带 node.exe，直接顶上
set "MCNODE=%~dp0..\\..\\runtime\\pkgs\\mediacrawler\\playwright\\driver"
if exist "%MCNODE%\\node.exe" set "PATH=%MCNODE%;%PATH%"

echo ============================================
echo   MediaCrawler - {title}
echo ============================================
echo.
echo 用法：把{what}链接粘贴进来，然后回车。
echo 示例：{sample}
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

"%PY%" main.py --platform {pf} --lt qrcode {args} --get_media yes --get_comment no --save_data_option jsonl

echo.
echo 采集结束。数据保存在 data 目录下。
pause
'''

LAUNCHERS = {
    "1-采集小红书作者主页.bat": {
        "title": "小红书作者主页采集",
        "what": "小红书作者",
        "sample": "https://www.xiaohongshu.com/user/profile/xxxxxxxx?xsec_token=xxxx&xsec_source=pc_user",
        "pf": "xhs",
        "args": '--type creator --creator_id "%TARGET%" --crawler_max_notes_count 50',
    },
    "2-采集抖音作者主页.bat": {
        "title": "抖音作者主页采集",
        "what": "抖音作者",
        "sample": "https://www.douyin.com/user/MS4wLjABAAAAxxxxxxxx",
        "pf": "dy",
        "args": '--type creator --creator_id "%TARGET%" --crawler_max_notes_count 50',
    },
    "3-下载抖音单条作品.bat": {
        "title": "抖音单条作品下载",
        "what": "抖音作品（视频 / 图文的分享链接都行）",
        "sample": "https://www.douyin.com/video/7525082444551310602",
        "pf": "dy",
        "args": '--type detail --specified_id "%TARGET%"',
    },
}


def make_ignore(root, top_skip):
    """顶层的运行产物整目录跳过；__pycache__ 与 .pyc 任意层级都跳过。"""
    root = os.path.normpath(root)

    def _ignore(dirpath, names):
        out = set()
        at_root = os.path.normpath(dirpath) == root
        for n in names:
            if n == "__pycache__" or n.endswith(".pyc"):
                out.add(n)
            elif at_root and n in top_skip:
                out.add(n)
        return out

    return _ignore


def sizeof(path, top_skip=()):
    """统计目录体积，按同样的排除规则计算，避免把 .venv 也算进去。"""
    path = os.path.normpath(path)
    total = 0
    for cur, dirs, files in os.walk(path):
        if os.path.normpath(cur) == path:
            dirs[:] = [d for d in dirs if d not in top_skip]
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith(".pyc"):
                continue
            try:
                total += os.path.getsize(os.path.join(cur, f))
            except OSError:
                pass
    return total


def mb(n):
    return "%.1f MB" % (n / 1024.0 / 1024.0)


def find_mediacrawler():
    """在本机常见位置找 MediaCrawler（含 main.py 的那个目录）。"""
    cands = []
    # 从技能目录逐级往上找 05_工具\xhs-tools\MediaCrawler
    d = SKILL_DIR
    for _ in range(5):
        cands.append(os.path.join(d, "05_工具", "xhs-tools", "MediaCrawler"))
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    cands += [
        os.path.join(os.path.expanduser("~"), "MediaCrawler"),
        os.path.join(os.path.expanduser("~"), "Downloads", "MediaCrawler"),
    ]
    for c in cands:
        c = os.path.abspath(c)
        if os.path.isfile(os.path.join(c, "main.py")):
            return c
    return ""


def write_launchers():
    """在打包出来的源码目录里写好启动脚本（用自带运行时，不依赖 uv）。"""
    if not os.path.isdir(MC_DEST):
        sys.exit("[×] 还没有 %s，请先完整打包一次再单独重写启动脚本" % MC_DEST)

    # 先删掉原来自带的 bat（它们依赖 uv，用户机器上没有，留着只会让人双击报错）
    # 注意必须先删再写：新脚本里有一个和旧脚本同名
    for stale in ("1-采集作者主页.bat", "2-采集抖音作者主页.bat",
                  "3-下载抖音单条作品.bat"):
        p = os.path.join(MC_DEST, stale)
        if os.path.isfile(p):
            os.remove(p)

    for name, info in LAUNCHERS.items():
        text = LAUNCHER.format(**info)
        text = text.replace("\r\n", "\n").replace("\n", "\r\n")
        path = os.path.join(MC_DEST, name)
        with open(path, "w", encoding="gbk", newline="") as fh:
            fh.write(text)
        print("[打包] 启动脚本 → %s" % path)


def build(src, dry_run=False):
    venv = os.path.join(src, ".venv")
    site_packages = os.path.join(venv, "Lib", "site-packages")
    cfg_file = os.path.join(venv, "pyvenv.cfg")

    if not os.path.isfile(os.path.join(src, "main.py")):
        sys.exit("[×] 这不像 MediaCrawler 目录（没有 main.py）：%s" % src)
    if not os.path.isdir(site_packages):
        sys.exit("[×] 没找到 %s，请先在 MediaCrawler 目录里装好依赖（uv sync）" % site_packages)
    if not os.path.isfile(cfg_file):
        sys.exit("[×] 没找到 %s，无法定位它用的 Python 解释器" % cfg_file)

    base_py = ""
    with open(cfg_file, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip().lower().startswith("home"):
                base_py = line.split("=", 1)[1].strip()
                break
    if not base_py or not os.path.isfile(os.path.join(base_py, "python.exe")):
        sys.exit("[×] pyvenv.cfg 里的 home 指向的解释器不存在：%s" % base_py)

    print("")
    print("MediaCrawler 目录 : %s" % src)
    print("Python 3.11 基础   : %s" % base_py)
    print("浏览器             : 用用户本机已装的 Chrome / Edge（不打包内核）")
    print("")

    items = [
        ("源码", src, MC_DEST, SRC_SKIP_TOP),
        ("Python 3.11", base_py, PY311_DEST, set()),
        ("依赖包", site_packages, PKG_DEST, PKG_SKIP_TOP),
    ]
    total = 0
    for label, s, d, skip in items:
        n = sizeof(s, skip)
        total += n
        print("  %-12s %10s" % (label, mb(n)))
    print("  %-12s %10s" % ("合计", mb(total)))
    print("")

    if dry_run:
        print("（试运行，未复制任何文件）")
        return

    for label, s, d, skip in items:
        print("[打包] %s → %s" % (label, d))
        shutil.copytree(s, d, dirs_exist_ok=True, ignore=make_ignore(s, skip))

    write_launchers()

    # 3.11 运行时挂载依赖包组
    sc = os.path.join(PY311_DEST, "Lib", "site-packages", "sitecustomize.py")
    os.makedirs(os.path.dirname(sc), exist_ok=True)
    with open(sc, "w", encoding="utf-8") as fh:
        fh.write(SITECUSTOMIZE)

    # 老版本可能残留 Playwright 内核，顺手清掉（不再需要）
    if os.path.isdir(BROWSERS_DEST):
        n = sizeof(BROWSERS_DEST)
        shutil.rmtree(BROWSERS_DEST, ignore_errors=True)
        print("[清理] 移除旧的浏览器内核 %s（%s）—— 现在改用本机浏览器" % (BROWSERS_DEST, mb(n)))

    print("")
    print("[√] 抖音补充包已就绪，体积约 %s" % mb(total))
    print("    接着跑一次「配置向导」，抖音状态灯会变绿。")
    print("    抖音需要浏览器：本机没装 Chrome / Edge 时，双击 app\\安装浏览器.bat。")
    print("")


def clean():
    targets = [MC_DEST, PY311_DEST, PKG_DEST, BROWSERS_DEST]
    for t in targets:
        if os.path.isdir(t):
            n = sizeof(t)
            shutil.rmtree(t)
            print("[删除] %s（%s）" % (t, mb(n)))
    # 3.12 运行时的 sitecustomize 不挂 mediacrawler，无需处理
    print("[√] 已移除抖音补充包（其它平台不受影响）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="", help="MediaCrawler 目录（含 main.py）")
    ap.add_argument("--dry-run", action="store_true", help="只统计体积，不复制")
    ap.add_argument("--launchers", action="store_true",
                    help="只重写启动脚本（不需要本机装有 MediaCrawler）")
    ap.add_argument("--clean", action="store_true", help="删除已打包的抖音补充包")
    args = ap.parse_args()

    if args.clean:
        clean()
        return
    if args.launchers:
        write_launchers()
        return

    src = os.path.abspath(args.src) if args.src else find_mediacrawler()
    if not src:
        sys.exit("找不到 MediaCrawler 目录，请用 --src 指定（该目录里应有 main.py 和 .venv）")
    build(src, dry_run=args.dry_run)


if __name__ == "__main__":
    main()