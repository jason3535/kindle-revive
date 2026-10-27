#!/usr/bin/env python3
"""把 Kindle 的 My Clippings.txt 解析成结构化 JSON。

Kindle 的剪贴文件是按 ========== 分隔的记录块，每块四行：
    书名 (作者)
    - 您在位置 #1234-1235的标注 | 添加于 2018年7月25日星期三 下午3:43:42
    (空行)
    正文
中英文固件的措辞不同，两种都认。
"""
import json
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

SEP = "=========="

OPENERS = "（("
CLOSERS = "）)"


def unmojibake(s):
    """修 Kindle 偶尔写坏的书名。

    典型症状是 UTF-8 的字节被当成 Latin-1 解过一次，
    《翦商 → ã\x80\x8aç¿¦å\x95\x86。把这一步反过来即可还原。
    还原后必须确认真的出现了 CJK，否则原样返回——
    别把本来就正常的西文标题给改坏了。"""
    if not any(" " <= c <= "ÿ" or c in "ã¥æç¿è" for c in s):
        return s
    # macOS 把重音字母做了 NFD 分解（ã → a + 组合波浪号），
    # 分解后字符跑出 Latin-1 范围，反编码必然失败，先合回 NFC。
    orig = s
    s = unicodedata.normalize("NFC", s)
    try:
        fixed = s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return orig
    has_cjk = any("一" <= c <= "鿿" for c in fixed)
    return fixed if has_cjk else s


def split_title_author(header):
    """「书名 (作者)」拆分。作者名自己也可能带括号，例如
    「管理的实践(珍藏版) (德鲁克管理经典) (彼得·德鲁克(Peter F. Drucker))」，
    所以从末尾按括号配平往回找，取最后一组顶层括号当作者。"""
    s = header.rstrip()
    if not s or s[-1] not in CLOSERS:
        return s, ""

    depth = 0
    for i in range(len(s) - 1, -1, -1):
        if s[i] in CLOSERS:
            depth += 1
        elif s[i] in OPENERS:
            depth -= 1
            if depth == 0:
                title, author = s[:i].strip(), s[i + 1:-1].strip()
                # 括号里是卷次/版本而不是人名时，宁可原样保留
                return (title, author) if title else (s, "")
    return s, ""

TYPE_MAP = {
    "标注": "highlight", "笔记": "note", "书签": "bookmark",
    "Highlight": "highlight", "Note": "note", "Bookmark": "bookmark",
}

LOC = re.compile(r"#(?P<start>\d+)(?:-(?P<end>\d+))?")
PAGE = re.compile(r"第\s*(?P<page>\d+)\s*页|page\s+(?P<page_en>\d+)", re.I)

# 2018年7月25日星期三 下午3:43:42
CN_DATE = re.compile(
    r"(?P<y>\d{4})年(?P<m>\d{1,2})月(?P<d>\d{1,2})日"
    r"(?:星期.)?\s*(?P<ampm>上午|下午)?\s*(?P<H>\d{1,2}):(?P<M>\d{2}):(?P<S>\d{2})"
)


def parse_date(meta):
    m = CN_DATE.search(meta)
    if m:
        hour = int(m["H"])
        if m["ampm"] == "下午" and hour != 12:
            hour += 12
        elif m["ampm"] == "上午" and hour == 12:
            hour = 0
        try:
            return datetime(int(m["y"]), int(m["m"]), int(m["d"]),
                            hour, int(m["M"]), int(m["S"]))
        except ValueError:
            return None
    # 英文固件: "Added on Wednesday, July 25, 2018 3:43:42 PM"
    m = re.search(r"(\w+ \d{1,2}, \d{4} \d{1,2}:\d{2}:\d{2} [AP]M)", meta)
    if m:
        try:
            return datetime.strptime(m.group(1), "%B %d, %Y %I:%M:%S %p")
        except ValueError:
            return None
    return None


def entry_type(meta):
    for zh, en in TYPE_MAP.items():
        if zh in meta:
            return en
    return "highlight"


def parse(path):
    raw = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    blocks = raw.replace("\r\n", "\n").split(SEP)
    out, skipped = [], 0

    for block in blocks:
        lines = [ln.strip() for ln in block.split("\n")]
        lines = [ln for ln in lines if ln]
        if len(lines) < 2:
            skipped += 1
            continue

        header, meta = lines[0], lines[1]
        body = "\n".join(lines[2:]).strip()

        title, author = split_title_author(header)
        # 有的行标题是乱码、作者却是正常中文，整行一起反编码会失败，
        # 所以拆开各修各的
        title, author = unmojibake(title), unmojibake(author)

        kind = entry_type(meta)
        if kind == "bookmark" or not body:
            skipped += 1
            continue

        loc = LOC.search(meta)
        pg = PAGE.search(meta)
        dt = parse_date(meta)

        out.append({
            "title": title,
            "author": author,
            "type": kind,
            "text": body,
            "loc": int(loc["start"]) if loc else None,
            "page": int(pg["page"] or pg["page_en"]) if pg else None,
            "date": dt.isoformat() if dt else None,
            "chars": len(body),
        })

    return out, skipped


def dedupe(entries):
    """同一本书里位置相近、正文互为前缀的条目，保留最长的那条。

    Kindle 上反复调整高亮范围会留下多条重叠记录。"""
    by_book = defaultdict(list)
    for e in entries:
        by_book[e["title"]].append(e)

    kept = []
    for items in by_book.values():
        items.sort(key=lambda x: (x["loc"] or 0, -x["chars"]))
        survivors = []
        for e in items:
            absorbed = False
            for s in survivors:
                if s["type"] != e["type"]:
                    continue
                if e["text"] in s["text"] or s["text"] in e["text"]:
                    if e["chars"] > s["chars"]:
                        s.update(e)
                    absorbed = True
                    break
            if not absorbed:
                survivors.append(e)
        kept.extend(survivors)
    return kept


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else (
        str(Path(__file__).parent / "_kindle" / "My Clippings.txt")
    )
    entries, skipped = parse(src)
    deduped = dedupe(entries)

    books = defaultdict(list)
    for e in deduped:
        books[(e["title"], e["author"])].append(e)

    dated = [e["date"] for e in deduped if e["date"]]
    payload = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "source": str(src),
        "stats": {
            "raw_blocks": len(entries) + skipped,
            "parsed": len(entries),
            "after_dedupe": len(deduped),
            "skipped": skipped,
            "books": len(books),
            "notes": sum(1 for e in deduped if e["type"] == "note"),
            "highlights": sum(1 for e in deduped if e["type"] == "highlight"),
            "first": min(dated) if dated else None,
            "last": max(dated) if dated else None,
        },
        "books": [
            {
                "title": t,
                "author": a,
                "count": len(v),
                "first": min((e["date"] for e in v if e["date"]), default=None),
                "last": max((e["date"] for e in v if e["date"]), default=None),
                "entries": sorted(v, key=lambda x: (x["loc"] or 0)),
            }
            for (t, a), v in sorted(books.items(), key=lambda kv: -len(kv[1]))
        ],
    }

    out = Path(__file__).parent / "highlights.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    s = payload["stats"]
    print(f"原始块 {s['raw_blocks']} → 解析 {s['parsed']} → 去重后 {s['after_dedupe']}")
    print(f"跳过(书签/空) {s['skipped']}  书 {s['books']} 本  笔记 {s['notes']} 条")
    print(f"时间跨度 {s['first']} → {s['last']}")
    print(f"写入 {out}")


if __name__ == "__main__":
    main()
