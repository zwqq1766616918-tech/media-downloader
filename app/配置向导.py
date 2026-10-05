# -*- coding: utf-8 -*-
"""配置向导 —— 优先使用技能自带的便携运行时与引擎，其次才扫描本机环境，生成 config.json。

用法：
    python 配置向导.py            # 交互式，逐项确认
    python 配置向导.py --check    # 只体检，不写配置
    python 配置向导.py --yes      # 全自动，直接写入探测结果

设计要点：
    * 技能自带 runtime/（便携 Python + 预装依赖）和 engines/（下载引擎）时，
      一律优先使用自带版本 —— 用户电脑上**不需要装过任何东西**，真正做到开箱即用。
    * 只有自带件缺失时，才回退到扫描本机常见目录（老用户 / 自己装了引擎的场景）。
    * 抖音 MediaCrawler 体积过大，作为可选补充包单独安装；它需要的浏览器**不随包分发**，
      改用用户本机已装的 Chrome / Edge（没有就引导双击 app\\安装浏览器.bat）。
    * 本文件不写死任何机器路径，也不读取、复制任何 Cookie 内容，只记录 Cookie 文件的路径。
"""
import argparse
import json
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(APP_DIR)
WORKSPACE = os.path.abspath(os.path.join(APP_DIR, "..", "..", "..", ".."))
CONFIG_FILE = os.path.join(SKILL_DIR, "config.json")

# ---------------- 技能自带的便携运行时 / 引擎 ----------------
RUNTIME_DIR = os.path.join(SKILL_DIR, "runtime")
BUNDLE_PY = os.path.join(RUNTIME_DIR, "python", "python.exe")
ENGINES_DIR = os.path.join(SKILL_DIR, "engines")
BUNDLE_TIKTOK = os.path.join(ENGINES_DIR, "tiktok", "tiktok_dl.py")
BUNDLE_XHS_DIR = os.path.join(ENGINES_DIR, "xhs-downloader")
BUNDLE_MCP_DIR = os.path.join(ENGINES_DIR, "xiaohongshu-mcp")
# 抖音补充包（可选，体积大）：源码目录 + 依赖包组（浏览器不打包，用本机的）
BUNDLE_MC_DIR = os.path.join(ENGINES_DIR, "mediacrawler")
# 用户自己解压的便携版浏览器（npmmirror 的 chrome-win64.zip）
PORTABLE_BROWSER_DIR = os.path.join(SKILL_DIR, "browser")
# 用户自己导出的 cookies.txt 统一放这里（各平台一个子目录）
COOKIE_ROOT = os.path.join(SKILL_DIR, "cookies")
COOKIE_PLATFORMS = ("twitter", "instagram", "weibo", "tiktok")

SKIP_DIRS = {
    "node_modules", "site-packages", "__pycache__", ".git", "Lib", "include",
    "dist-info", ".idea", ".vscode", "dist", "build",
    # 体积大、且不可能存放引擎的产物目录，扫描时跳过（通用名，不含任何个人习惯）
    "downloads", "download", "output", "outputs", "results", "logs", "log",
    "data", "media", "models", "cache", "tmp", "temp",
    "下载", "运行记录", "输出", "日志", "模型", "素材", "数据集", "图片", "视频",
}

TARGETS = {
    "gallery_dl": ["gallery-dl.exe", "gallery-dl"],
    "yt_dlp": ["yt-dlp.exe", "yt-dlp"],
    "uv": ["uv.exe", "uv"],
    "tiktok_dl": ["tiktok_dl.py"],
    "xhs_core": ["xhs_core.py"],
    "mediacrawler": ["main.py"],
    "mcp_exe": ["xiaohongshu-mcp-windows-amd64.exe"],
}

COOKIE_HINTS = {
    "twitter": ["twitter-tools", "twitter"],
    "instagram": ["instagram-tools", "instagram"],
    "weibo": ["weibo-tools", "weibo"],
    "tiktok": ["tiktok-tools", "tiktok"],
}

# 扫描预算：避免误入超大的素材目录导致卡死
SCAN_BUDGET = {"used": 0, "limit": 40000}


def bundle_ready():
    """技能是否自带可用的便携运行时 + 引擎。"""
    return os.path.isfile(BUNDLE_PY) and os.path.isdir(ENGINES_DIR)


def walk_find(roots, names, max_depth=7, limit=1):
    """在 roots 下按目录名/文件名查找，返回最多 limit 个绝对路径。"""
    found = []
    want = {n.lower() for n in names}
    for root in roots:
        if not os.path.isdir(root):
            continue
        base_depth = root.rstrip("\\/").count(os.sep)
        for cur, dirs, files in os.walk(root):
            SCAN_BUDGET["used"] += 1
            if SCAN_BUDGET["used"] > SCAN_BUDGET["limit"]:
                return found
            depth = cur.rstrip("\\/").count(os.sep) - base_depth
            if depth >= max_depth:
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith("_")]
            for d in list(dirs):
                if d.lower() in want:
                    found.append(os.path.join(cur, d))
                    if len(found) >= limit:
                        return found
            for f in files:
                if f.lower() in want:
                    found.append(os.path.join(cur, f))
                    if len(found) >= limit:
                        return found
    return found


def find_portable_browser():
    """技能目录下 browser\\ 里用户自己解压的便携版浏览器（npmmirror 的 zip）。"""
    if not os.path.isdir(PORTABLE_BROWSER_DIR):
        return ""
    for cur, dirs, files in os.walk(PORTABLE_BROWSER_DIR):
        if cur[len(PORTABLE_BROWSER_DIR):].count(os.sep) > 3:
            dirs[:] = []
            continue
        for f in files:
            if f.lower() in ("chrome.exe", "msedge.exe"):
                return os.path.join(cur, f)
    return ""


def find_chrome():
    """找本机可用的 Chromium 系浏览器（抖音要用它生成签名、保存扫码登录态）。"""
    pf = os.environ.get("PROGRAMFILES", "")
    pf86 = os.environ.get("PROGRAMFILES(X86)", "")
    la = os.environ.get("LOCALAPPDATA", "")
    cands = [
        os.path.join(la, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(pf86, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(la, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(pf86, "Microsoft", "Edge", "Application", "msedge.exe"),
    ]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return find_portable_browser()


def venv_python_near(path):
    """给定一个工具目录或文件，找出它所在工具目录下的 .venv python。"""
    if not path:
        return ""
    d = path if os.path.isdir(path) else os.path.dirname(path)
    for _ in range(4):
        for sub in (("Scripts", "python.exe"), ("bin", "python")):
            cand = os.path.join(d, ".venv", *sub)
            if os.path.isfile(cand):
                return cand
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return ""


def cookie_in(tool_dir):
    if not tool_dir or not os.path.isdir(tool_dir):
        return ""
    for name in ("cookies.txt", "cookie.txt"):
        p = os.path.join(tool_dir, name)
        if os.path.isfile(p):
            return p
    return ""


def python_script_dirs():
    """常见 Python 安装目录下的 Scripts（uv / gallery-dl 等可能装在这里）。"""
    import glob
    pats = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python*", "Scripts"),
        os.path.join(os.environ.get("APPDATA", ""), "Python", "Python*", "Scripts"),
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Python*", "Scripts"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Python*", "Scripts"),
        r"C:\Python*\Scripts",
    ]
    out = []
    for p in pats:
        out += glob.glob(p)
    return [d for d in out if os.path.isdir(d)]


def bundled_cookie(platform):
    """自带模式下 cookies.txt 的约定位置。"""
    return os.path.join(COOKIE_ROOT, platform, "cookies.txt")


def detect_local():
    """扫描本机（仅在不使用自带引擎时才需要）。"""
    SCAN_BUDGET["used"] = 0
    roots = [WORKSPACE, SKILL_DIR]
    roots += python_script_dirs()
    for extra in (os.path.join(os.path.expanduser("~"), "Downloads"),):
        if os.path.isdir(extra):
            roots.append(extra)

    res = {"engines": {}, "platforms": {}, "chrome_path": "", "found_dirs": {}}
    res["chrome_path"] = find_chrome()

    gd = walk_find(roots, TARGETS["gallery_dl"])
    yt = walk_find(roots, TARGETS["yt_dlp"])
    uv = walk_find(roots, TARGETS["uv"])
    tk = walk_find(roots, TARGETS["tiktok_dl"])
    xhs = walk_find(roots, TARGETS["xhs_core"])
    mc = walk_find(roots, TARGETS["mediacrawler"], max_depth=5)
    mcp = walk_find(roots, TARGETS["mcp_exe"], max_depth=5)

    res["engines"]["gallery_dl"] = gd[0] if gd else ""
    res["engines"]["yt_dlp"] = yt[0] if yt else ""
    res["engines"]["uv"] = uv[0] if uv else ""
    res["engines"]["tiktok_dl"] = tk[0] if tk else ""
    res["engines"]["tiktok_python"] = venv_python_near(tk[0]) if tk else ""

    if xhs:
        res["engines"]["xhs_python"] = venv_python_near(xhs[0])
        res["found_dirs"]["xhs"] = os.path.dirname(xhs[0])

    if mc:
        res["found_dirs"]["douyin"] = os.path.dirname(mc[0])

    # 各平台工具目录 + cookies.txt
    for key, names in COOKIE_HINTS.items():
        hit = walk_find(roots, names, max_depth=4)
        if hit:
            d = hit[0]
            res["platforms"].setdefault(key, {})["workdir"] = d
            ck = cookie_in(d)
            if ck:
                res["platforms"][key]["cookie"] = ck
            cfg = os.path.join(d, "config.json")
            if os.path.isfile(cfg):
                res["platforms"][key]["config"] = cfg

    # 小红书 MCP
    if mcp:
        d = os.path.dirname(mcp[0])
        res["platforms"].setdefault("xhs", {})["mcp"] = "http://localhost:18060"
        res["found_dirs"]["mcp"] = d
        ck = os.path.join(d, "cookies.json")
        if os.path.isfile(ck):
            res["platforms"]["xhs"]["cookie"] = ck

    res["platforms"].setdefault("xhs", {})["workdir"] = res["found_dirs"].get("xhs", "")
    res["platforms"].setdefault("douyin", {})["workdir"] = res["found_dirs"].get("douyin", "")
    return res


def build_config(found):
    """组装最终配置。自带运行时优先，本机扫描结果作为兜底。"""
    use_bundle = bundle_ready()
    py = BUNDLE_PY if use_bundle else ""

    cfg = {
        "port": 8790,
        "output_dir": "下载",
        "open_browser": True,
        "chrome_path": found.get("chrome_path", ""),
        "runtime": {"python": py, "bundled": use_bundle},
        "engines": {
            "gallery_dl": found["engines"].get("gallery_dl", ""),
            "yt_dlp": found["engines"].get("yt_dlp", ""),
            "uv": found["engines"].get("uv", ""),
            "xhs_python": found["engines"].get("xhs_python", ""),
            "tiktok_dl": found["engines"].get("tiktok_dl", ""),
            "tiktok_python": found["engines"].get("tiktok_python", ""),
        },
        "platforms": {
            "twitter": {"cookie": "", "config": "", "workdir": ""},
            "instagram": {"cookie": "", "config": "", "workdir": ""},
            "weibo": {"cookie": "", "config": "", "workdir": ""},
            "tiktok": {"cookie": "", "workdir": ""},
            "douyin": {"workdir": ""},
            "xhs": {"cookie": "", "workdir": "", "mcp": "http://localhost:18060"},
        },
    }

    # 本机扫描结果先铺底
    for key, val in (found.get("platforms") or {}).items():
        cfg["platforms"].setdefault(key, {}).update(val)

    # 自带运行时覆盖：引擎全部指向包内，用户无需装任何东西
    if use_bundle:
        cfg["engines"]["tiktok_python"] = py
        if os.path.isfile(BUNDLE_TIKTOK):
            cfg["engines"]["tiktok_dl"] = BUNDLE_TIKTOK
        if os.path.isdir(BUNDLE_XHS_DIR):
            cfg["engines"]["xhs_python"] = py
            cfg["platforms"]["xhs"]["workdir"] = BUNDLE_XHS_DIR
        cfg["platforms"]["xhs"]["mcp"] = "http://localhost:18060"
        # 抖音补充包（可选）：装了就自动接上，没装不影响其它平台
        if os.path.isdir(BUNDLE_MC_DIR):
            cfg["platforms"]["douyin"]["workdir"] = BUNDLE_MC_DIR
        # 推特/Ins/微博 走自带 gallery-dl，工作目录就用技能目录
        for key in ("twitter", "instagram", "weibo"):
            cfg["platforms"][key]["workdir"] = SKILL_DIR

    # Cookie：自带约定位置优先，其次本机找到的
    for key in COOKIE_PLATFORMS:
        mine = bundled_cookie(key)
        have = (cfg["platforms"][key].get("cookie") or "").strip()
        if os.path.isfile(mine):
            cfg["platforms"][key]["cookie"] = mine
        elif have and os.path.isfile(have):
            cfg["platforms"][key]["cookie"] = have

    return cfg


LABELS = {
    "twitter": "推特 X", "instagram": "Instagram", "weibo": "微博",
    "tiktok": "TikTok", "douyin": "抖音", "xhs": "小红书",
}


def report(cfg):
    print("")
    print("=" * 60)
    print("  环境体检结果")
    print("=" * 60)

    def line(name, ok, detail):
        print("  [%s] %-14s %s" % ("√" if ok else "×", name, detail))

    rt = cfg.get("runtime") or {}
    line("自带运行时", bool(rt.get("bundled")),
         ("已启用（" + rt.get("python", "") + "）") if rt.get("bundled")
         else "未找到 runtime\\python，将使用本机已装的引擎")
    line("浏览器", bool(cfg["chrome_path"]),
         cfg["chrome_path"] or "没找到 Chrome / Edge（抖音需要，双击 app\\安装浏览器.bat）")

    e = cfg["engines"]
    if rt.get("bundled"):
        line("gallery-dl", True, "自带（推特/Instagram/微博）")
        line("TikTok 下载器", bool(e["tiktok_dl"]), e["tiktok_dl"] or "缺失")
    else:
        line("gallery-dl", bool(e["gallery_dl"]), e["gallery_dl"] or "未找到（推特/Instagram/微博需要）")
        line("TikTok 下载器", bool(e["tiktok_dl"]), e["tiktok_dl"] or "未找到")
    if os.path.isfile(os.path.join(RUNTIME_DIR, "python311", "python.exe")):
        line("uv", True, "自带（抖音补充包用自带 3.11 运行时，无需 uv）")
    else:
        line("uv", bool(e["uv"]), e["uv"] or "未找到（仅抖音补充包需要）")

    print("")
    for key in ("twitter", "instagram", "weibo", "tiktok", "douyin", "xhs"):
        p = cfg["platforms"].get(key) or {}
        ck = p.get("cookie") or ""
        has = bool(ck and os.path.isfile(ck))
        if key == "douyin":
            if not p.get("workdir"):
                ok, note = False, "未安装抖音补充包（可选）"
            elif not cfg.get("chrome_path"):
                ok, note = False, "缺少浏览器：双击 app\\安装浏览器.bat 装 Chrome 或 Edge"
            else:
                ok, note = True, "已配置（首次会弹浏览器扫码登录；主页/单条都支持）"
        elif key == "xhs":
            ok = bool(p.get("workdir"))
            note = "已自带（需先扫码登录并启动 MCP）" if ok else "未找到 XHS-Downloader"
        else:
            ok = has
            note = ("Cookie 已就绪：" + os.path.basename(os.path.dirname(ck)) + "\\" + os.path.basename(ck)) if has \
                else ("把 cookies.txt 放到 " + os.path.join("cookies", key) + "\\")
        line(LABELS[key], ok, note)

    print("")
    print("  保存位置： %s" % os.path.join(SKILL_DIR, "下载"))
    print("  配置文件： %s" % CONFIG_FILE)
    print("=" * 60)
    print("")


def ensure_cookie_dirs():
    """建好 cookies\\<平台>\\ 目录，并放一份说明，方便新手知道往哪放。"""
    os.makedirs(COOKIE_ROOT, exist_ok=True)
    for key in COOKIE_PLATFORMS:
        os.makedirs(os.path.join(COOKIE_ROOT, key), exist_ok=True)
    note = os.path.join(COOKIE_ROOT, "把导出的文件放这里.txt")
    if not os.path.isfile(note):
        with open(note, "w", encoding="utf-8") as fh:
            fh.write(
                "把用 Chrome 扩展导出的 cookies.txt 放进对应子文件夹，文件名必须是 cookies.txt\n"
                "\n"
                "  twitter\\cookies.txt     ← 在 https://x.com 登录后导出\n"
                "  instagram\\cookies.txt   ← 在 https://www.instagram.com 登录后导出\n"
                "  weibo\\cookies.txt       ← 在 https://weibo.com 登录后导出\n"
                "  tiktok\\cookies.txt      ← 在 https://www.tiktok.com 登录后导出\n"
                "\n"
                "小红书和抖音不用这个，它们走扫码登录。\n"
                "详细步骤见 assets\\cookie导出工具\\使用说明.md\n"
            )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只体检，不写配置")
    ap.add_argument("--yes", action="store_true", help="直接写入，不再询问")
    args = ap.parse_args()

    print("")
    print("多平台资源下载工作台 —— 配置向导")
    if bundle_ready():
        # 自带件齐全时不去翻用户的硬盘：既没必要，也避免误扫到个人文件
        print("检测到技能自带的便携运行时与引擎，正在生成配置（无需本机安装任何东西）…")
        found = {"engines": {}, "platforms": {}, "chrome_path": find_chrome(),
                 "found_dirs": {}}
    else:
        print("未检测到自带运行时，正在扫描本机的下载引擎与 Cookie 文件，请稍候…")
        found = detect_local()
    cfg = build_config(found)

    if args.check:
        report(cfg)
        return

    report(cfg)

    if not args.yes:
        ans = input("把上面的结果写入 config.json 吗？(Y/n) ").strip().lower()
        if ans and ans not in ("y", "yes", "是", "1"):
            print("已取消，未写入任何内容。")
            return

    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_FILE)
    os.makedirs(os.path.join(SKILL_DIR, "下载"), exist_ok=True)
    ensure_cookie_dirs()

    print("配置已写入： %s" % CONFIG_FILE)
    print("")
    print("接下来：")
    print("  1. 双击「启动下载工作台.bat」，浏览器会自动打开下载页面")
    print("  2. 上面标 × 的平台，按提示补 Cookie 或扫码登录")
    print("     · 推特/Ins/微博/TikTok：把导出的 cookies.txt 放进 cookies\\<平台>\\")
    print("     · 小红书：先跑 engines\\xiaohongshu-mcp\\1-扫码登录.bat，再跑 2-启动MCP服务.bat")
    print("     · 抖音：需要单独安装「抖音补充包」（见 references\\环境准备.md），")
    print("             并确保电脑上有 Chrome / Edge（没有就双击 app\\安装浏览器.bat）")
    print("")


if __name__ == "__main__":
    main()