#!/usr/bin/env python3
"""Apple Books 进度 → 云端同步服务器(cloud/worker.js) → Kindle 上的 KOReader「进度同步」插件。

和 sync_progress.py 的区别:不再需要 Mac 能直连 Kindle。Mac 只跟服务器说话,
Kindle 自己在开书/关书/休眠时跟服务器说话(KOReader kosync 插件,auto sync)。
Kindle 在公司、在路上、在任何能上网的 Wi-Fi 下都一样。

服务器一本书只存一条「最新进度」。谁的阅读时刻更晚谁说了算:
  - 这里推 Apple Books 位置时带上 Apple Books 的最后阅读时刻做 timestamp,
    并且只在它比服务器现有记录更新时才覆盖(否则就是 Kindle 读得更晚,不动)。
  - Kindle 端 kosync 开书时拉:服务器记录比自己新 → 跳过去;比自己旧 → 不动(sync_backward=disable)。

文档 id = md5(文件名),对应 kosync 的「按文件名匹配」,所以 ~/Downloads/kindle-books 里的
文件名必须和 Kindle 上的一致(本来就是从这里推过去的)。

用法:
  cloud_sync.py status     看两边位置
  cloud_sync.py push       把 Apple Books 更新的位置推到服务器
  cloud_sync.py push --quiet   同上,只在推了东西时打一行(给 autosync.command 循环用)
凭据在 ~/.config/kindle-sync/env(KSYNC_URL / KSYNC_USER / KSYNC_KEY)。
"""
import glob
import hashlib
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_progress import BOOKS_DIR, Epub, apple_positions, cfi_to_xpointer  # noqa: E402

DEVICE, DEVICE_ID = "Apple Books", "applebooks-mac"
LAST_PUSH = os.path.expanduser("~/.config/kindle-sync/last_push.json")   # {doc: 上次推过的 xpointer}


def load_env():
    env = {}
    p = os.path.expanduser("~/.config/kindle-sync/env")
    if not os.path.exists(p):
        sys.exit("缺 ~/.config/kindle-sync/env(KSYNC_URL/KSYNC_USER/KSYNC_KEY)")
    for line in open(p, encoding="utf-8"):
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            env[k] = v
    return env


ENV = load_env()


def api(method, path, body=None):
    req = urllib.request.Request(ENV["KSYNC_URL"].rstrip("/") + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"x-auth-user": ENV["KSYNC_USER"], "x-auth-key": ENV["KSYNC_KEY"],
                                          "content-type": "application/json",
                                          # Cloudflare 对 Python-urllib 默认 UA 直接 403,必须换掉
                                          "user-agent": "kindle-sync/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode() or "{}")


def doc_id(path):
    return hashlib.md5(os.path.basename(path).encode("utf-8")).hexdigest()


def fmt(ts):
    return time.strftime("%m-%d %H:%M", time.localtime(ts)) if ts else "—"


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "status"
    quiet = "--quiet" in sys.argv            # 定时循环用:只在真的推了东西时输出
    apple = apple_positions()
    try:
        last = json.load(open(LAST_PUSH, encoding="utf-8"))
    except (OSError, ValueError):
        last = {}
    cloud = {r["document"]: r for r in api("GET", "/progress")}
    for path in sorted(glob.glob(f"{BOOKS_DIR}/*.epub")):
        ep = Epub(path)
        doc = doc_id(path)
        rec = cloud.get(doc)
        line = f"* {ep.title}"
        if rec:
            line += f"\n  云端: {rec['percentage']:.1%}  {fmt(rec.get('timestamp'))}  来自 {rec['device']}  {rec['progress']}"
        else:
            line += "\n  云端: 无记录"
        if ep.title not in apple:
            if not quiet:
                print(line + "\n  Apple Books: 无阅读位置")
            continue
        prog, cfi, mod = apple[ep.title]
        xp, label = cfi_to_xpointer(ep, cfi)
        line += f"\n  Apple: {prog:.1%}  {fmt(mod)}  {xp}  «{label}»"
        if not quiet:
            print(line)
        if mode != "push":
            continue
        if last.get(doc) == xp:
            # Apple Books 只要打开过书就会刷新时间戳,位置没动不算"读得更晚",否则会把 Kindle 拉回去
            if not quiet:
                print("  → Apple Books 位置没变,跳过")
        elif rec and rec.get("timestamp", 0) >= int(mod) and rec["device"] != DEVICE:
            if not quiet:
                print("  → Kindle 读得更晚,不覆盖")
        elif rec and rec["device"] == DEVICE and rec["progress"] == xp:
            if not quiet:
                print("  → 已是最新,跳过")
        else:
            out = api("PUT", "/syncs/progress", {
                "document": doc, "progress": xp, "percentage": round(prog, 4),
                "device": DEVICE, "device_id": DEVICE_ID, "timestamp": int(mod),
                "metadata": {"filename": os.path.basename(path), "title": ep.title},
            })
            if quiet:
                print(f"{time.strftime('%m-%d %H:%M')} 推送 {ep.title} → {prog:.1%} ({fmt(mod)})")
            else:
                print(f"  ✓ 已推到云端(Kindle 下次开书自动跳过去) {out}")
        last[doc] = xp
        os.makedirs(os.path.dirname(LAST_PUSH), exist_ok=True)
        json.dump(last, open(LAST_PUSH, "w", encoding="utf-8"))


if __name__ == "__main__":
    main()
