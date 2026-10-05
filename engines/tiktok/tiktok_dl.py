# -*- coding: utf-8 -*-
"""TikTok 下载器：视频走 yt-dlp，图文（slideshow）走 curl_cffi。

为什么这么分工（本机出口是东京机房 IP）：
  * gallery-dl 完全不行：它对 TikTok 用普通 requests 指纹，作品页直接 403。
  * 视频：yt-dlp 能解 TikTok 的 JS 挑战，且在同分辨率多源里会自动换到可用的
    /aweme/v1/play/ 代理地址（直连 v16/v19-webapp-prime.tiktokcdn.com 对机房 IP
    返回 403 Akamai TCP_DENIED），实测可稳定下载。
  * 图文：yt-dlp 的 TikTok 提取器不产出 imagePost 的图片，这里用 curl_cffi
    （Chrome 指纹，实测页面/接口 200、图片 CDN p*-sign*.tiktokcdn.com 200）
    调 /api/creator/item_list/ 取作品并下载图片。

用法：
  python tiktok_dl.py --url <主页/单视频/单图文/短链> --out <目录> [--limit N] [--cookies <文件>]

输出：<out>/<用户名>/<日期>_<作品ID>_<序号>.<ext>
"""
import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse

from curl_cffi import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36")
ITEM_API = "https://www.tiktok.com/api/creator/item_list/"
SLEEP = 3.0
HEX = "0123456789abcdef"
CT_EXT = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png",
          "image/webp": "webp", "image/heic": "heic"}
SCAN_PAGES = 8          # 单帖兜底：最多回翻多少页去找目标作品


def log(msg):
    print(msg, flush=True)


# ---------- curl_cffi 会话 ----------

def _ca_path():
    """libcurl 读不了含中文的 CA 路径，拷一份到纯 ASCII 目录。"""
    try:
        import certifi
        src = certifi.where()
    except Exception:  # noqa: BLE001
        return True
    if all(ord(c) < 128 for c in src) and os.path.isfile(src):
        return src
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    dst = os.path.join(base, "pdtools", "cacert.pem")
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.isfile(dst) or os.path.getsize(dst) != os.path.getsize(src):
            shutil.copyfile(src, dst)
        return dst
    except OSError:
        return True


def new_session(cookies_path):
    s = requests.Session(impersonate="chrome", timeout=60, verify=_ca_path())
    if cookies_path and os.path.isfile(cookies_path):
        n = 0
        for line in open(cookies_path, encoding="utf-8", errors="replace"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            p = line.split("\t")
            if len(p) >= 7:
                s.cookies.set(p[5], p[6], domain=".tiktok.com")
                n += 1
        log("[TikTok] 已载入 %d 条 Cookie" % n)
    else:
        log("[TikTok] 未找到 cookies.txt，按匿名访问（部分主页/内容可能受限）")
    return s


def resolve_url(s, url):
    if "://" not in url:
        url = "https://" + url
    host = urllib.parse.urlparse(url).netloc.lower()
    if "vm.tiktok.com" in host or "vt.tiktok.com" in host:
        try:
            r = s.get(url, headers={"User-Agent": UA}, allow_redirects=True)
            url = str(r.url)
        except Exception as e:  # noqa: BLE001
            log("[TikTok] 短链解析失败：%s" % e)
    return url


def parse_target(url):
    path = urllib.parse.urlparse(url).path
    m = re.search(r"/@([\w.\-]+)", path)
    user = m.group(1) if m else ""
    m2 = re.search(r"/(?:video|photo)/(\d+)", path)
    vid = m2.group(1) if m2 else ""
    return user, vid


def _universal(s, url):
    r = s.get(url, headers={"User-Agent": UA})
    if r.status_code != 200:
        raise RuntimeError("页面请求返回 %d：%s" % (r.status_code, url))
    m = re.search(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
                  r.text, re.S)
    if not m:
        raise RuntimeError("页面未包含 __UNIVERSAL_DATA_FOR_REHYDRATION__（可能被风控）：" + url)
    return json.loads(m.group(1)).get("__DEFAULT_SCOPE__") or {}


def profile_user(s, user):
    """主页页 → secUid。"""
    scope = _universal(s, "https://www.tiktok.com/@" + user)
    ud = scope.get("webapp.user-detail") or {}
    if not ud:
        raise RuntimeError("未取到用户信息（账号可能不存在或被风控）：@" + user)
    if ud.get("statusCode") not in (0, None):
        raise RuntimeError("用户信息状态码 %s（账号私密或受限）" % ud.get("statusCode"))
    sec = (((ud.get("userInfo") or {}).get("user")) or {}).get("secUid")
    if not sec:
        raise RuntimeError("未取到 secUid：@" + user)
    return sec


def build_query(sec_uid, cursor):
    return {
        "aid": "1988", "app_language": "en", "app_name": "tiktok_web",
        "browser_language": "en-US", "browser_name": "Mozilla", "browser_online": "true",
        "browser_platform": "Win32", "browser_version": "5.0 (Windows)",
        "channel": "tiktok_web", "cookie_enabled": "true", "count": "15",
        "cursor": str(cursor),
        "device_id": str(random.randint(7_250_000_000_000_000_000, 7_325_099_899_999_994_577)),
        "device_platform": "web_pc", "focus_state": "true", "from_page": "user",
        "history_len": "2", "is_fullscreen": "false", "is_page_visible": "true",
        "language": "en", "os": "windows", "priority_region": "", "referer": "",
        "region": "US", "screen_height": "1080", "screen_width": "1920",
        "secUid": sec_uid, "type": "1",
        "tz_name": "UTC", "verifyFp": "verify_" + "".join(random.choices(HEX, k=7)),
        "webcast_language": "en",
    }


def iter_posts(s, user, sec_uid, limit=0, max_pages=0, want_id=""):
    """按 最新→最旧 翻页取作品，产出 itemStruct。"""
    cursor = int(time.time() * 1000)
    seen = set()
    got = 0
    page = 0
    while True:
        page += 1
        q = build_query(sec_uid, cursor)
        r = s.get(ITEM_API + "?" + urllib.parse.urlencode(q),
                  headers={"User-Agent": UA, "Referer": "https://www.tiktok.com/@" + user})
        if r.status_code != 200:
            raise RuntimeError("作品列表接口返回 %d：%s" % (r.status_code, r.text[:120]))
        j = r.json()
        items = j.get("itemList") or []
        log("[TikTok] 作品列表第 %d 页：%d 个" % (page, len(items)))
        if not items:
            return
        for it in items:
            vid = it.get("id")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            yield it
            got += 1
            if limit and got >= limit:
                return
            if want_id and vid == want_id:
                return
        last = items[-1].get("createTime") or 0
        new_cursor = int(last * 1000)
        if not new_cursor or new_cursor == cursor:
            new_cursor = cursor - 7 * 86_400_000
        cursor = new_cursor
        if max_pages and page >= max_pages:
            return
        if cursor < 1472706000000 or not j.get("hasMorePrevious"):
            return
        time.sleep(SLEEP)


# ---------- 图片下载 ----------

def image_candidates(item):
    out = []
    for img in ((item.get("imagePost") or {}).get("images") or []):
        urls = [u for u in (((img.get("imageURL") or {}).get("urlList")) or []) if u]
        if urls:
            out.append(urls)
    return out


def download(s, urls, dst_dir, stem, referer):
    """依次试 urls，成功返回 (文件名, 字节数)，全失败返回 (None, 0)。"""
    tmp = os.path.join(dst_dir, "_dl.part")
    for i, u in enumerate(urls, 1):
        try:
            r = s.get(u, headers={"User-Agent": UA, "Referer": referer}, stream=True)
        except Exception as e:  # noqa: BLE001
            log("[TikTok]   候选 %d 请求异常：%s" % (i, str(e)[:80]))
            continue
        ct = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if r.status_code not in (200, 206) or ct not in CT_EXT:
            r.close()
            continue
        n = 0
        try:
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    if chunk:
                        f.write(chunk)
                        n += len(chunk)
        except Exception as e:  # noqa: BLE001
            log("[TikTok]   候选 %d 下载中断：%s" % (i, str(e)[:80]))
        finally:
            r.close()
        if n < 2048:
            continue
        name = "%s.%s" % (stem, CT_EXT[ct])
        os.replace(tmp, os.path.join(dst_dir, name))
        return name, n
    if os.path.exists(tmp):
        try:
            os.remove(tmp)
        except OSError:
            pass
    return None, 0


def date_of(item):
    try:
        return time.strftime("%Y%m%d", time.localtime(int(item.get("createTime") or 0)))
    except (TypeError, ValueError, OSError):
        return "00000000"


def do_photo_post(s, item, out_dir, referer, stats):
    vid = item.get("id") or "0"
    date = date_of(item)
    urls = image_candidates(item)
    if not urls:
        return False
    prefix = "%s_%s_" % (date, vid)
    if any(f.startswith(prefix) for f in os.listdir(out_dir)):
        log("[TikTok]   图文 %s 已存在，跳过" % vid)
        stats["skip"] += 1
        return True
    ok = 0
    for idx, cands in enumerate(urls, 1):
        name, size = download(s, cands, out_dir, "%s_%s_%02d" % (date, vid, idx), referer)
        if name:
            ok += 1
            log("[TikTok]   图文 %s %d/%d → %s (%.2f MB)"
                % (vid, idx, len(urls), name, size / 1048576))
        else:
            log("[TikTok]   图文 %s %d/%d 全部候选失败" % (vid, idx, len(urls)))
    if ok:
        stats["photo"] += 1
        stats["files"] += ok
    else:
        stats["fail"] += 1
    return True


# ---------- 视频下载（yt-dlp） ----------

def run_ytdlp(url, out_dir, limit, cookies):
    if not (cookies and os.path.isfile(cookies)):
        cookies = ""
    cmd = [sys.executable, "-m", "yt_dlp",
           "--impersonate", "chrome",
           "--no-check-certificates",
           "--ignore-errors",
           "--no-warnings",
           "--newline",
           "--no-overwrites",
           "--no-progress",
           "--sleep-requests", "3",
           "--retries", "3",
           "-o", os.path.join(out_dir, "%(upload_date>%Y%m%d)s_%(id)s_01.%(ext)s")]
    if cookies:
        cmd += ["--cookies", cookies]
    if limit:
        cmd += ["--playlist-items", "1-%d" % limit]
    cmd.append(url)

    log("[TikTok] 视频：调用 yt-dlp（Chrome 指纹）…")
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                         errors="replace", bufsize=1)
    done = 0
    for line in p.stdout:
        line = line.rstrip()
        if not line:
            continue
        if line.startswith("[download] Destination:"):
            done += 1
            log("[TikTok] 视频 → " + os.path.basename(line.split("Destination:", 1)[1].strip()))
        elif "has already been downloaded" in line:
            log("[TikTok] 视频已存在，跳过")
        elif line.startswith("ERROR") or "Unable to" in line:
            log("[TikTok] yt-dlp | " + line[:160])
    p.wait()
    return p.returncode, done


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--cookies", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                     "cookies.txt"))
    args = ap.parse_args()

    s = new_session(args.cookies)
    url = resolve_url(s, args.url)
    user, vid = parse_target(url)
    if not user:
        raise SystemExit("无法从链接解析用户名（支持 /@用户名 主页或 /video|/photo/<id> 链接）")
    log("[TikTok] 目标：%s（用户 %s%s）" % (url, user, "，作品 " + vid if vid else ""))

    out_dir = os.path.join(args.out, user)
    os.makedirs(out_dir, exist_ok=True)
    stats = {"photo": 0, "files": 0, "skip": 0, "fail": 0}

    # 1) 视频交给 yt-dlp（/photo/ 链接一定是图文，跳过以免报 Unsupported URL）
    rc = 1
    if "/photo/" not in urllib.parse.urlparse(url).path:
        rc, _ = run_ytdlp(url, out_dir, args.limit, args.cookies)

    # 2) 图文作品：yt-dlp 不认，自己抓作品列表下载
    need_photo = (not vid) or rc != 0
    if need_photo:
        try:
            sec = profile_user(s, user)
        except Exception as e:  # noqa: BLE001
            log("[TikTok] 跳过图文阶段：%s" % str(e)[:120])
            sec = None
        if sec:
            referer = "https://www.tiktok.com/@%s" % user
            if vid:
                posts = iter_posts(s, user, sec, max_pages=SCAN_PAGES, want_id=vid)
            else:
                posts = iter_posts(s, user, sec, limit=args.limit)
            for item in posts:
                try:
                    do_photo_post(s, item, out_dir, referer, stats)
                except Exception as e:  # noqa: BLE001
                    log("[TikTok]   图文 %s 处理失败：%s" % (item.get("id"), str(e)[:100]))
                if not vid:
                    time.sleep(SLEEP)

    log("[TikTok] 完成：图文 %d 个作品 / %d 张图片落盘，跳过 %d，失败 %d"
        % (stats["photo"], stats["files"], stats["skip"], stats["fail"]))
    log("[TikTok] 输出目录：%s" % out_dir)
    total = len([f for f in os.listdir(out_dir) if not f.startswith("_")])
    if not total:
        if vid:
            log("[TikTok] 单帖链接只能回翻最近 %d 页作品定位；较旧的帖子请改用主页链接"
                % SCAN_PAGES)
        raise SystemExit(3)


if __name__ == "__main__":
    main()
