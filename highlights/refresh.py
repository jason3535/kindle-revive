#!/usr/bin/env python3
"""一键刷新：抓两个来源的最新标注 → 重新解析 → 重建页面 → 报告新增。

Apple Books 直接从容器读（授权已持久化，不用再手工导文件）。
Kindle 只有在设备插着时才更新，没插就沿用上次备份的 My Clippings.txt。
KOReader 的划线不进 My Clippings，另走 Wi-Fi SSH 拉 .sdr（parse_koreader.py --pull，不在线就沿用上次）。

    python3 refresh.py            # 刷新
    python3 refresh.py --quiet    # 只在有新增时输出，给定时任务用
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
BOOKS_SRC = Path.home() / "Library/Containers/com.apple.iBooksX/Data/Documents"
BOOKS_DST = HERE / "_applebooks"
KINDLE_VOL = Path("/Volumes/KINDLE")
CLIPPINGS = HERE / "_kindle" / "My Clippings.txt"

QUIET = "--quiet" in sys.argv


def say(*a):
    if not QUIET:
        print(*a)


def counts():
    """当前页面里的条数，用来对比刷新前后。"""
    f = HERE / "index.html"
    if not f.exists():
        return {}
    try:
        import re
        blob = re.search(r'<script id="data" type="application/json">(.*?)</script>',
                         f.read_text(encoding="utf-8"), re.S).group(1)
        return json.loads(blob.replace("<\\/", "</"))["s"]["srcs"]
    except Exception:
        return {}


def pull_apple_books():
    """连 -wal/-shm 一起拷，否则会漏掉尚未落盘的最新标注。"""
    got = 0
    for sub in ("AEAnnotation", "BKLibrary"):
        src, dst = BOOKS_SRC / sub, BOOKS_DST / sub
        dst.mkdir(parents=True, exist_ok=True)
        try:
            listing = list(src.iterdir())
        except (PermissionError, OSError):
            # 容器受 TCC 保护，只有拿到授权的 App（终端）跑才读得到。
            # 从 launchd 之类的身份跑必然是这条路，沿用上次拷贝即可。
            say("· Apple Books: 无访问权限，沿用上次数据"
                "（需从已授权的终端运行）")
            return any(BOOKS_DST.rglob("*.sqlite"))
        for f in listing:
            if f.suffix in (".sqlite",) or f.name.endswith(("-wal", "-shm")):
                try:
                    shutil.copy2(f, dst / f.name)
                    got += 1
                except OSError as e:
                    say(f"  ! {f.name}: {e}")
    say(f"· Apple Books: 取到 {got} 个文件")
    return got > 0


def pull_kindle():
    src = KINDLE_VOL / "documents" / "My Clippings.txt"
    if not src.exists():
        say("· Kindle: 设备未连接，沿用上次数据")
        return CLIPPINGS.exists()
    CLIPPINGS.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, CLIPPINGS)
    say(f"· Kindle: 已更新 ({CLIPPINGS.stat().st_size // 1024} KB)")
    return True


def run(script, *args):
    r = subprocess.run([sys.executable, str(HERE / script), *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        say(f"  ! {script} 失败:\n{r.stderr.strip()}")
        return False
    say("  " + (r.stdout.strip().splitlines() or [""])[-1])
    return True


def main():
    before = counts()

    have_books = pull_apple_books()
    have_kindle = pull_kindle()

    say("解析…")
    if have_kindle:
        run("parse_clippings.py", str(CLIPPINGS))
    run("parse_koreader.py", "--pull")
    if have_books:
        run("parse_applebooks.py")

    say("重建…")
    if not run("build.py"):
        return 1

    after = counts()
    delta = {k: after.get(k, 0) - before.get(k, 0) for k in set(before) | set(after)}
    new = {k: v for k, v in delta.items() if v}

    if new:
        bits = "，".join(f"{k} +{v}" if v > 0 else f"{k} {v}" for k, v in new.items())
        print(f"有新增：{bits} · 现共 {sum(after.values())} 条")
        print("页面已重建。要同步到线上私有页，让 Claude 重新发布一次即可。")
    else:
        say(f"没有新增 · 共 {sum(after.values())} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
