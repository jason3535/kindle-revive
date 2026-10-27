#!/usr/bin/env python3
"""解析 Apple Books 的标注，产出跟 Kindle 侧同构的 applebooks.json。

数据在两个 Core Data 库里：
    AEAnnotation/AEAnnotation*.sqlite   标注正文、笔记、时间、章节
    BKLibrary/BKLibrary*.sqlite         书名、作者
两边用 asset id 关联（ZANNOTATIONASSETID ←→ ZASSETID）。

用法：先把这两个目录从
    ~/Library/Containers/com.apple.iBooksX/Data/Documents/
拷到 _applebooks/ 下（该容器有沙盒保护，脚本自己读不了）。
"""
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "_applebooks"

# Core Data 的时间基准是 2001-01-01 UTC
EPOCH = datetime(2001, 1, 1)


def find_db(subdir, prefix):
    d = SRC / subdir
    if not d.is_dir():
        return None
    cands = sorted(d.glob(f"{prefix}*.sqlite"), key=lambda p: p.stat().st_size, reverse=True)
    return cands[0] if cands else None


def cd_time(v):
    if v is None:
        return None
    try:
        return (EPOCH + timedelta(seconds=float(v))).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError):
        return None


def read_library(path):
    """asset id → (书名, 作者)"""
    if not path:
        return {}
    # 必须能读写地打开副本，SQLite 才会回放 -wal 里尚未落盘的记录；
    # immutable/只读模式会直接忽略 WAL，漏掉最近的标注。
    con = sqlite3.connect(str(path))
    try:
        rows = con.execute(
            "SELECT ZASSETID, ZASSETGUID, ZEPUBID, ZTITLE, ZAUTHOR FROM ZBKLIBRARYASSET"
        ).fetchall()
    except sqlite3.Error as e:
        print(f"读书目库失败: {e}", file=sys.stderr)
        return {}
    finally:
        con.close()

    # 多数标注对得上 ZASSETID，也有对到 GUID / EPUBID 上的，三个都当键收进来
    table = {}
    for asset, guid, epub, title, author in rows:
        info = ((title or "").strip(), (author or "").strip())
        if not info[0]:
            continue
        for key in (asset, guid, epub):
            if key:
                table.setdefault(key, info)
    return table


def read_annotations(path):
    if not path:
        return []
    # 必须能读写地打开副本，SQLite 才会回放 -wal 里尚未落盘的记录；
    # immutable/只读模式会直接忽略 WAL，漏掉最近的标注。
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("""
            SELECT ZANNOTATIONASSETID   AS asset,
                   ZANNOTATIONSELECTEDTEXT AS text,
                   ZANNOTATIONNOTE     AS note,
                   ZFUTUREPROOFING5    AS chapter,
                   ZANNOTATIONCREATIONDATE AS created,
                   ZANNOTATIONLOCATION AS loc
            FROM ZAEANNOTATION
            WHERE ZANNOTATIONDELETED = 0
              AND (ZANNOTATIONSELECTEDTEXT IS NOT NULL
                   OR ZANNOTATIONNOTE IS NOT NULL)
        """).fetchall()
    except sqlite3.Error as e:
        print(f"读标注库失败: {e}", file=sys.stderr)
        return []
    finally:
        con.close()
    return rows


def main():
    ann_db = find_db("AEAnnotation", "AEAnnotation")
    lib_db = find_db("BKLibrary", "BKLibrary")

    if not ann_db:
        print(f"没找到标注库。请先把 AEAnnotation / BKLibrary 两个目录拷到:\n  {SRC}")
        return 1

    library = read_library(lib_db)

    # 从资料库删掉的书在书目表里没有记录，可以在这个文件里手工补名字：
    #   {"68010594": ["翦商", "李硕"]}   键是 asset id 的前若干位
    ov_path = HERE / "title_overrides.json"
    overrides = json.loads(ov_path.read_text(encoding="utf-8")) if ov_path.exists() else {}
    rows = read_annotations(ann_db)
    print(f"标注库 {ann_db.name}: {len(rows)} 条  ·  书目库: {len(library)} 本")

    books = defaultdict(list)
    for r in rows:
        # 书从资料库里删掉后书目表就没记录了，此时按 asset 各自分桶，
        # 否则几本不同的书会被并成同一本
        asset = r["asset"] or ""
        hit = next((v for k, v in overrides.items() if asset.startswith(k)), None)
        title, author = (
            (hit[0], hit[1] if len(hit) > 1 else "") if hit
            else library.get(asset, (f"(未匹配 {asset[:8]})", ""))
        )
        text = (r["text"] or "").strip()
        note = (r["note"] or "").strip()
        # 只写了笔记没选中文字的，就把笔记当正文
        body, is_note = (text, False) if text else (note, True)
        if not body:
            continue
        books[(title, author)].append({
            "text": body,
            "note": note if text and note else "",
            "type": "note" if is_note else "highlight",
            "chapter": (r["chapter"] or "").strip(),
            "date": cd_time(r["created"]),
            "loc": None,
            "chars": len(body),
            "source": "books",
        })

    entries = [e for v in books.values() for e in v]
    dated = [e["date"] for e in entries if e["date"]]
    payload = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "source": str(ann_db),
        "stats": {
            "after_dedupe": len(entries),
            "books": len(books),
            "notes": sum(1 for e in entries if e["type"] == "note"),
            "first": min(dated) if dated else None,
            "last": max(dated) if dated else None,
        },
        "books": [
            {"title": t, "author": a, "count": len(v),
             "entries": sorted(v, key=lambda x: x["date"] or "")}
            for (t, a), v in sorted(books.items(), key=lambda kv: -len(kv[1]))
        ],
    }

    out = HERE / "applebooks.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    s = payload["stats"]
    print(f"{s['after_dedupe']} 条 / {s['books']} 本 / {(s['first'] or '?')[:10]} → {(s['last'] or '?')[:10]}")
    print(f"写入 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
