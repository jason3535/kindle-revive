#!/usr/bin/env python3
"""把 KOReader 的划线(每本书旁边 .sdr/metadata.*.lua 里的 annotations)解析成和
highlights.json 同构的 koreader.json。KOReader 不写 My Clippings.txt,这一路不接,
在 Kindle 上用 KOReader 读的书划线全漏。

    python3 parse_koreader.py --pull     # 先经 SSH 从 Kindle 拉最新 .sdr 再解析
    python3 parse_koreader.py            # 只解析 _koreader/sdr 里上次拉下来的

只拉 /mnt/us/documents 下的(真正的书);koreader/settings 里播客文章的 .sdr 不算。
KOReader 的 sidecar 是 Lua 表(dump.lua 用 %q 转义),没有现成解析器,这里手写一个。
"""
import json
import os
import re
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
SDR = HERE / "_koreader" / "sdr"
OUT = HERE / "koreader.json"

KEY = Path.home() / ".config/mcp-show-on-kindle/id_ed25519"
KNOWN = Path.home() / ".config/mcp-show-on-kindle/known_hosts"
HOST_CACHE = Path.home() / ".cache/mcp-show-on-kindle/host"


def kindle_host():
    env = os.environ.get("KINDLE_HOST")
    if env:
        return env
    if HOST_CACHE.exists():
        return HOST_CACHE.read_text().strip()
    return "kindle.local"  # 或 export KINDLE_HOST=<Kindle IP>


def pull():
    host = kindle_host()
    try:
        socket.create_connection((host, 2222), timeout=3).close()
    except OSError:
        print(f"· KOReader: Kindle({host}:2222)不在线,沿用上次数据")
        return SDR.exists()
    SDR.mkdir(parents=True, exist_ok=True)
    ssh = ["ssh", "-i", str(KEY), "-o", "IdentitiesOnly=yes", "-p", "2222", "-o", "ConnectTimeout=10",
           "-o", f"UserKnownHostsFile={KNOWN}", "-o", "HostKeyAlias=kindle", f"root@{host}",
           'cd /mnt/us/documents && find . -path "*.sdr/metadata.*.lua" -print0 | xargs -0 tar -cf -']
    r = subprocess.run(ssh, capture_output=True)
    if r.returncode != 0 or not r.stdout:
        print("· KOReader: 拉取失败", r.stderr.decode(errors="replace")[-200:])
        return SDR.exists()
    subprocess.run(["tar", "-xf", "-", "-C", str(SDR)], input=r.stdout, check=True)
    n = sum(1 for _ in SDR.rglob("metadata.*.lua"))
    print(f"· KOReader: 拉到 {n} 本书的 sidecar")
    return True


# ── Lua 表解析(只覆盖 KOReader dump.lua 产出的子集)───────────────────────
class Lua:
    def __init__(self, s):
        self.s, self.i = s, 0

    def ws(self):
        while self.i < len(self.s):
            c = self.s[self.i]
            if c in " \t\r\n":
                self.i += 1
            elif self.s.startswith("--", self.i):
                j = self.s.find("\n", self.i)
                self.i = len(self.s) if j < 0 else j + 1
            else:
                break

    def expect(self, tok):
        self.ws()
        if not self.s.startswith(tok, self.i):
            raise ValueError(f"expected {tok!r} at {self.i}: {self.s[self.i:self.i+30]!r}")
        self.i += len(tok)

    def value(self):
        self.ws()
        c = self.s[self.i]
        if c == "{":
            return self.table()
        if c == '"':
            return self.string()
        if self.s.startswith("true", self.i):
            self.i += 4; return True
        if self.s.startswith("false", self.i):
            self.i += 5; return False
        if self.s.startswith("nil", self.i):
            self.i += 3; return None
        m = re.compile(r"-?(?:\d+\.?\d*(?:[eE][-+]?\d+)?|\.\d+|inf|nan)").match(self.s, self.i)
        if not m:
            raise ValueError(f"bad value at {self.i}: {self.s[self.i:self.i+30]!r}")
        self.i = m.end()
        t = m.group(0)
        return float(t) if any(ch in t for ch in ".eEin") else int(t)

    def string(self):
        assert self.s[self.i] == '"'
        self.i += 1
        out = []
        while True:
            c = self.s[self.i]
            if c == '"':
                self.i += 1
                return "".join(out)
            if c == "\\":
                n = self.s[self.i + 1]
                if n.isdigit():                       # \ddd
                    m = re.compile(r"\d{1,3}").match(self.s, self.i + 1)
                    out.append(chr(int(m.group(0)))); self.i = m.end()
                    continue
                out.append({"n": "\n", "r": "\r", "t": "\t", "\n": "\n", "\\": "\\", '"': '"', "'": "'",
                            "a": "\a", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}.get(n, n))
                self.i += 2
                continue
            out.append(c)
            self.i += 1

    def table(self):
        self.expect("{")
        d, arr, nxt = {}, True, 1
        while True:
            self.ws()
            if self.s[self.i] == "}":
                self.i += 1
                break
            if self.s[self.i] == "[":
                self.i += 1
                k = self.value()
                self.expect("]")
                self.expect("=")
            else:
                m = re.compile(r"[A-Za-z_]\w*").match(self.s, self.i)
                if m and self.s[m.end():m.end() + 2].strip().startswith("="):
                    k = m.group(0); self.i = m.end(); self.expect("=")
                else:
                    k = nxt
            v = self.value()
            if k != nxt:
                arr = False
            nxt = k + 1 if isinstance(k, int) and k == nxt else nxt
            d[k] = v
            self.ws()
            if self.s[self.i] in ",;":
                self.i += 1
        if d and arr and all(isinstance(k, int) for k in d):
            return [d[k] for k in sorted(d)]
        return d


def load_lua(path):
    s = path.read_text(encoding="utf-8", errors="replace")
    p = Lua(s)
    p.ws()
    p.expect("return")
    return p.value()


def norm_date(s):
    # "2026-10-25 21:08:40" → ISO,与 highlights.json 一致
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").isoformat()
    except (TypeError, ValueError):
        return ""


def book_of(path, meta):
    props = meta.get("doc_props") or {}
    title = (props.get("title") or "").strip()
    if not title:
        title = path.parent.name[:-4] if path.parent.name.endswith(".sdr") else path.parent.name
    author = (props.get("authors") or "").strip().replace("\n", "; ")
    return title, author


def dedupe(entries):
    """同书内正文互为前缀取最长(划线时反复拖拽留下的叠层),和 parse_clippings 同规则。"""
    entries = sorted(entries, key=lambda e: -len(e["text"]))
    kept = []
    for e in entries:
        if e["type"] == "highlight" and any(
                k["type"] == "highlight" and k["text"].startswith(e["text"]) for k in kept):
            continue
        kept.append(e)
    return sorted(kept, key=lambda e: (e["date"], e.get("loc") or 0))


def main():
    if "--pull" in sys.argv and not pull():
        return 1
    books = {}
    for path in sorted(SDR.rglob("metadata.*.lua")):
        try:
            meta = load_lua(path)
        except Exception as e:               # 一个坏文件不该拖垮整批
            print(f"  ! {path.parent.name}: {e}")
            continue
        title, author = book_of(path, meta)
        anns = meta.get("annotations") or []
        if isinstance(anns, dict):
            anns = [anns[k] for k in sorted(anns)]
        entries = []
        for a in anns:
            text = (a.get("text") or "").strip()
            if not text:                      # 纯书签(翻页位置)没有正文,不是摘录
                continue
            base = {"title": title, "author": author, "loc": a.get("pageno"), "page": a.get("pageno"),
                    "date": norm_date(a.get("datetime")), "chapter": (a.get("chapter") or "").strip()}
            entries.append({**base, "type": "highlight", "text": text, "chars": len(text)})
            note = (a.get("note") or "").strip()
            if note:
                entries.append({**base, "type": "note", "text": note, "chars": len(note)})
        if entries:
            key = (title, author)
            books.setdefault(key, []).extend(entries)

    out = []
    for (title, author), entries in books.items():
        entries = dedupe(entries)
        dates = [e["date"] for e in entries if e["date"]]
        out.append({"title": title, "author": author, "count": len(entries),
                    "first": min(dates) if dates else "", "last": max(dates) if dates else "",
                    "entries": entries})
    out.sort(key=lambda b: -b["count"])
    total = sum(b["count"] for b in out)
    OUT.write_text(json.dumps({
        "generated": datetime.now().isoformat(timespec="seconds"), "source": "koreader",
        "stats": {"books": len(out), "entries": total}, "books": out,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"KOReader: {len(out)} 本 / {total} 条 → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
