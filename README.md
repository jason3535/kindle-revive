# kindle-revive · 让吃灰的 Kindle 重新活过来

给吃灰几年的 Kindle 做个改造：

1. **连上 MCP，电脑上的书一键发送过去**——在 Claude Code / Claude Desktop 里说一句「把这本书发到 Kindle」就行；
2. **和电脑上的 Apple Books 阅读进度保持同步**——在 Mac 上读到哪，Kindle 打开就跳到哪；
3. **Kindle 上的高亮笔记自动汇入全局笔记**——Kindle 原生摘录、KOReader 划线、Apple Books 标注合并去重，电脑上有可视化页面（今日回顾 / 全文搜索 / 书架 / 知识点图谱 / 单词本）；
4. **最重要的：[AI Podcast](https://aipodcast.jasonlin.tech) 播客内容可以在 Kindle 上阅读**——内容源已预置进 KOReader 插件，打开即读。

外加一张《神奈川冲浪里》休眠壁纸。

> English summary at the [bottom](#english-summary).

---

## ⚠️ 兼容性与免责声明

- **实测设备只有一台：Kindle Paperwhite 3（第七代，2015）固件 5.16.2.1.1**，KOReader `kindlepw2` 包 v2026.07.x，macOS（Apple Silicon）。
- 其他型号 / 固件 **未经测试**，越狱方法与 KOReader 安装包都可能不同，务必先用 [Kindle Modding 越狱向导](https://kindlemodding.org/jailbreak-wizard.html) 确认。
- 越狱有变砖风险、可能违反亚马逊条款、失去保修。**后果自负**。动手前请完整备份 Kindle 的 `documents/`。
- 本路线（WinterBreak）**不清空设备上已有的书**，原生阅读器照常可用，KOReader 是另起的一个 App。
- 本仓库**不分发任何第三方二进制**（越狱包、hotfix、KOReader），只给链接和步骤。
- 第 3 项（高亮页面）与第 1 项的 Apple Books 部分依赖 macOS；Windows/Linux 未测试。

## 功能一览

| 模块 | 目录 | 需越狱 | 说明 |
|---|---|---|---|
| 越狱 + KOReader | `jailbreak/` `koreader/` | 是 | 步骤文档、启动器脚本、SSH/inspector 配置模板 |
| MCP 推书 | `mcp/` `scripts/rezip_applebooks_epub.sh` | 是 | 基于 [mcp-show-on-kindle](https://pypi.org/project/mcp-show-on-kindle/) |
| 进度同步 | `sync/sync_progress.py` | 是 | Apple Books CFI → KOReader XPointer |
| 高亮站点 | `highlights/` | 否（KOReader 划线需越狱） | 单文件离线网页 + 可导出 AZW3 给 Kindle 读 |
| AI Podcast 插件 | `plugin/simpleui.koplugin` | 是 | KOReader SimpleUI 改版，预置 aipodcast 内容源 |
| 休眠壁纸 | `wallpaper/` | 是（KOReader 屏保） | 1072×1448 灰度 |

## 架构

```mermaid
flowchart LR
  subgraph Mac["电脑 (macOS)"]
    AB[(Apple Books<br/>AEAnnotation / BKLibrary sqlite)]
    EP[~/Downloads/kindle-books<br/>EPUB]
    CC[Claude Code / Desktop]
    MCP[mcp-show-on-kindle<br/>uvx]
    SYNC[sync_progress.py]
    HL[highlights/refresh.py<br/>→ index.html]
  end
  subgraph Kindle["Kindle PW3 (越狱)"]
    KO[KOReader]
    SSH[SSH :2222<br/>密钥登录]
    INS[HTTP inspector :8080<br/>仅回环]
    DOC[/mnt/us/documents/llm/]
    SDR[.sdr 划线]
    PL[SimpleUI · AI Podcast 插件]
  end
  SITE[(aipodcast.jasonlin.tech<br/>/kindle/api 静态 JSON)]

  CC --> MCP -- scp over SSH --> DOC
  AB --> EP
  AB -- 最后阅读位置 CFI --> SYNC -- SSH → curl 127.0.0.1:8080 --> INS --> KO
  AB --> HL
  SDR -- parse_koreader.py --pull --> HL
  PL -- HTTPS --> SITE
  KO --- PL
```

## 目录

```
.
├── README.md / LICENSE (MIT) / NOTICE.md
├── jailbreak/        KOReader 启动器脚本模板
├── koreader/         settings 片段、koreader.sh 防火墙补丁说明
├── mcp/              Claude Code / Desktop 配置示例
├── scripts/          SSH 密钥安装、kssh、EPUB 重打包、插件安装/卸载、壁纸
├── sync/             Apple Books → KOReader 进度同步
├── highlights/       高亮管线 + 页面模板（sample/ 是虚构示例数据）
├── plugin/           simpleui.koplugin（GPL-3.0，AI Podcast 版）
└── wallpaper/        休眠壁纸
```

---

## 1. 越狱（PW3 / 5.16.2.1.1，WinterBreak2）

> 国区 Kindle 商店已关闭，原版 WinterBreak 依赖商店页面，这里用 **WinterBreak2 v1.0.0 + 体验版浏览器（Experimental Browser）** 的路线。

1. 备份：USB 连电脑，把整个 Kindle 盘拷一份。（macOS 终端报 `Operation not permitted` 读不了 `/Volumes/Kindle` 时：`tccutil reset SystemPolicyRemovableVolumes com.apple.Terminal`，不用重启。别用 Finder 让 AppleScript 代拷，会产出 0 字节空壳。）
2. 打开飞行模式之外的 Wi-Fi，在 Kindle 的 **体验版浏览器** 打开 <https://penguins184.xyz/wb2>，按页面提示操作（详见 [WinterBreak 文档](https://kindlemodding.org/jailbreaking/WinterBreak/)）。
3. 越狱成功后，安装 **hotfix**：从 [Kindle Modding](https://kindlemodding.org/jailbreaking/post-jailbreak/installing-hotfix/) 下载 `Update_hotfix_universal.bin`（实测 v2.5.0），拷到 Kindle 根目录，「设置 → 更新您的 Kindle」。hotfix 让越狱在重启/系统更新后保持。
4. （可选）安装 KUAL / MRPI，参照 [post-jailbreak 指南](https://kindlemodding.org/jailbreaking/post-jailbreak/)。
5. 每一步拔线前都要在访达里**先推出宗卷**，硬拔会造成 FAT 损坏（出现删不掉也拷不走的「孤立目录项」）。

## 2. 安装 KOReader

1. 从 [KOReader Releases](https://github.com/koreader/koreader/releases) 下载 **`koreader-kindlepw2-*.zip`**（PW2 包覆盖 PW2 之后、固件 < 5.16.3 的 soft-float 机型；5.16.3+ 的新机器要用 `kindlehf` 包——**未测试**）。
2. 解压，把 `koreader/` 文件夹拷到 Kindle 根目录（即 `/mnt/us/koreader`）。
3. 把 `jailbreak/koreader_launcher_asap.sh`（和可选的 `koreader_launcher_no_framework.sh`）拷进 Kindle 的 `documents/`（或 KUAL 的 extensions），书架上点它即可启动 KOReader。
   - `--asap`：常规启动；`--framework_stop`：停掉亚马逊框架，省内存，但退出前原生界面不可用。
4. 推出宗卷，在书架点启动器。

## 3. SSH + HTTP inspector 配置

在 KOReader 里：**工具 → 更多工具 → SSH 服务器**：端口 `2222`、开机自启、仅密钥登录；**HTTP inspector**：开机自启、端口 `8080`。等价配置见 `koreader/settings.snippet.lua`。

```bash
export KINDLE_HOST=<Kindle 局域网 IP>     # Kindle：设置 → 设备选项 → 设备信息 里能看到
./scripts/install_ssh_key.sh             # 生成 ~/.config/mcp-show-on-kindle/id_ed25519 并装公钥
./scripts/kssh.sh 'uname -a'             # 验证
```

首次装公钥时需要临时打开「允许无密码登录」，装好后关掉。之后给 inspector 加防火墙（它无鉴权）：

```bash
./scripts/kssh.sh 'sh -s' < scripts/patch_koreader_sh.sh   # 在 koreader.sh 里加一行：
# iptables -I INPUT 1 -p tcp --dport 8080 ! -i lo -j DROP
```

之后 8080 只有 Kindle 本机能访问，电脑端都通过 `kssh.sh "curl http://127.0.0.1:8080/koreader/..."` 调用。

## 4. MCP：电脑上的书一键发到 Kindle

用 [mcp-show-on-kindle](https://pypi.org/project/mcp-show-on-kindle/)（`uvx` 运行，需先装 [uv](https://docs.astral.sh/uv/)）。它通过 SSH 把文件推到 Kindle 的 `/mnt/us/documents/llm/`，KOReader 里刷新即见。

**Claude Code**（`~/.claude.json` 的 `mcpServers`，或 `claude mcp add`）/ **Claude Desktop**（`~/Library/Application Support/Claude/claude_desktop_config.json`）都用同样的结构，见 `mcp/*.example.json`：

```json
{
  "mcpServers": {
    "show-on-kindle": {
      "type": "stdio",
      "command": "uvx",
      "args": ["mcp-show-on-kindle"],
      "env": { "KINDLE_ALLOWED_DIRECTORIES": "~/Downloads/kindle-books,~/Documents/books" }
    }
  }
}
```

要点：
- `KINDLE_ALLOWED_DIRECTORIES` 用 **逗号** 分隔（源码是 `split(",")`），写成冒号会把所有路径都拒掉。
- 其余参数（Kindle 地址、密钥位置等）以上游 README 为准；本仓库脚本默认密钥在 `~/.config/mcp-show-on-kindle/`。
- **Apple Books 的 .epub 在磁盘上是文件夹**，要先重打包：
  ```bash
  ./scripts/rezip_applebooks_epub.sh "~/Library/Containers/com.apple.BKAgentService/Data/Documents/iBooks/Books/<书>.epub"
  # 等价于 cd 书目录 && zip -X0 out.epub mimetype && zip -Xr9D out.epub . -x mimetype
  ```
- MCP 没连上时可以直接推：`./scripts/kssh.sh "cat > /mnt/us/documents/llm/书.epub" < 书.epub`
- 原生阅读器（不越狱）**不认 EPUB**，要用 calibre 转 AZW3：`ebook-convert in.epub out.azw3 --output-profile kindle_pw3`。

## 5. Apple Books → KOReader 进度同步

```bash
pip3 install lxml
export KINDLE_HOST=<Kindle IP>
python3 sync/sync_progress.py plan            # 只看换算结果
python3 sync/sync_progress.py push [书名关键字] # 让 Kindle 打开书并跳到 Apple Books 的位置
```

原理：Apple Books 的最后位置是 `AEAnnotation` 库中 `ZANNOTATIONTYPE=3` 记录的 EPUB CFI；用本地同一份 EPUB（默认 `~/Downloads/kindle-books`，按 `dc:title == ZTITLE` 匹配，同一份文件需已推到 Kindle 的 `/mnt/us/documents/llm`）换算成 crengine XPointer（`/body/DocFragment[spine序号]/body/...`），再经 SSH 调 inspector：先 `switchDocument` 打开书，再 `ui/rolling/onGotoXPointer/"xp"/` 跳转。**不改 .sdr 文件**，避免被运行中的 KOReader 覆盖。

- 需要给终端 **完全磁盘访问权限**（系统设置 → 隐私与安全性 → 完全磁盘访问），否则读不到 Apple Books 容器。
- 反向同步（Kindle → Apple Books）**未实现**（要改 Apple 数据库并经 iCloud，风险高）。

## 6. 高亮笔记站点

```bash
cd highlights
# 试跑示例数据（虚构）
cp sample/vocab_zh.json . && python3 parse_clippings.py "sample/My Clippings.txt" && python3 build.py && open index.html
# 实际使用：一条命令拉取三个来源并重建
python3 refresh.py
```

| 来源 | 脚本 | 取法 |
|---|---|---|
| Kindle 原生 `My Clippings.txt` | `parse_clippings.py` | Kindle 插着 USB 时 `refresh.py` 自动从 `/Volumes/KINDLE` 拷到 `_kindle/` |
| KOReader 划线（`.sdr/metadata.*.lua`） | `parse_koreader.py --pull` | Wi-Fi SSH 拉取，Kindle 不在线就沿用上次 |
| Apple Books 标注 | `parse_applebooks.py` | 直接读容器 sqlite（连 `-wal` 一起拷） |

产物 `index.html` 是单文件离线站（数据内嵌）：今日回顾、全文搜索、书架、知识点图谱（`concepts.json` 定义概念与正则，可按自己的阅读改）、单词本（释义写在 `vocab_zh.json`，`build.py` 会列出缺释义的词）。`make_epub.py` 可把摘录导出 EPUB，再用 calibre 转 AZW3 放到 Kindle 上读（PW3 自带浏览器跑不动这个网页）。

**macOS 权限（TCC）注意：**
- Apple Books 容器受保护，**终端要有完全磁盘访问权限**；授权跟随终端进程，所以从终端（或在终端里运行的 Claude Code）跑 `refresh.py` 可以，**launchd 定时任务会报 `PermissionError`**。
- 读 `/Volumes/KINDLE` 报 `Operation not permitted`：`tccutil reset SystemPolicyRemovableVolumes com.apple.Terminal`。
- sqlite 必须连 `-wal` 一起拷，并以读写方式打开副本，否则最近的标注会被静默漏掉。

`.gitignore` 已排除所有个人数据（`*.json` 产物、`index.html`、`_kindle/` 等）。

## 7. AI Podcast 插件（KOReader SimpleUI 改版）

基于 [joeseesun/qiaomu-simpleui](https://github.com/joeseesun/qiaomu-simpleui) v3.0.0（SimpleUI 3.0 改版，GPL-3.0），版本 `3.0.0-aipodcast.1`：

- 底栏「播客」页读取 **aipodcast.jasonlin.tech** 的 `/kindle/api` 静态 JSON（`entries`、`channels`、`sources/<id>/entries`），文章取 `/mcp-data/ep/<id>.json` 在设备端排版、跳过广告段；
- 人物 = 频道，按领域分组，预置在 `data/qiaomu_sources.json`；
- 去掉了原版的 AI 助手、自动更新等入口。
- 站点侧数据生成器在 [jason3535/aipodcast](https://github.com/jason3535/aipodcast) 的 `pipeline/gen_kindle_api.py`，想换成自己的内容源可改 `features/sui_news.lua` 里的 `ORIGIN` / `API`。

安装 / 卸载：

```bash
export KINDLE_HOST=<Kindle IP>
./scripts/install_plugin.sh     # 备份到 /mnt/us/koreader-backup-<时间>/，tar over SSH 装到 plugins/，重启 KOReader
./scripts/uninstall_plugin.sh   # 删 plugins/simpleui.koplugin 并重启
```

不用 SSH 的话：USB 连接，把 `plugin/simpleui.koplugin` 整个文件夹拷到 `koreader/plugins/`（**先退出 KOReader 再挂载**）。
换过数据源后要删 `koreader/settings/simpleui/news` 缓存。首次拉取 GitHub Pages 大约 7 秒 / 90KB，单篇文章超时设为 120 秒。

## 8. 休眠壁纸

`wallpaper/great-wave-pw3.png`（1072×1448 灰度，公有领域）。`./scripts/set_wallpaper.sh` 上传到 `/mnt/us/koreader/screensaver/`，然后在 KOReader 里 **设置 → 屏幕 → 屏保** 选这张图。
**只在 Kindle 醒着时改屏保设置**——休眠时 inspector 不通，直接改 `settings.reader.lua` 会被内存中的值覆盖。

---

## 常见坑（Troubleshooting）

| 现象 | 原因 / 解决 |
|---|---|
| SSH 偶尔 `Connection refused` / 扫描找不到 Kindle | Kindle 休眠后 Wi-Fi 重连有空窗；先点亮屏幕，等几秒重试。局域网扫描**扫两轮**，第一轮休眠中的 Kindle 常不应答 |
| USB 挂载后文件不一致 / 损坏 | **先退出 KOReader 再挂载**；拔线前在访达里推出 |
| 原生阅读器看不到 EPUB | PW3 原生不支持 EPUB，用 KOReader 打开，或 calibre 转 AZW3 |
| inspector `event/GotoXPointer` 返回 `Event sent` 但没跳转 | 要用 `ui/rolling/onGotoXPointer/"<xp>"/`；而重启用 `event/Restart/` 是有效的 |
| 改了屏保设置不生效 | 只在 Kindle 醒着、KOReader 运行时通过菜单改 |
| Kindle 上出现 `._xxx` 文件 / 插件报错 | macOS tar 会带 AppleDouble，用 `COPYFILE_DISABLE=1 tar ...` |
| zsh 里 `tar $FILES` 只传了一个“文件” | zsh 默认不对 `$VAR` 分词，用 `${=FILES}` |
| MCP 拒绝所有目录 | `KINDLE_ALLOWED_DIRECTORIES` 必须逗号分隔 |
| 推过去的 Apple Books 书打不开 | 那是文件夹，用 `rezip_applebooks_epub.sh` 重打包（`mimetype` 首个且不压缩） |
| 改 Lua 后插件白屏 | 在 Kindle 上 `luajit -e 'assert(loadfile("文件.lua"))'` 检查语法 |
| 插件升级后 AI Podcast 不见了 | 若通过上游更新覆盖了插件，重新运行 `install_plugin.sh` |
| GitHub 访问慢 | 给 git/gh 设代理，如 `export https_proxy=http://127.0.0.1:7890` |

## FAQ：如何撤销 / 卸载

- **卸载插件**：`./scripts/uninstall_plugin.sh`，或删 `koreader/plugins/simpleui.koplugin`。原设置备份在 `/mnt/us/koreader-backup-*/`。
- **卸载 KOReader**：删 Kindle 根目录的 `koreader/` 和 `documents/` 里的启动器脚本即可，原生阅读器与书籍不受影响。
- **撤销防火墙补丁**：`cp /mnt/us/koreader/koreader.sh.bak /mnt/us/koreader/koreader.sh`。
- **停用 MCP**：从 Claude 配置里删除 `show-on-kindle` 条目；删 Kindle 上的 `documents/llm/`。
- **撤销越狱**：参考 [Kindle Modding](https://kindlemodding.org/) 的卸载说明；也可以恢复出厂设置（会清空设备）。hotfix 会让越狱在系统更新后保留。
- **会不会删我的书？** WinterBreak 路线实测不清空书籍；但仍请先备份。
- **其他型号能用吗？** 未测试。脚本部分（MCP、同步、高亮、插件）只依赖 KOReader + SSH，理论上通用；越狱与安装包请按型号查越狱向导。

## 许可

自有代码 MIT（见 `LICENSE`）；`plugin/simpleui.koplugin/` 为 GPL-3.0-or-later；第三方致谢见 `NOTICE.md`。

---

## English summary

**kindle-revive** turns an old, jailbroken Kindle (tested only on a Paperwhite 3, FW 5.16.2.1.1, KOReader kindlepw2 v2026.07) into a companion for your Mac:

1. **Send books from your computer via MCP** (`mcp-show-on-kindle` with Claude Code / Claude Desktop; note `KINDLE_ALLOWED_DIRECTORIES` is comma-separated; Apple Books EPUBs are folders and must be re-zipped — see `scripts/rezip_applebooks_epub.sh`).
2. **Sync reading position from Apple Books to KOReader** (`sync/sync_progress.py`, converts EPUB CFI → crengine XPointer and jumps via the HTTP inspector over SSH).
3. **Merge highlights** from Kindle clippings, KOReader and Apple Books into a single offline HTML page (`highlights/`, macOS Full Disk Access required for Apple Books).
4. **Read [AI Podcast](https://aipodcast.jasonlin.tech) on the Kindle** with a modified SimpleUI KOReader plugin (GPL-3.0, based on joeseesun/qiaomu-simpleui) with preset sources.

Jailbreak route: WinterBreak2 via the Experimental Browser → hotfix → manual KOReader install. No third-party binaries are redistributed; follow the upstream links. Jailbreaking is at your own risk. Other models are untested. Own code is MIT; the plugin is GPL-3.0.
