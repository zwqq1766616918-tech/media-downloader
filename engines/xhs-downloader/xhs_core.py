r"""小红书主页批量下载核心逻辑（CLI 与 Web 界面共用）。

流程：解析帖子 → 定位作者 → MCP 枚举全部作品 → 下载 → 按 图片 / 视频 分类。
"""

import io
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from contextlib import redirect_stdout
from json import load
from pathlib import Path
from shutil import move
from time import sleep

from curl_cffi import requests

from source.application import XHS

MCP_BASE = "http://localhost:18060/mcp"

IMAGE_EXT = {".jpeg", ".jpg", ".png", ".webp", ".avif", ".heic", ".gif"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv"}

NOTE_ID_RE = re.compile(r"/(?:explore|discovery/item)/([0-9a-zA-Z]+)")
USER_ID_RE = re.compile(r"/user/profile/([0-9a-zA-Z]+)")

LOGIN_HINT = (
    "登录态已失效：小红书返回登录墙，页面元素等待超时。"
    "请运行 xhs-tools\\xiaohongshu-mcp\\1-扫码登录.bat 重新扫码登录后重试。"
)


def _is_login_error(text: str) -> bool:
    return any(
        key in text
        for key in ("context deadline exceeded", "未登录", "登录已过期", "登录失效")
    )


class MCPClient:
    """极简 MCP (Streamable HTTP) 客户端，只用到 initialize + tools/call。"""

    def __init__(self, base: str = MCP_BASE):
        self.base = base
        self.session_id: str | None = None

    def _rpc(self, payload: dict) -> dict:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(self.base, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json, text/event-stream")
        if self.session_id:
            req.add_header("mcp-session-id", self.session_id)
        with urllib.request.urlopen(req, timeout=300) as resp:
            self.session_id = resp.headers.get("mcp-session-id") or self.session_id
            body = resp.read().decode("utf-8", "replace")
            ctype = resp.headers.get("content-type", "")
        if not body.strip():
            return {}
        if "text/event-stream" in ctype:
            for line in body.splitlines():
                if line.startswith("data:"):
                    return json.loads(line[5:].strip())
            return {}
        return json.loads(body)

    def connect(self) -> None:
        self._rpc(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "xhs-pipeline", "version": "1.0"},
                },
            }
        )
        self._rpc({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call(self, tool: str, args: dict) -> dict:
        res = self._rpc(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": tool, "arguments": args},
            }
        )
        if "error" in res:
            raise RuntimeError(f"MCP 调用 {tool} 失败：{res['error']}")
        content = (res.get("result") or {}).get("content") or []
        for item in content:
            if item.get("type") == "text":
                try:
                    return json.loads(item["text"])
                except json.JSONDecodeError:
                    return {"_text": item["text"]}
        return {}

    def login_text(self) -> str:
        """返回登录状态的可读文本。

        注意：check_login_status 会偶发误报“未登录”（页面加载时序问题），
        因此这里只作为参考信息，不能用来硬性拦截流程。
        """
        try:
            status = self.call("check_login_status", {})
        except urllib.error.URLError as exc:
            raise RuntimeError(
                "无法连接 xiaohongshu-mcp 服务（localhost:18060）。"
                "请先运行 xhs-tools\\xiaohongshu-mcp\\2-启动MCP服务.bat。"
            ) from exc
        return status.get("_text", "") or json.dumps(status, ensure_ascii=False)

    def ensure_service(self) -> None:
        """只确认 MCP 服务可达；登录态交给真实业务接口去判断。"""
        try:
            self._rpc(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/list",
                    "params": {},
                }
            )
        except urllib.error.URLError as exc:
            raise RuntimeError(
                "无法连接 xiaohongshu-mcp 服务（localhost:18060）。"
                "请先运行 xhs-tools\\xiaohongshu-mcp\\2-启动MCP服务.bat。"
            ) from exc


def load_cookie_dict(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(
            f"未找到登录 Cookie 文件：{path}"
            "请先运行 xhs-tools\\xiaohongshu-mcp\\1-扫码登录.bat 完成扫码登录。"
        )
    data = load(path.open(encoding="utf-8"))
    items = data["cookies"] if isinstance(data, dict) and "cookies" in data else data
    cookies = {i["name"]: i["value"] for i in items if i.get("name")}
    if not cookies.get("a1") or not cookies.get("web_session"):
        raise RuntimeError("Cookie 文件缺少 a1 或 web_session，登录状态无效，请重新扫码登录。")
    return cookies


def cookie_to_str(cookies: dict) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def parse_xsec_token(url: str) -> str:
    query = urllib.parse.urlparse(url).query
    return urllib.parse.parse_qs(query).get("xsec_token", [""])[0]


def expand_short(url: str) -> str:
    """短链（xhslink.*）跟随跳转展开成完整链接，其他链接原样返回。"""
    url = (url or "").strip()
    if "xhslink" in url:
        resp = requests.get(
            url,
            impersonate="chrome",
            allow_redirects=True,
            timeout=20,
            verify=False,
        )
        url = str(resp.url)
    return url


def resolve_ref(url: str) -> tuple[str, str, str]:
    """把链接规整为 (note_id, user_id, xsec_token)；短链只展开一次。

    帖子链接给 note_id，作者主页链接给 user_id，两者互斥。
    """
    url = expand_short(url)
    token = parse_xsec_token(url)
    match = NOTE_ID_RE.search(url)
    if match:
        return match.group(1), "", token
    match = USER_ID_RE.search(url)
    return "", (match.group(1) if match else ""), token


def fetch_author(mcp: MCPClient, note_id: str, xsec_token: str) -> tuple[str, str]:
    """通过 MCP 笔记详情获取作者 (user_id, nickname)，失败时自动重试。"""
    last = ""
    for attempt in range(3):
        detail = mcp.call("get_feed_detail", {"feed_id": note_id, "xsec_token": xsec_token})
        note = (detail.get("data") or {}).get("note") or {}
        user = note.get("user") or {}
        author_id = user.get("userId") or ""
        author_name = user.get("nickname") or user.get("nickName") or ""
        if author_id:
            return author_id, author_name
        last = json.dumps(detail, ensure_ascii=False)[:200]
        sleep(2 * (attempt + 1))
    raise RuntimeError(
        "未能从帖子中获取作者信息。可能原因：链接无效或已删除、作品为私密内容、"
        f"或登录态失效（可在 xhs-tools\\xiaohongshu-mcp 下重新扫码登录）。原始返回：{last}"
    )


def default_cookie_path() -> Path:
    return Path(__file__).resolve().parent.parent / "xiaohongshu-mcp" / "cookies.json"


def _nickname_from_profile(profile: dict) -> str:
    """尽力从 user_profile 返回里挖出昵称（不同版本字段位置不一）。"""
    for key in ("user", "basicInfo", "basic_info", "userInfo", "user_info"):
        obj = profile.get(key)
        if isinstance(obj, dict):
            for nk in ("nickname", "nickName", "nick_name", "name"):
                if obj.get(nk):
                    return str(obj[nk])
    for nk in ("nickname", "nickName"):
        if profile.get(nk):
            return str(profile[nk])
    return ""


def fetch_user_notes(mcp: MCPClient, user_id: str, xsec_token: str) -> tuple[list[dict], str]:
    """通过 MCP user_profile 拉取作者主页全部作品，顺带取作者昵称。"""
    profile = mcp.call(
        "user_profile",
        {"user_id": user_id, "xsec_token": xsec_token, "tab": "note"},
    )
    if not profile or "feeds" not in profile:
        raw = json.dumps(profile, ensure_ascii=False)
        if _is_login_error(raw):
            raise RuntimeError(f"{LOGIN_HINT}（原始返回：{raw[:160]}）")
        raise RuntimeError(f"user_profile 未返回作品列表：{raw[:200]}")

    notes: list[dict] = []
    seen: set[str] = set()
    nickname = ""
    for item in profile.get("feeds") or []:
        note_id = item.get("id")
        if not note_id or note_id in seen:
            continue
        seen.add(note_id)
        card = item.get("noteCard") or {}
        if not nickname:
            user = card.get("user") or {}
            nickname = user.get("nickname") or user.get("nickName") or ""
        notes.append(
            {
                "id": note_id,
                "xsec_token": item.get("xsecToken") or "",
                "title": card.get("displayTitle") or "",
                "type": card.get("type") or "",
            }
        )
    return notes, (nickname or _nickname_from_profile(profile))


def build_links(notes: list[dict]) -> list[str]:
    links = []
    for note in notes:
        token = note["xsec_token"]
        suffix = f"?xsec_token={token}&xsec_source=pc_user" if token else ""
        links.append(f"https://www.xiaohongshu.com/explore/{note['id']}{suffix}")
    return links


def classify(author_dir: Path) -> tuple[int, int]:
    """把作者目录下的作品文件夹按 图片 / 视频 归类。

    含图片文件的作品视为图文（含 Live Photo 的情况），否则视为视频。
    """
    image_root = author_dir / "图片"
    video_root = author_dir / "视频"

    pending = [
        w
        for w in sorted(author_dir.iterdir())
        if w.is_dir() and w.name not in {"图片", "视频"}
    ]
    for work in pending:
        files = [f for f in work.rglob("*") if f.is_file()]
        if not files:
            continue
        has_image = any(f.suffix.lower() in IMAGE_EXT for f in files)
        target = image_root if has_image else video_root
        target.mkdir(parents=True, exist_ok=True)
        destination = target / work.name
        if destination.exists():
            for f in files:
                move(str(f), str(destination / f.name))
            work.rmdir()
        else:
            move(str(work), str(destination))

    # 统一按最终目录结构统计，避免重复运行时数字不准
    img_count = (
        sum(1 for d in image_root.iterdir() if d.is_dir()) if image_root.is_dir() else 0
    )
    vid_count = (
        sum(1 for d in video_root.iterdir() if d.is_dir()) if video_root.is_dir() else 0
    )
    return img_count, vid_count


class _LineWriter(io.TextIOBase):
    """把 stdout 的写入按行转发给回调。"""

    def __init__(self, emit):
        self.emit = emit
        self._buf = ""

    def write(self, s):
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                self.emit(line.rstrip())
        return len(s)

    def flush(self):
        if self._buf.strip():
            self.emit(self._buf.rstrip())
            self._buf = ""


async def run_pipeline(
    url: str,
    out_dir: str,
    limit: int = 0,
    emit=None,
    dry_run: bool = False,
) -> dict:
    """执行完整流水线，返回结果摘要。emit 为日志回调。"""
    emit = emit or (lambda line: None)

    cookie_path = default_cookie_path()
    cookies = load_cookie_dict(cookie_path)

    mcp = MCPClient()
    mcp.connect()
    mcp.ensure_service()
    emit("[就绪] xiaohongshu-mcp 服务已连接")

    async with XHS(
        work_path=out_dir,
        folder_name="Download",
        name_format="发布时间 作者昵称 作品标题",
        cookie=cookie_to_str(cookies),
        image_format="JPEG",
        folder_mode=True,
        author_archive=True,
        video_cover_download=False,
        live_download=True,
        download_record=True,
        note_format="md",
        record_data=False,
        language="zh_CN",
    ) as xhs:
        with redirect_stdout(_LineWriter(emit)):
            emit("[1/4] 解析链接，定位作者主页...")
            note_id, user_id, xsec_token = resolve_ref(url)
            if note_id:
                author_id, author_name = fetch_author(mcp, note_id, xsec_token)
            elif user_id:
                # 作者主页链接：user_id 直接可用，昵称稍后从作品列表补
                author_id, author_name = user_id, ""
            else:
                raise RuntimeError(
                    "无法从链接中识别作品或作者，请用帖子链接或作者主页链接"
                    "（explore / discovery / user/profile 均可）。"
                )
            emit(f"[作者] {author_name or author_id}（{author_id}）")

            emit("[2/4] 拉取作者主页作品列表...")
            notes, nickname = fetch_user_notes(mcp, author_id, xsec_token)
            if not author_name:
                author_name = nickname
                if not author_name and notes:
                    try:
                        author_name = fetch_author(mcp, notes[0]["id"], notes[0]["xsec_token"])[1]
                    except Exception:  # noqa: BLE001
                        author_name = ""
                author_name = author_name or author_id
                emit(f"[作者] {author_name}（{author_id}）")
            if limit:
                notes = notes[:limit]
            emit(f"[作品] 共 {len(notes)} 个")
            if not notes:
                raise RuntimeError("该作者没有可下载的公开作品。")

            if dry_run:
                for note in notes:
                    emit(f"  - {note['id']} [{note['type']}] {note['title']}")
                return {
                    "author_id": author_id,
                    "author_name": author_name,
                    "total": len(notes),
                    "img_count": 0,
                    "vid_count": 0,
                    "author_dir": "",
                    "dry_run": True,
                }

            emit("[3/4] 下载作品文件（已下载的会自动跳过）...")
            await xhs.extract(" ".join(build_links(notes)), download=True)

            emit("[4/4] 按 图片 / 视频 分类归档...")
            author_dir = Path(out_dir) / "Download" / f"{author_id}_{author_name}"
            img_count = vid_count = 0
            if author_dir.is_dir():
                img_count, vid_count = classify(author_dir)
                emit(f"[完成] 图文 {img_count} 个，视频 {vid_count} 个")
                emit(f"[目录] {author_dir}")
            else:
                emit(f"[警告] 未找到作者目录：{author_dir}")

            return {
                "author_id": author_id,
                "author_name": author_name,
                "total": len(notes),
                "img_count": img_count,
                "vid_count": vid_count,
                "author_dir": str(author_dir),
                "dry_run": False,
            }