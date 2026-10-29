#!/usr/bin/env python3
"""云端书架:把书传到自建同步服务器,Kindle / BOOX 上的 hlsync 插件联网时自己拉下来。

    shelf.py push 书1.epub [书2.pdf ...]   上传(同名覆盖)
    shelf.py list                          看云端有哪些书
    shelf.py rm 文件名                      从云端删掉(设备上已下载的不动)

文件名就是书在设备上的文件名,也是进度同步的匹配键(md5(文件名)),所以别改名。
凭据在 ~/.config/kindle-sync/env(KSYNC_URL / KSYNC_USER / KSYNC_KEY)。
服务器把书切成 20 MB 一块存在 KV 里,免费额度 1 GB 总量、每天 1000 次写入。
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ENV = {}
for line in open(os.path.expanduser("~/.config/kindle-sync/env"), encoding="utf-8"):
    if "=" in line and not line.startswith("#"):
        k, v = line.strip().split("=", 1)
        ENV[k] = v
BASE = ENV["KSYNC_URL"].rstrip("/")
MAX = 90 * 1024 * 1024   # Workers 免费版单次请求体上限 100 MB,留余量


def call(method, path, data=None):
    req = urllib.request.Request(BASE + path, method=method, data=data, headers={
        "x-auth-user": ENV["KSYNC_USER"], "x-auth-key": ENV["KSYNC_KEY"],
        "user-agent": "kindle-sync/1.0",   # Cloudflare 会 403 掉 Python-urllib 默认 UA
        "content-type": "application/octet-stream"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode() or "{}")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("push", "list", "rm"):
        sys.exit(__doc__)
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "list":
        books = call("GET", "/books")
        for b in sorted(books, key=lambda b: -b["uploaded"]):
            print(f"{time.strftime('%m-%d %H:%M', time.localtime(b['uploaded']))}  {b['size'] / 1048576:6.1f} MB  {b['name']}")
        print(f"共 {len(books)} 本,{sum(b['size'] for b in books) / 1048576:.0f} MB")
    elif cmd == "push":
        for f in args:
            if not os.path.isfile(f):
                print(f"跳过(不存在): {f}")
                continue
            size = os.path.getsize(f)
            if size > MAX:
                print(f"跳过(超过 90 MB,服务器收不下): {f}")
                continue
            name = os.path.basename(f)
            with open(f, "rb") as fh:
                r = call("PUT", "/books/" + urllib.parse.quote(name), fh.read())
            print(f"✓ {name}  {r['size'] / 1048576:.1f} MB  → Kindle / BOOX 下次联网自动下载")
    elif cmd == "rm":
        for name in args:
            r = call("DELETE", "/books/" + urllib.parse.quote(os.path.basename(name)))
            print(("✓ 已从云端删除 " if r.get("deleted") else "云端没有 ") + r["name"])


if __name__ == "__main__":
    main()
