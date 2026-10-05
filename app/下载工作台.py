# -*- coding: utf-8 -*-
"""多平台资源下载工作台 —— 本地可视化下载服务。

设计目标：给「电脑水平有限、且连不上外网」的用户一个开箱即用的下载入口。
- 所有引擎路径、Cookie 路径全部从 config.json 读取（由「配置向导」生成），本文件不写死任何机器路径
- 只做下载：不裁剪、不训练、不碰任何个人数据
- 单一串行 worker，任务持久化到 运行记录/任务记录.json
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(APP_DIR)
CONFIG_FILE = os.path.join(SKILL_DIR, "config.json")
RECORD_DIR = os.path.join(SKILL_DIR, "运行记录")
TASK_FILE = os.path.join(RECORD_DIR, "任务记录.json")
TMP_ROOT = os.path.join(RECORD_DIR, "暂存")
PAGE_FILE = os.path.join(APP_DIR, "网页", "index.html")
# 抖音补充包附带的 Playwright 内核（可选；没有就走系统默认缓存）
PW_BROWSERS_DIR = os.path.join(SKILL_DIR, "playwright-browsers")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

VID_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".heic", ".gif", ".bmp"}

PLATFORM_LABEL = {
    "twitter": "推特 X",
    "instagram": "Instagram",
    "weibo": "微博",
    "tiktok": "TikTok",
    "douyin": "抖音",
    "xhs": "小红书",
}

PLATFORM_HOSTS = {
    "xhs": ("xiaohongshu.com", "xhslink.com"),
    "douyin": ("douyin.com", "iesdouyin.com"),
    "twitter": ("x.com", "twitter.com", "t.co"),
    "instagram": ("instagram.com", "instagr.am"),
    "tiktok": ("tiktok.com", "vm.tiktok.com"),
    "weibo": ("weibo.com", "weibo.cn"),
}

URL_RE = re.compile(r"https?://[^\s，。、；）】」》\"'<>]+", re.I)


# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "port": 8790,
    "output_dir": "下载",
    "open_browser": True,
    "chrome_path": "",
    "runtime": {"python": "", "bundled": False},
    "engines": {"gallery_dl": "", "yt_dlp": "", "uv": "", "xhs_python": "",
                "tiktok_dl": "", "tiktok_python": ""},
    "platforms": {
        "twitter": {"cookie": "", "config": "", "workdir": ""},
        "instagram": {"cookie": "", "config": "", "workdir": ""},
        "weibo": {"cookie": "", "config": "", "workdir": ""},
        "tiktok": {"cookie": "", "workdir": ""},
        "douyin": {"workdir": ""},
        "xhs": {"cookie": "", "workdir": "", "mcp": ""},
    },
}


def _deep_merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
                cfg = _deep_merge(DEFAULT_CONFIG, json.load(fh))
        except Exception:
            pass
    out = cfg.get("output_dir") or "下载"
    if not os.path.isabs(out):
        out = os.path.join(SKILL_DIR, out)
    cfg["output_dir"] = os.path.normpath(out)
    return cfg


CFG = load_config()
# 开机自启时用隐藏窗口运行，此时不要自动弹浏览器打扰用户
if os.environ.get("MD_NO_BROWSER") == "1":
    CFG["open_browser"] = False
STATE_LOCK = threading.Lock()
WORK_LOCK = threading.Lock()
TASKS = []
CURRENT = {"id": ""}


def out_dir():
    d = CFG["output_dir"]
    os.makedirs(d, exist_ok=True)
    return d


def plat_cfg(key):
    return (CFG.get("platforms") or {}).get(key) or {}


def eng(name):
    return ((CFG.get("engines") or {}).get(name) or "").strip()


def rt_python():
    """技能自带的便携 Python 路径（没有则为空）。"""
    return ((CFG.get("runtime") or {}).get("python") or "").strip()


def use_bundle():
    """是否启用自带运行时（自带时不需要本机装过任何引擎）。"""
    return bool((CFG.get("runtime") or {}).get("bundled")) and os.path.isfile(rt_python())


def gallery_cmd():
    """gallery-dl 的调用前缀。

    自带运行时里没有 gallery-dl.exe，用 `python -m gallery_dl` 代替；
    非自带模式仍走本机找到的 gallery-dl.exe。
    """
    if use_bundle():
        return [rt_python(), "-m", "gallery_dl"]
    gd = eng("gallery_dl")
    if not gd or not os.path.isfile(gd):
        raise RuntimeError("未配置 gallery-dl，请重新运行配置向导")
    return [gd]


# --------------------------------------------------------------------------
# 通用工具
# --------------------------------------------------------------------------
def now_ts():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def sanitize_name(name):
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "", (name or "").strip())
    name = name.strip(". ")
    return name[:80]


def log_task(t, line):
    line = str(line).rstrip()
    if not line:
        return
    with STATE_LOCK:
        t.setdefault("log", []).append("%s %s" % (time.strftime("%H:%M:%S"), line))
        if len(t["log"]) > 400:
            t["log"] = t["log"][-400:]


def base_env(group=""):
    """子进程环境。

    自带运行时里 gallerydl / xhs / mediacrawler 三组各带一份同名第三方库，
    一次性全挂会互相遮蔽（xhs 引擎会 import 到 mediacrawler 的 fastapi）。
    这里用 MD_PKG_GROUPS 告诉自带的 sitecustomize 本次只挂哪一组。
    """
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    if use_bundle():
        # 避免用户全局的 PYTHONHOME / PYTHONPATH 干扰自带运行时
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)
        if group:
            env["MD_PKG_GROUPS"] = group
    return env


def run_stream(t, cmd, cwd=None, env=None, on_line=None):
    """跑子进程，逐行回显日志。返回退出码。"""
    log_task(t, "$ " + " ".join(os.path.basename(c) if i == 0 else c
                                for i, c in enumerate(cmd)))
    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd, env=env or base_env(),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
            errors="replace", bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except FileNotFoundError as exc:
        raise RuntimeError("找不到程序：%s（请重新运行配置向导）" % exc.filename)
    for line in proc.stdout:
        log_task(t, line)
        if on_line:
            try:
                on_line(line)
            except Exception:
                pass
    proc.wait()
    return proc.returncode


def move_unique(src, dst):
    if not os.path.exists(dst):
        shutil.move(src, dst)
        return dst
    stem, ext = os.path.splitext(os.path.basename(dst))
    i = 1
    while True:
        cand = os.path.join(os.path.dirname(dst), "%s__%d%s" % (stem, i, ext))
        if not os.path.exists(cand):
            shutil.move(src, cand)
            return cand
        i += 1


def merge_move(src, dst):
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        move_unique(os.path.join(src, name), os.path.join(dst, name))
    shutil.rmtree(src, ignore_errors=True)


def count_media(d):
    img = vid = 0
    for root, _, files in os.walk(d):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in VID_EXT:
                vid += 1
            elif ext in IMG_EXT:
                img += 1
    return img, vid


def _author_hint(url, platform):
    try:
        path = urllib.parse.urlparse(url if "://" in url else "https://" + url).path
    except Exception:
        return ""
    seg = [s for s in path.split("/") if s]
    if platform == "twitter":
        return sanitize_name(seg[0]) if seg else ""
    if platform == "tiktok":
        m = re.search(r"/@([\w_.-]+)", path)
        return sanitize_name(m.group(1)) if m else ""
    if platform == "instagram":
        if not seg or seg[0] in ("p", "reel", "reels", "tv", "stories",
                                 "explore", "accounts", "share"):
            return ""
        return sanitize_name(seg[0])
    if platform == "weibo":
        if not seg:
            return ""
        if seg[0] in ("u", "n", "p", "profile") and len(seg) > 1:
            return sanitize_name(urllib.parse.unquote(seg[1]))
        if seg[0] in ("detail", "status", "comments", "attitude", "repost", "hot", "search"):
            return ""
        return sanitize_name(seg[0])
    return ""


def collect_author_dir(tmp, before, hint, dest, tip):
    """把下载器在 tmp 下产出的作者目录归位到 dest，返回结果字典。"""
    after = os.listdir(tmp)
    new = sorted(set(after) - set(before))
    person = sanitize_name(new[0]) if new else hint
    if not person:
        cands = [d for d in after if os.path.isdir(os.path.join(tmp, d))]
        person = sanitize_name(cands[0]) if len(cands) == 1 else ""
    if not person:
        raise RuntimeError(tip)
    src = os.path.join(tmp, person)
    if not os.path.isdir(src):
        for sub in after:
            alt = os.path.join(tmp, sub, person)
            if os.path.isdir(alt):
                src = alt
                break
    if not os.path.isdir(src):
        raise RuntimeError(tip)
    target = os.path.join(dest, person)
    if os.path.isdir(target):
        merge_move(src, target)
    else:
        shutil.move(src, target)
    for sub in os.listdir(tmp):
        p = os.path.join(tmp, sub)
        if os.path.isdir(p) and not os.listdir(p):
            shutil.rmtree(p, ignore_errors=True)
    img, vid = count_media(target)
    return {"author_name": person, "author_dir": target,
            "img_count": img, "vid_count": vid}


def flatten_single(res, dest):
    """单条模式：把 <dest>/<博主>/ 里的文件直接摊到 dest 根下。"""
    src = res.get("author_dir") or ""
    if not src or not os.path.isdir(src) or os.path.abspath(src) == os.path.abspath(dest):
        return res
    files = []
    for root, _, fs in os.walk(src):
        files += [os.path.join(root, f) for f in fs]
    for fp in sorted(files):
        move_unique(fp, os.path.join(dest, os.path.basename(fp)))
    shutil.rmtree(src, ignore_errors=True)
    res["author_dir"] = dest
    return res


# --------------------------------------------------------------------------
# 平台识别
# --------------------------------------------------------------------------
def detect_platform(url):
    try:
        host = (urllib.parse.urlparse(url if "://" in url else "https://" + url)
                .hostname or "").lower()
    except Exception:
        return ""
    for key, hosts in PLATFORM_HOSTS.items():
        for h in hosts:
            if host == h or host.endswith("." + h):
                return key
    return ""


def extract_urls(text):
    urls = URL_RE.findall(text or "")
    if not urls:
        cand = (text or "").strip()
        if re.match(r"^[\w.-]+\.[a-z]{2,}/\S*$", cand, re.I):
            urls = ["https://" + cand]
    return [u.rstrip(".,;") for u in urls]


# --------------------------------------------------------------------------
# 抖音链接解析
# --------------------------------------------------------------------------
SEC_UID_RE = re.compile(r"sec_uid=([\w-]+)")
# 单条作品：/video/123、/note/123、?modal_id=123、纯数字 ID
DOUYIN_AWEME_RE = re.compile(r"/(?:video|note)/(\d+)")
DOUYIN_MODAL_RE = re.compile(r"[?&]modal_id=(\d+)")


def _final_url(url):
    """跟随重定向拿到最终地址（短链 v.douyin.com 要靠它分辨是作品还是作者）。"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.geturl(), resp.read().decode("utf-8", "replace")


def douyin_target(url):
    """抖音链接 → (类型, 取值)。

    类型 ``detail`` 表示单条作品，取值是作品 ID（短链则原样交给 MediaCrawler 解析）；
    类型 ``creator`` 表示作者主页，取值是 sec_uid。
    """
    url = (url or "").strip()
    m = DOUYIN_AWEME_RE.search(url) or DOUYIN_MODAL_RE.search(url)
    if m:
        return "detail", m.group(1)
    if url.isdigit():
        return "detail", url

    try:
        host = (urllib.parse.urlparse(url if "://" in url else "https://" + url)
                .hostname or "").lower()
    except Exception:
        host = ""
    # v.douyin.com 分享短链：先跟一次重定向，能认出作品就按单条处理
    if host.endswith("v.douyin.com"):
        try:
            final, _ = _final_url(url)
        except Exception:
            return "detail", url  # 解析不了就交给 MediaCrawler 自己跟短链
        m = DOUYIN_AWEME_RE.search(final) or DOUYIN_MODAL_RE.search(final)
        if m:
            return "detail", m.group(1)
        if "/user/" in final:
            return "creator", final.split("/user/", 1)[1].split("?")[0].strip("/")
        return "detail", final

    m = SEC_UID_RE.search(url)
    if m:
        return "creator", m.group(1)
    if "/user/" in url:
        seg = url.split("/user/", 1)[1].split("?")[0].strip("/")
        if seg:
            return "creator", seg

    try:
        final, body = _final_url(url)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("打开抖音链接失败：%s" % exc)
    for text in (final, body):
        if "/user/" in text:
            seg = text.split("/user/", 1)[1].split("?")[0].strip("/\"' <")
            if seg:
                return "creator", seg
        m = SEC_UID_RE.search(text)
        if m:
            return "creator", m.group(1)
    raise RuntimeError("无法识别这个抖音链接（作品链接或作者主页链接都行）")


# --------------------------------------------------------------------------
# 各平台下载
# --------------------------------------------------------------------------
def dl_gallery(t, platform, tmp):
    """推特 / Instagram / 微博：gallery-dl。"""
    p = plat_cfg(platform)
    cfg_file = (p.get("config") or "").strip()
    cookie = (p.get("cookie") or "").strip()
    workdir = (p.get("workdir") or "").strip() or (os.path.dirname(cfg_file) or None)
    os.makedirs(tmp, exist_ok=True)
    before = os.listdir(tmp)
    cmd = gallery_cmd()
    if cfg_file and os.path.isfile(cfg_file):
        cmd += ["--config", cfg_file]
    cmd += ["-d", tmp]
    if cookie and os.path.isfile(cookie):
        log_task(t, "[%s] 使用 cookies.txt" % PLATFORM_LABEL[platform])
        cmd += ["-C", cookie]
    else:
        log_task(t, "[%s] 未找到 cookies.txt，改用本机 Chrome 登录态（可能失败，建议先导出）"
                    % PLATFORM_LABEL[platform])
        cmd += ["--cookies-from-browser", "chrome"]
    limit = int(t.get("limit") or 0)
    if limit > 0:
        if platform == "instagram":
            cmd += ["-o", "extractor.instagram.max-posts=%d" % limit]
        elif platform == "twitter":
            cmd += ["-o", "extractor.twitter.max-posts=%d" % limit]
        elif platform == "weibo":
            cmd += ["--range", "1-%d" % limit]
    cmd.append(t["url"])
    rc = run_stream(t, cmd, cwd=workdir, env=base_env("gallerydl"))
    if rc != 0:
        raise RuntimeError("下载退出码 %d（Cookie 可能失效，请重新导出 cookies.txt）" % rc)
    return collect_author_dir(t, tmp, _author_hint(t["url"], platform), t["dest"],
                              "未下载到文件（Cookie 可能失效，或该主页是私密账号）")


def dl_tiktok(t, tmp):
    """TikTok：自建下载器（yt-dlp Chrome 指纹 + curl_cffi）。"""
    script = eng("tiktok_dl")
    py = eng("tiktok_python") or rt_python()
    if not script or not os.path.isfile(script):
        raise RuntimeError("未配置 TikTok 下载器，请重新运行配置向导")
    if not py or not os.path.isfile(py):
        raise RuntimeError("未配置 TikTok 下载器所用的 Python，请重新运行配置向导")
    p = plat_cfg("tiktok")
    cookie = (p.get("cookie") or "").strip()
    workdir = (p.get("workdir") or "").strip() or os.path.dirname(script)
    os.makedirs(tmp, exist_ok=True)
    before = os.listdir(tmp)
    cmd = [py, script, "--url", t["url"], "--out", tmp, "--cookies", cookie]
    limit = int(t.get("limit") or 0)
    if limit > 0:
        cmd += ["--limit", str(limit)]
    if not (cookie and os.path.isfile(cookie)):
        log_task(t, "[TikTok] 未找到 cookies.txt，按匿名访问（部分内容受限）")
    rc = run_stream(t, cmd, cwd=workdir, env=base_env("gallerydl"))
    if rc != 0:
        raise RuntimeError("TikTok 下载退出码 %d（Cookie 可能失效，或该主页是私密账号）" % rc)
    return collect_author_dir(t, tmp, _author_hint(t["url"], "tiktok"), t["dest"],
                              "未下载到文件（Cookie 可能失效，或该主页是私密账号）")


def dl_xhs(t, tmp):
    """小红书：XHS-Downloader + 本地 MCP 服务。"""
    py = eng("xhs_python") or rt_python()
    p = plat_cfg("xhs")
    xhs_dir = (p.get("workdir") or "").strip()
    if not py or not os.path.isfile(py):
        raise RuntimeError("未配置 XHS-Downloader 的 Python，请重新运行配置向导")
    if not xhs_dir or not os.path.isdir(xhs_dir):
        raise RuntimeError("未配置 XHS-Downloader 目录，请重新运行配置向导")
    if not _mcp_alive():
        raise RuntimeError("小红书 MCP 服务未启动：请先运行 xiaohongshu-mcp 的扫码登录/启动服务")
    worker = os.path.join(APP_DIR, "engine", "xhs_worker.py")
    os.makedirs(tmp, exist_ok=True)
    before = os.listdir(tmp)
    env = base_env("xhs")
    env["XHS_DIR"] = xhs_dir
    cmd = [py, worker, "--url", t["url"], "--stage", tmp]
    limit = int(t.get("limit") or 0)
    if limit > 0:
        cmd += ["--limit", str(limit)]
    rc = run_stream(t, cmd, cwd=xhs_dir, env=env)
    if rc != 0:
        raise RuntimeError("小红书下载失败（登录态可能已过期，请重新扫码登录）")
    return collect_author_dir(t, tmp, "", t["dest"], "小红书未下载到文件")


def _mcp_alive():
    p = plat_cfg("xhs")
    base = (p.get("mcp") or "http://localhost:18060").rstrip("/")
    try:
        req = urllib.request.Request(base + "/mcp", method="GET")
        urllib.request.urlopen(req, timeout=3)
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


def pw_browsers():
    """抖音补充包自带的 Playwright 内核目录；没有则返回空（用系统默认缓存）。"""
    if os.path.isdir(PW_BROWSERS_DIR) and os.listdir(PW_BROWSERS_DIR):
        return PW_BROWSERS_DIR
    return ""


def pw_default_cache():
    """本机 Playwright 默认缓存目录（%LOCALAPPDATA%\\ms-playwright）。"""
    d = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")
    return d if os.path.isdir(d) and os.listdir(d) else ""


def _portable_browser():
    """技能目录下 browser\\ 里用户自己解压的便携版浏览器（npmmirror 的 zip）。"""
    root = os.path.join(SKILL_DIR, "browser")
    if not os.path.isdir(root):
        return ""
    for cur, dirs, files in os.walk(root):
        if cur[len(root):].count(os.sep) > 3:
            dirs[:] = []
            continue
        for f in files:
            if f.lower() in ("chrome.exe", "msedge.exe"):
                return os.path.join(cur, f)
    return ""


def find_system_browser():
    """找本机可用的 Chromium 系浏览器，返回可执行文件路径（没有则空）。

    抖音需要真实浏览器来生成签名、保存登录态。本包不再附带 Chromium 内核，
    所以优先用用户自己装的浏览器。顺序：配置里的路径 → 标准安装路径 → 便携版。
    """
    la = os.environ.get("LOCALAPPDATA", "")
    pf = os.environ.get("PROGRAMFILES", "")
    pf86 = os.environ.get("PROGRAMFILES(X86)", "")
    cands = [
        (CFG.get("chrome_path") or "").strip(),
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
    return _portable_browser()


def mc_python(mc_dir):
    """跑 MediaCrawler 的 Python。

    MediaCrawler 的依赖是 3.11 编译的，跟自带 3.12 运行时不是同一个版本，
    所以补充包里额外带了一个 3.11 运行时；老用户自己建过 venv 的则用它的 venv。
    """
    py = os.path.join(SKILL_DIR, "runtime", "python311", "python.exe")
    if os.path.isfile(py):
        return py
    if mc_dir:
        venv_py = os.path.join(mc_dir, ".venv", "Scripts", "python.exe")
        if os.path.isfile(venv_py):
            return venv_py
    return ""


def mc_node_dir():
    """抖音签名脚本要一个 JS 运行时。

    MediaCrawler 用 execjs 跑 `libs/douyin.js` 生成 a_bogus，execjs 默认去 PATH 里找
    node；用户电脑上一般没装 Node。Playwright 的驱动里正好自带一个 node.exe，
    直接拿它顶上，省得让用户再装 Node。
    """
    d = os.path.join(SKILL_DIR, "runtime", "pkgs", "mediacrawler",
                     "playwright", "driver")
    return d if os.path.isfile(os.path.join(d, "node.exe")) else ""


def with_node_path(env):
    """把自带的 node.exe 目录塞到 PATH 最前面（已有 Node 的机器不受影响）。"""
    d = mc_node_dir()
    if not d:
        return env
    cur = env.get("PATH") or ""
    if os.path.normcase(d) not in os.path.normcase(cur):
        env["PATH"] = d + os.pathsep + cur
    return env


def dl_douyin(t, tmp):
    """抖音：MediaCrawler，作者主页批量 + 单条作品都走它。

    - 作者主页 → ``--type creator``
    - 单条作品 → ``--type detail --specified_id``（支持 /video/、/note/、分享短链、纯 ID）

    自带 3.11 运行时可用时直接跑 main.py（用户不必装 uv / Python）；
    只有回退到本机环境时才需要 uv。
    """
    mc_dir = (plat_cfg("douyin").get("workdir") or "").strip()
    if not mc_dir or not os.path.isdir(mc_dir):
        raise RuntimeError("未配置 MediaCrawler 目录，请先安装「抖音补充包」（见 references\\环境准备.md）")
    py = mc_python(mc_dir)
    if py:
        head = [py, "main.py"]
    else:
        uv = eng("uv")
        if not uv or not os.path.isfile(uv):
            raise RuntimeError("未配置 uv，请重新运行配置向导")
        head = [uv, "run", "main.py"]

    kind, value = douyin_target(t["url"])
    limit = int(t.get("limit") or 0) or 50
    if kind == "detail":
        if t["mode"] != "single":
            t["mode"] = "single"
            log_task(t, "[抖音] 检测到单条作品链接，按「只下载这一条」处理")
        log_task(t, "[抖音] 单条作品 → " + value)
        tail = ["--type", "detail", "--specified_id", value]
        person = sanitize_name("抖音_" + (value if value.isdigit() else "单条"))
    else:
        if t["mode"] == "single":
            raise RuntimeError("这是作者主页链接，请把下载方式改成「下载整个主页」")
        log_task(t, "[抖音] 作者主页 → " + value)
        tail = ["--type", "creator", "--creator_id", value,
                "--crawler_max_notes_count", str(limit)]
        person = sanitize_name(value) or ("抖音_" + value[:8])

    media_roots = [os.path.join(mc_dir, "data", p, "media") for p in ("douyin", "dy")]
    media_roots = [d for d in media_roots if os.path.isdir(d)] or \
                  [os.path.join(mc_dir, "data", "douyin", "media")]
    before = set()
    for r in media_roots:
        if os.path.isdir(r):
            for root, _, files in os.walk(r):
                for f in files:
                    before.add(os.path.join(root, f))
    started = time.time() - 1

    env = base_env("mediacrawler")
    env["UV_DEFAULT_INDEX"] = "https://mirrors.aliyun.com/pypi/simple/"
    with_node_path(env)
    browser = find_system_browser()
    if browser:
        # 用用户本机已装的浏览器，包内不必再带 Chromium 内核
        env["MC_BROWSER_PATH"] = browser
        log_task(t, "[抖音] 使用本机浏览器：" + browser)
    elif pw_browsers():
        env["PLAYWRIGHT_BROWSERS_PATH"] = pw_browsers()
        log_task(t, "[抖音] 使用补充包自带的浏览器内核")
    elif pw_default_cache():
        log_task(t, "[抖音] 使用本机 Playwright 缓存的内核")
    else:
        raise RuntimeError("没找到 Chrome / Edge。抖音需要一个浏览器，"
                           "请先双击 app\\安装浏览器.bat 按引导安装（见 references\\环境准备.md）")

    cmd = head + ["--platform", "dy", "--lt", "qrcode"] + tail + \
          ["--get_media", "yes", "--get_comment", "no", "--save_data_option", "jsonl"]
    log_task(t, "[抖音] 启动 MediaCrawler（如弹出浏览器请扫码登录）…")
    grabbed = set()

    def grab(line):
        for m in re.finditer(r"fetching aweme (\d+)", line):
            grabbed.add(m.group(1))
        m = re.search(r"douyin aweme id:(\d+)", line)
        if m:
            grabbed.add(m.group(1))

    rc = run_stream(t, cmd, cwd=mc_dir, env=env, on_line=grab)
    if rc != 0:
        raise RuntimeError("抖音采集退出码 %d（若为登录/风控，请先手动扫码登录一次）" % rc)

    picked = []
    for r in media_roots:
        if not os.path.isdir(r):
            continue
        for root, _, files in os.walk(r):
            for f in files:
                fp = os.path.join(root, f)
                aid = os.path.basename(root)
                if aid in grabbed or fp not in before or os.path.getmtime(fp) >= started:
                    picked.append(fp)
    if not picked:
        if kind == "detail":
            raise RuntimeError("抖音没下到这个作品（链接失效 / 作品已删除 / 未登录 / 被风控）")
        raise RuntimeError("抖音未采集到媒体（该主页无作品 / 未登录 / 被风控）")

    target = os.path.join(t["dest"], person)
    img_dir, vid_dir = os.path.join(target, "图片"), os.path.join(target, "视频")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(vid_dir, exist_ok=True)
    img = vid = 0
    for fp in sorted(picked):
        name = os.path.basename(os.path.dirname(fp)) + "_" + os.path.basename(fp)
        is_vid = os.path.splitext(fp)[1].lower() in VID_EXT
        dst = os.path.join(vid_dir if is_vid else img_dir, name)
        if os.path.exists(dst):
            os.remove(fp)
            continue
        shutil.move(fp, dst)
        vid += 1 if is_vid else 0
        img += 0 if is_vid else 1
    return {"author_name": person, "author_dir": target,
            "img_count": img, "vid_count": vid}


DISPATCH = {
    "twitter": lambda t, tmp: dl_gallery(t, "twitter", tmp),
    "instagram": lambda t, tmp: dl_gallery(t, "instagram", tmp),
    "weibo": lambda t, tmp: dl_gallery(t, "weibo", tmp),
    "tiktok": dl_tiktok,
    "xhs": dl_xhs,
    "douyin": dl_douyin,
}


# --------------------------------------------------------------------------
# 任务
# --------------------------------------------------------------------------
def save_tasks():
    os.makedirs(RECORD_DIR, exist_ok=True)
    try:
        with STATE_LOCK:
            data = [dict(x) for x in TASKS][-100:]
        tmp = TASK_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, TASK_FILE)
    except Exception:
        pass


def load_tasks():
    global TASKS
    if not os.path.isfile(TASK_FILE):
        return
    try:
        with open(TASK_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for x in data:
            if x.get("status") in ("queued", "running"):
                x["status"] = "failed"
                x["error"] = x.get("error") or "服务重启，任务已中断"
            x.pop("_gd_before", None)
        TASKS = data
    except Exception:
        TASKS = []


def add_task(url, mode, dest, limit):
    platform = detect_platform(url)
    if not platform:
        raise ValueError("无法识别这个链接属于哪个平台，请检查是否粘贴完整")
    if not dest or not os.path.isdir(dest):
        raise ValueError("保存目录不存在：" + (dest or "（未选择）"))
    t = {
        "id": "%d" % int(time.time() * 1000),
        "url": url, "platform": platform, "mode": mode or "author",
        "dest": dest, "limit": int(limit or 0),
        "status": "queued", "stage": "排队中", "error": "",
        "author": "", "author_dir": "", "img_count": 0, "vid_count": 0,
        "created": now_ts(), "finished": "", "log": [],
    }
    with STATE_LOCK:
        TASKS.append(t)
    save_tasks()
    return t


def run_task(t):
    tmp = os.path.join(TMP_ROOT, t["id"])
    os.makedirs(tmp, exist_ok=True)
    try:
        t["stage"] = "下载中"
        log_task(t, "[开始] %s%s → %s" % (
            PLATFORM_LABEL[t["platform"]],
            "（单条内容）" if t["mode"] == "single" else "（博主全部作品）",
            t["dest"]))
        res = DISPATCH[t["platform"]](t, tmp)
        if t["mode"] == "single":
            res = flatten_single(res, t["dest"])
        t["author"] = res.get("author_name") or ""
        t["author_dir"] = res.get("author_dir") or ""
        t["img_count"] = res.get("img_count") or 0
        t["vid_count"] = res.get("vid_count") or 0
        t["status"] = "done"
        t["stage"] = "已完成"
        log_task(t, "[完成] %s：图片 %d，视频 %d → %s" % (
            t["author"] or "未知博主", t["img_count"], t["vid_count"], t["author_dir"]))
    except Exception as exc:  # noqa: BLE001
        t["status"] = "failed"
        t["stage"] = "失败"
        t["error"] = str(exc)
        log_task(t, "[失败] " + str(exc))
    finally:
        t["finished"] = now_ts()
        shutil.rmtree(tmp, ignore_errors=True)
        save_tasks()


def worker_loop():
    while True:
        job = None
        with STATE_LOCK:
            for x in TASKS:
                if x.get("status") == "queued":
                    job = x
                    break
        if job is None:
            time.sleep(1.0)
            continue
        with STATE_LOCK:
            job["status"] = "running"
            CURRENT["id"] = job["id"]
        with WORK_LOCK:
            run_task(job)
        CURRENT["id"] = ""


# --------------------------------------------------------------------------
# 状态
# --------------------------------------------------------------------------
def chrome_ok():
    """本机是否有可用的 Chrome / Edge（抖音需要它来生成签名与登录）。"""
    return bool(find_system_browser())


def gallery_ok():
    """gallery-dl 可用（自带运行时，或本机装了 exe）。"""
    if use_bundle():
        return True
    gd = eng("gallery_dl")
    return bool(gd and os.path.isfile(gd))


def platform_status():
    items = []
    for key in ("twitter", "instagram", "weibo", "tiktok", "xhs", "douyin"):
        p = plat_cfg(key)
        notes = []
        ready = True
        if key in ("twitter", "instagram", "weibo"):
            if not gallery_ok():
                ready = False
                notes.append("缺少 gallery-dl（未启用自带运行时）")
            if not (p.get("cookie") or "") or not os.path.isfile(p.get("cookie") or ""):
                ready = False
                notes.append("缺少 cookies.txt（放到 cookies\\%s\\）" % key)
        elif key == "tiktok":
            if not eng("tiktok_dl") or not os.path.isfile(eng("tiktok_dl")):
                ready = False
                notes.append("缺少下载器")
            if not (p.get("cookie") or "") or not os.path.isfile(p.get("cookie") or ""):
                notes.append("未配置 Cookie（匿名可下部分内容）")
        elif key == "xhs":
            if not (eng("xhs_python") or rt_python()):
                ready = False
                notes.append("缺少 XHS-Downloader")
            if not (p.get("workdir") or "") or not os.path.isdir(p.get("workdir") or ""):
                ready = False
                notes.append("未配置 XHS 目录")
            if ready and not _mcp_alive():
                ready = False
                notes.append("MCP 服务未启动：先跑 engines\\xiaohongshu-mcp\\1-扫码登录.bat")
        elif key == "douyin":
            wd = p.get("workdir") or ""
            if not wd or not os.path.isdir(wd):
                ready = False
                notes.append("未安装抖音补充包（可选，见 references\\环境准备.md）")
            elif not mc_python(wd) and (not eng("uv") or not os.path.isfile(eng("uv"))):
                ready = False
                notes.append("缺少运行环境（自带 3.11 运行时或 uv）")
            elif not (find_system_browser() or pw_browsers() or pw_default_cache()):
                ready = False
                notes.append("缺少浏览器：先装 Chrome 或 Edge（双击 app\\安装浏览器.bat）")
        items.append({
            "key": key, "name": PLATFORM_LABEL[key],
            "ready": ready, "notes": notes,
            "cookie": bool((p.get("cookie") or "") and os.path.isfile(p.get("cookie") or "")),
        })
    return items


def state_payload():
    with STATE_LOCK:
        tasks = [dict(x) for x in TASKS][-30:]
    for x in tasks:
        x.pop("_gd_before", None)
    return {
        "ok": True,
        "version": "1.0",
        "port": CFG.get("port"),
        "output_dir": out_dir(),
        "chrome_ok": chrome_ok(),
        "browser": find_system_browser(),
        "bundled": use_bundle(),
        "platforms": platform_status(),
        "tasks": tasks,
        "current": CURRENT["id"],
    }


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "MediaDownloader/1.0"

    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else str(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            try:
                with open(PAGE_FILE, "rb") as fh:
                    self._send(200, fh.read(), "text/html; charset=utf-8")
            except FileNotFoundError:
                self._send(404, "页面文件缺失", "text/plain; charset=utf-8")
            return
        if path == "/api/state":
            self._json(state_payload())
            return
        self._json({"ok": False, "error": "not found"}, 404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except Exception:
            body = {}
        try:
            if path == "/api/task":
                urls = extract_urls(body.get("url") or "")
                if not urls:
                    return self._json({"ok": False, "error": "请先粘贴链接"})
                dest = (body.get("dest") or "").strip() or out_dir()
                if not os.path.isdir(dest):
                    try:
                        os.makedirs(dest, exist_ok=True)
                    except Exception:
                        return self._json({"ok": False, "error": "保存目录无法创建：" + dest})
                mode = "single" if body.get("mode") == "single" else "author"
                created = []
                for u in urls:
                    try:
                        t = add_task(u, mode, dest, body.get("limit") or 0)
                        created.append({"id": t["id"], "url": u, "platform": t["platform"]})
                    except Exception as exc:  # noqa: BLE001
                        created.append({"id": "", "url": u, "error": str(exc)})
                return self._json({"ok": True, "created": created})
            if path == "/api/cancel":
                tid = str(body.get("id") or "")
                with STATE_LOCK:
                    for x in TASKS:
                        if x["id"] == tid and x["status"] == "queued":
                            x["status"] = "canceled"
                            x["stage"] = "已取消"
                            x["finished"] = now_ts()
                save_tasks()
                return self._json({"ok": True})
            if path == "/api/opendir":
                d = (body.get("dir") or "").strip() or out_dir()
                if os.path.isdir(d):
                    subprocess.Popen(["explorer", os.path.normpath(d)])
                    return self._json({"ok": True})
                return self._json({"ok": False, "error": "目录不存在：" + d})
            if path == "/api/pickdir":
                return self._json({"ok": True, "dir": pick_dir()})
            if path == "/api/exit":
                self._json({"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
        except Exception as exc:  # noqa: BLE001
            return self._json({"ok": False, "error": str(exc)}, 500)
        self._json({"ok": False, "error": "not found"}, 404)


def pick_dir():
    """弹系统文件夹选择框。低配用户不想手打路径时用。"""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        d = filedialog.askdirectory(title="选择下载保存位置")
        root.destroy()
        return d or ""
    except Exception:
        return ""


def lan_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("223.5.5.5", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main():
    os.makedirs(RECORD_DIR, exist_ok=True)
    os.makedirs(TMP_ROOT, exist_ok=True)
    out_dir()
    load_tasks()
    threading.Thread(target=worker_loop, daemon=True).start()
    port = int(CFG.get("port") or 8790)
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as exc:
        print("端口 %d 已被占用：%s" % (port, exc))
        print("可能「下载工作台」已经在运行了，直接打开下面的网址即可。")
        print("  http://127.0.0.1:%d" % port)
        input("按回车退出…")
        return
    url = "http://127.0.0.1:%d" % port
    print("=" * 52)
    print("  多平台资源下载工作台 已启动")
    print("=" * 52)
    print("  本机访问： %s" % url)
    print("  保存位置： %s" % out_dir())
    print("  关闭窗口即停止服务（加入开机自启后无需手动启动）")
    print("=" * 52)
    if CFG.get("open_browser", True):
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()