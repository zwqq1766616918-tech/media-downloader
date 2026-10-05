---
name: "media-downloader"
description: "多平台资源下载（小红书/抖音/推特X/Instagram/TikTok/微博）：引导用户装好 Chrome 与 Cookie 导出扩展、导出 cookies.txt，并用本地可视化网页按「单条链接」或「博主主页」下载。技能自带便携 Python 运行时与全部下载引擎，用户电脑上不需要装过 Python 或任何命令行工具。当用户要下载这些平台的图片/视频、要批量下载某博主全部作品、或要搭建/配置下载环境时调用。"
---

# 多平台资源下载工作台

给「**电脑水平有限的新手**」和「**连不上外网的国内用户**」准备的一整套下载方案：
从装浏览器、装扩展、导出 Cookie，到打开一个**可视化网页**点按钮下载，全流程有人带着走。

> **开箱即用**：技能包自带便携 Python 运行时和全部下载引擎。
> 用户电脑上**不需要装过 Python、pip、uv、gallery-dl、yt-dlp 或任何命令行工具**，
> 解压即用。配置向导也**不会去翻用户的硬盘**。

> 本 skill 里**不含任何个人凭据**。`cookies.txt` 一律由用户自己在本地导出，只存在用户自己的电脑上。

---

## 一、能做什么

| 能力 | 说明 |
| --- | --- |
| 单条下载 | 粘贴一条作品链接，只下载那一条 |
| 主页批量 | 粘贴博主主页链接，下载该号全部作品 |
| 可视化界面 | 本地网页，大按钮、状态灯、进度条，无需命令行 |
| 开机自启 | 可一键加入开机自动后台运行（需先征询用户） |

支持的平台：**小红书、抖音、推特 X、Instagram、TikTok、微博**。

平台能力差异（务必先告知用户，避免踩空）：

- 抖音：**主页和单条都支持**（`/user/`、`/video/`、`/note/`、`v.douyin.com` 短链、纯数字 ID 都行）；
  需要额外装「抖音补充包」，且电脑上要有 Chrome / Edge（本包不带浏览器内核，见第六节）
- 小红书：必须先启动本地 MCP 服务并**扫码登录**，否则报「MCP 服务未启动」
- 推特 / Instagram / 微博 / TikTok：需要 `cookies.txt`，缺失时自动退回读本机 Chrome 登录态（不一定成功）

---

## 二、标准引导流程（按顺序带用户走）

### 第 0 步：先问清楚

在动手前，先确认三件事：

1. 要下载哪个平台、是「整个主页」还是「单条」？
2. 这台电脑**能不能上外网**？（决定用国内镜像还是官方地址）
3. 之前有没有配过？（若有 `config.json` 可跳过第 3 步）

### 第 1 步：确认有浏览器

需要 **Chrome 或 Edge**。国内用户**连不上外网也能装**，给用户这三条路（按推荐顺序）：

| 用途 | 地址 | 说明 |
| --- | --- | --- |
| Chrome 官方中国站（离线安装包） | `https://www.google.cn/chrome/?standalone=1&platform=win64` | 必须带 `standalone=1` 才是**离线包**，安装时无需联网 |
| 国内镜像（阿里 npmmirror） | `https://registry.npmmirror.com/binary.html?path=chrome-for-testing/` | 进 `win64` 取 `chrome-win64.zip`，解压即用，**纯国内直连最稳** |
| Edge 官方下载页 | `https://www.microsoft.com/zh-cn/edge` | Windows 10/11 一般自带，可直接用，无需额外安装 |

**优先推荐 Edge**：Win10/11 绝大多数机器已经预装，让用户先试「开始菜单搜 Edge」，
能打开就直接用，省掉装浏览器这一步。若 `google.cn` 打不开，直接让用户走 npmmirror 镜像。

> 注意：**不需要**装 Python，也不需要装任何下载引擎 —— 技能包里都带好了。
>
> 已经拿到技能包的用户，可以直接双击 `app/安装浏览器.bat`：它会先自动检测本机
> 有没有 Chrome / Edge，找到了直接提示「无需再装」；没找到才给出上面三种办法，
> 并自动打开下载页。**抖音**就是靠这个浏览器来生成签名和保存扫码登录态的。

### 第 2 步：装 Cookie 导出扩展（离线，不用商店）

扩展本体已随 skill 附带：`assets/cookie导出工具/扩展_Get-cookies.txt-LOCALLY_v0.7.2/`

1. 让用户双击 `assets/cookie导出工具/一键安装扩展.bat`（会自动复制路径 + 打开 `chrome://extensions`）
2. 打开右上角「**开发者模式**」
3. 点「**加载已解压的扩展程序**」
4. 选择上面那个 `扩展_Get-cookies.txt-LOCALLY_v0.7.2` **文件夹本身**
5. 列表出现 **Get cookies.txt LOCALLY** 即成功，建议「固定到工具栏」

> 详细图文步骤与常见问题见 `references/环境准备.md`。
> 该扩展开源（MIT），只在本机读取 Cookie 生成文件，**不会把数据发到外部**。

### 第 3 步：导出各平台 cookies.txt

用 Chrome **登录目标网站** → 停在那个网站上 → 点扩展图标 → 格式选 **Netscape** → 点 **Export** →
把下载到的文件改名为 `cookies.txt`，放到技能目录下 `cookies/<平台>/`：

| 平台 | 登录的网站 | 放到 |
| --- | --- | --- |
| 推特 X | `https://x.com` | `cookies/twitter/cookies.txt` |
| Instagram | `https://www.instagram.com` | `cookies/instagram/cookies.txt` |
| 微博 | `https://weibo.com` | `cookies/weibo/cookies.txt` |
| TikTok | `https://www.tiktok.com` | `cookies/tiktok/cookies.txt` |

> `cookies/` 目录由配置向导自动创建，里面还放了一份「把导出的文件放这里.txt」提示。
> 小红书和抖音**不用这个扩展**，它们走扫码登录。

各平台必须包含的关键字段（缺了基本抓不到数据）：
微博 `SUB`/`SUBP`、Instagram `sessionid`/`csrftoken`、推特 `auth_token`/`ct0`、TikTok `sessionid`。

### 第 4 步：跑配置向导

让用户**双击 `app/配置向导.bat`** 即可（也可以 `python "app/配置向导.py" --check` 只体检）。

- 检测到自带的 `runtime/` 和 `engines/` 时，它**直接生成配置，不会扫描本机**；
- 只有在自带件缺失（老用户自行改过包）时，才会退回去扫描本机的下载引擎。

体检结果里标 `×` 的项，就是用户还需要补的步骤——照着提示补。

### 第 5 步：启动可视化下载界面

双击 `app/启动下载工作台.bat`，浏览器会自动打开 `http://127.0.0.1:8790`。

**务必把「以后怎么启动」讲清楚**（这是新手最容易卡住的地方）：

- 以后每次要用，**双击 `启动下载工作台.bat`** 就行，网页会自动弹出来
- 也可以手动在浏览器输入：`http://127.0.0.1:8790`
- 后台那个**黑色窗口不能关**，关掉就等于停掉服务
- 页面本身可以随便关，不影响下载

### 第 6 步：询问是否加入开机自启

**主动问用户一句**：「要不要设置成开机自动在后台运行？这样以后开电脑就能直接用，不用每次双击。」

- 同意 → 双击 `app/开机自启-开启.bat`
- 想取消 → 双击 `app/开机自启-关闭.bat`

加入自启后：开机自动在后台运行（不弹黑窗口、不自动开浏览器），
用户只要打开浏览器访问 `http://127.0.0.1:8790` 即可。

---

## 三、界面怎么用（讲给用户听）

1. **粘贴链接**：主页链接或单条链接都行，可以一次粘多条（每行一条）
2. **选方式**：「下载整个主页」/「只下载这一条」
3. **选保存位置**：默认已设好；想换就点「选择文件夹」
4. **数量上限**（可选）：想先试水填 `20`，留空就是全部
5. 点 **开始下载**，在下面「下载记录」看进度

顶部状态灯：**绿色**=该平台已就绪；**红色**=还没配好，鼠标放上去会显示原因。

---

## 四、目录结构

```
media-downloader/
├── SKILL.md                  ← 本文件
├── runtime/                  ← 【自带】便携运行时，用户无需装 Python
│   ├── python/               便携 Python 3.12（跑 gallery-dl / 小红书 / TikTok）
│   └── pkgs/                 各引擎的依赖包组
│       ├── gallerydl/        gallery-dl + yt-dlp + 依赖
│       ├── xhs/              小红书 XHS-Downloader 的依赖
│       └── mediacrawler/     （可选补充包）抖音 MediaCrawler 的依赖
├── engines/                  ← 【自带】下载引擎
│   ├── tiktok/tiktok_dl.py   TikTok 下载器
│   ├── xhs-downloader/       小红书 XHS-Downloader 源码
│   ├── xiaohongshu-mcp/      小红书 MCP 服务（含扫码登录）
│   └── mediacrawler/         （可选补充包）抖音 MediaCrawler 源码
├── tools/
│   └── 打包-抖音补充包.py     维护用：把本机 MediaCrawler 打成抖音补充包
├── references/
│   ├── 环境准备.md            ← 浏览器/扩展/cookie 的详细图文步骤（含国内下载地址）
│   ├── 平台与引擎对照.md       ← 每个平台用什么引擎、需要什么凭据
│   └── 故障排查.md            ← 常见报错与处理
├── assets/
│   └── cookie导出工具/         ← 离线版 Cookie 导出扩展 + 一键安装脚本
├── app/
│   ├── 下载工作台.py           ← 本地下载服务（只用 Python 标准库）
│   ├── 配置向导.py             ← 生成 config.json（自带件优先，不扫本机）
│   ├── config.example.json     ← 配置模板（不含任何个人信息）
│   ├── 网页/index.html         ← 可视化下载界面
│   ├── engine/xhs_worker.py    ← 小红书下载子进程（便携版）
│   ├── 启动下载工作台.bat
│   ├── 配置向导.bat
│   ├── 安装浏览器.bat          ← 检测/引导安装 Chrome 或 Edge（抖音用）
│   ├── 开机自启-开启.bat
│   ├── 开机自启-关闭.bat
│   └── 后台启动.vbs
└── cookies/                  ← 用户自己导出的 cookies.txt（运行后才有）
```

运行时才会产生、**不随包分发**的三项：`config.json`（向导生成）、`运行记录/`、`下载/`。
装了抖音补充包还会多出 `runtime/python311/`。抖音所需的浏览器**不随包分发**，
用用户本机已装的 Chrome / Edge（没有就引导他双击 `app/安装浏览器.bat`）。

---

## 五、分享给别人之前（重要）

技能包**出厂时就不含**任何个人数据，可以直接分享。分享前只确认这三项不存在：

- `config.json`（里面记着本机路径）
- `运行记录/`（任务历史与日志）
- `下载/`（下载下来的内容）

另外，`cookies/` 目录里如果有你自己导出的 `cookies.txt`，**也必须删掉**再分享。
`cookies.txt` 从来不进 `assets/`、`app/`、`references/`、`runtime/`、`engines/`，
只存在用户自己电脑上。

对方拿到后双击 `app/配置向导.bat` 就能用。

---

## 六、抖音补充包（可选）

抖音走 MediaCrawler，它的依赖是 Python 3.11 编译的（跟主运行时的 3.12 不通用），
加起来约 600 MB，所以**不放进主包** —— 装不装都不影响其它五个平台。

抖音需要一个**真实浏览器**来执行签名脚本、保存扫码登录态。
本包**不再自带 Playwright 的 Chromium 内核**（约 400MB），改为复用用户本机已装的
Chrome / Edge（MediaCrawler 侧读环境变量 `MC_BROWSER_PATH`）。

**分发时把补充包一起带上**（在技能目录下执行，需要本机已装好 MediaCrawler）：

```bash
python tools/打包-抖音补充包.py
```

它会产出：

| 路径 | 内容 |
| --- | --- |
| `engines/mediacrawler/` | MediaCrawler 源码（已剔除登录态、下载数据）+ 三个启动脚本 |
| `runtime/python311/` | 便携 Python 3.11 |
| `runtime/pkgs/mediacrawler/` | MediaCrawler 的依赖 |

打包完再跑一次配置向导，抖音状态灯就会变绿。

**抖音的三种用法**：

| 方式 | 说明 |
| --- | --- |
| 界面里粘主页链接 | 自动按「下载整个主页」采集该博主全部作品 |
| 界面里粘单条链接 | 自动按「只下载这一条」处理（`/video/`、`/note/`、短链、纯数字 ID） |
| 双击 `engines/mediacrawler/3-下载抖音单条作品.bat` | 不开界面，直接命令行单条下载 |

第一次会**弹出浏览器窗口**，用抖音 App 扫码登录即可，登录态缓存在
`engines/mediacrawler/browser_data/`，之后一般不用重复登录。

> 不想带抖音：跳过这一步即可，抖音状态灯会显示「未安装抖音补充包（可选）」。
> 想删掉已打的包：`python tools/打包-抖音补充包.py --clean`
> 电脑上没有 Chrome / Edge 时，抖音状态灯会提示「缺少浏览器」，
> 让用户双击 `app/安装浏览器.bat` 按引导装即可。

---

## 七、硬性约束

- **绝不**读取、复制、上传用户的 `cookies.txt` 内容；只把它当作路径传给下载器
- **绝不**把用户的 Cookie、账号、下载内容写进 skill 的任何文件
- **绝不**在自带件齐全时扫描用户硬盘
- 抖音**不需要**浏览器内核随包分发；缺浏览器时引导用户双击 `app/安装浏览器.bat`，不要自己塞内核
- 下载任务串行执行（单 worker），不要并发拉多个平台
- 首次使用务必先跑配置向导；`config.json` 不存在时启动脚本会自动引导