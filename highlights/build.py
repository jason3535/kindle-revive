#!/usr/bin/env python3
"""把各来源的 JSON 合并塞进模板，产出一个可离线打开的单文件页面。

来源：
    highlights.json   Kindle 设备（parse_clippings.py）
    koreader.json     Kindle 上 KOReader 的划线（parse_koreader.py）
    applebooks.json   Apple Books（parse_applebooks.py，可选）
"""
import json
import re
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent

SOURCES = [
    ("highlights.json", "kindle"),
    ("koreader.json", "kindle"),     # 同一台 Kindle,KOReader 划的线(parse_koreader.py)
    ("applebooks.json", "books"),
]

# 纯英文、一到两个词、没有句末标点 —— 这是查词留下的，不是摘录
WORDLIKE = re.compile(r"[A-Za-z][A-Za-z\-']{1,24}(?:\s+[A-Za-z\-']{1,24})?\Z")

GLOSSES = json.loads((HERE / "vocab_zh.json").read_text(encoding="utf-8")) \
    if (HERE / "vocab_zh.json").exists() else {}

_cfg = json.loads((HERE / "concepts.json").read_text(encoding="utf-8")) \
    if (HERE / "concepts.json").exists() else {"concepts": [], "domains": {}}
CONCEPTS = _cfg["concepts"]
DOMAINS = _cfg.get("domains", {})
_MATCH = [(c["id"], re.compile("|".join(c["patterns"]))) for c in CONCEPTS]


def tag(text):
    """一条摘录可以同时属于多个知识点，共现即构成图谱里的一条边。"""
    return [cid for cid, pat in _MATCH if pat.search(text)]


def load(name, src):
    p = HERE / name
    if not p.exists():
        return None, src
    return json.loads(p.read_text(encoding="utf-8")), src


def slim_books(payload, src, vocab):
    """拆成两摞：正经摘录留在书里，查过的单词进单词本。"""
    out = []
    for b in payload["books"]:
        kept = []
        for e in b["entries"]:
            text = e["text"].strip()
            if WORDLIKE.match(text):
                key = text.lower()
                vocab.setdefault(key, {
                    "w": text, "z": GLOSSES.get(key, ""),
                    "b": b["title"], "d": (e.get("date") or "")[:10], "n": 0,
                })
                vocab[key]["n"] += 1
                # 同一个词查过多次，记最近一次的日期
                d = (e.get("date") or "")[:10]
                if d > vocab[key]["d"]:
                    vocab[key]["d"] = d
                continue
            row = {
                "x": e["text"],
                "l": e.get("loc"),
                "d": (e.get("date") or "")[:10],
                "n": 1 if e.get("type") == "note" else 0,
                "c": e.get("chapter") or "",
            }
            k = tag(text)
            if k:
                row["k"] = k
            kept.append(row)
        if kept:
            out.append({"t": b["title"], "a": b["author"], "s": src, "e": kept})
    return out


def main():
    books, srcs, vocab = [], {}, {}
    for name, src in SOURCES:
        payload, src = load(name, src)
        if not payload:
            continue
        got = slim_books(payload, src, vocab)
        books += got
        srcs[src] = srcs.get(src, 0) + sum(len(b["e"]) for b in got)   # kindle 有两份来源

    if not books:
        raise SystemExit("没有任何数据源，先跑 parse_clippings.py")

    # 同名同作者的书跨来源合并，避免书架上出现两条
    merged = {}
    for b in books:
        key = (b["t"].strip(), b["a"].strip())
        if key in merged:
            merged[key]["e"] += b["e"]
            if b["s"] not in merged[key]["s"].split(","):
                merged[key]["s"] += "," + b["s"]
        else:
            merged[key] = b
    books = sorted(merged.values(), key=lambda b: -len(b["e"]))

    entries = [e for b in books for e in b["e"]]
    dates = sorted(e["d"] for e in entries if e["d"])
    words = sorted(vocab.values(), key=lambda v: v["w"].lower())
    stats = {
        "after_dedupe": len(entries),
        "books": len(books),
        "words": len(words),
        "first": dates[0] if dates else None,
        "last": dates[-1] if dates else None,
        "srcs": srcs,
    }

    missing = [w["w"] for w in words if not w["z"]]
    if missing:
        print(f"! {len(missing)} 个词还没有释义，补进 vocab_zh.json: "
              + ", ".join(missing[:8]) + ("…" if len(missing) > 8 else ""))

    tagged = sum(1 for e in entries if e.get("k"))
    stats["tagged"] = tagged
    print(f"知识点标注覆盖 {tagged}/{len(entries)} = {tagged / max(1, len(entries)):.0%}")

    blob = json.dumps({
        "s": stats, "b": books, "v": words,
        "c": [{"id": c["id"], "l": c["label"], "d": c["domain"]} for c in CONCEPTS],
        "dm": DOMAINS,
    }, ensure_ascii=False, separators=(",", ":"))
    blob = blob.replace("</", "<\\/")  # 别让数据提前闭合 script 标签

    html = (HERE / "template.html").read_text(encoding="utf-8") \
        .replace("__DATA__", blob) \
        .replace("__BUILT__", datetime.now().strftime("%Y-%m-%d %H:%M"))

    out = HERE / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"写入 {out} ({out.stat().st_size / 1024:.0f} KB)")
    print(f"{stats['after_dedupe']} 条 / {stats['books']} 本 / "
          f"单词本 {stats['words']} 词 · 来源 " +
          " + ".join(f"{k} {v}" for k, v in srcs.items()))


if __name__ == "__main__":
    main()
