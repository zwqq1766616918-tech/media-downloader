# media-downloader · 多平台资源下载工作台

给电脑新手用的一站式下载工具，支持 **小红书 / 抖音 / 推特 X / Instagram / TikTok / 微博** 六个平台。

粘一条作品链接就下这一条，粘博主主页链接就下他全部作品。不用命令行，打开就是个本地网页，大按钮、状态灯、进度条，点一下开始下载。想装 Cookie 扩展、导出 `cookies.txt`，包里也都有图文引导一步步带着走。

**开箱即用** —— 自带便携 Python 运行时和全部下载引擎，你电脑上不用装过 Python、pip、uv、gallery-dl、yt-dlp，解压就能跑。

**不碰你的隐私** —— 仓库里不含任何个人凭据，`cookies.txt` 由你自己在本地导出，只存在你自己电脑上。

---

## English

A one-stop downloader built for non-technical users. Supports **Xiaohongshu, Douyin, X (Twitter), Instagram, TikTok, and Weibo**.

Paste a single post link to grab just that post, or paste a creator's profile link to pull their entire feed. No command line needed — it opens as a local web page with big buttons, status lights, and a progress bar. Step-by-step guides for installing the cookie extension and exporting `cookies.txt` are bundled in.

**Ready out of the box** — ships with a portable Python runtime and every download engine, so you don't need Python, pip, uv, gallery-dl, or yt-dlp installed. Just unzip and run.

**Your privacy stays yours** — this repository contains no personal credentials. You export `cookies.txt` locally yourself, and it never leaves your machine.

---

## 支持的平台

| 平台 | 单条 | 主页批量 | 登录方式 |
| --- | :-: | :-: | --- |
| 小红书 | ✅ | ✅ | 扫码登录本地 MCP 服务 |
| 抖音 | ✅ | ✅ | 扫码登录（需额外装补充包） |
| 推特 X | ✅ | ✅ | `cookies.txt` |
| Instagram | ✅ | ✅ | `cookies.txt` |
| TikTok | ✅ | ✅ | `cookies.txt` |
| 微博 | ✅ | ✅ | `cookies.txt` |

## 快速开始

1. 下载本仓库（`git clone` 或下载 ZIP 后解压）
2. 双击 `app/配置向导.bat` —— 它会自动找齐运行环境和引擎
3. 双击 `app/启动下载工作台.bat` —— 浏览器会自动打开操作界面
4. 把作品链接粘进去，选「只下载这一条」或「下载整个主页」，点开始

想装抖音：先双击 `app/安装浏览器.bat` 确认电脑上有 Chrome 或 Edge，再跑一次
`python tools/打包-抖音补充包.py`。抖音**不需要**装 Node.js，签名要的 JS 运行时由包里自带。

## 目录结构

```
media-downloader/
├── SKILL.md              ← 完整使用说明（技能定义）
├── app/                  ← 配置向导、下载工作台、可视化网页
├── references/           ← 环境准备、平台对照、故障排查
├── engines/              ← 各平台下载引擎
├── assets/               ← Cookie 导出扩展等素材
├── runtime/              ← 便携 Python 运行时与依赖（约 670 MB）
├── tools/                ← 打包脚本
└── cookies/              ← 放你自己导出的 cookies.txt（默认空）
```

## 隐私

以下内容**不会**进入版本库（见 `.gitignore`）：

- `config.json`（配置向导生成，含本机路径）
- `运行记录/`、`下载/`（任务历史与下载内容）
- `cookies/**/cookies.txt`、`cookies/**/cookies.json`（登录凭据）
- 抖音登录态与采集数据（`engines/mediacrawler/browser_data/`、`data/`）

## 第三方组件

`engines/`、`assets/` 和 `runtime/` 下包含若干第三方开源项目及其依赖，它们各自遵循自己的许可协议，版权归各自作者所有。分发或二次使用前请一并查看对应目录中的许可文件。

## 许可

本仓库以 [Apache License 2.0](LICENSE) 发布。
