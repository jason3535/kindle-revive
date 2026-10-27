#!/usr/bin/env python3
"""把摘录导出成 Kindle 能读的电子书。

产出 EPUB；再用 calibre 的 ebook-convert 转成 AZW3 就能直接 USB 拷进设备
（PW3 这类老机器不认 EPUB，认 AZW3）。

结构：
    卷一 按知识点   33 章，每章内按书分组 —— 这是网页版图谱的纸面形态
    卷二 按书       摘录 >= 10 条的书
    卷三 单词本     367 词 + 释义
"""
import html
import json
import re
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
TITLE = "读书高亮"


def load():
    h = (HERE / "index.html").read_text(encoding="utf-8")
    raw = re.search(r'<script id="data" type="application/json">(.*?)</script>', h, re.S).group(1)
    return json.loads(raw.replace("<\\/", "</"))


E = html.escape

CSS = """
body { font-family: serif; line-height: 1.7; margin: 0 1em; }
h1 { font-size: 1.5em; margin: 1.2em 0 .2em; page-break-before: always; }
h2 { font-size: 1.05em; margin: 1.6em 0 .4em; color: #444;
     border-bottom: 1px solid #bbb; padding-bottom: .2em; }
.lead { color: #555; font-size: .85em; margin: 0 0 1.2em; }
blockquote { margin: 0 0 1em; padding: 0; text-indent: 0; }
.meta { font-size: .75em; color: #777; margin: -.7em 0 1.2em; }
.w { font-weight: bold; }
.z { color: #444; }
dl { margin: 0; } dt { margin-top: .8em; font-weight: bold; }
dd { margin: 0 0 0 1em; color: #333; }
.note { color: #777; font-size: .85em; }
"""


def page(title, body):
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head>'
        f'<title>{E(title)}</title>'
        '<link rel="stylesheet" type="text/css" href="style.css"/>'
        f'</head><body>{body}</body></html>'
    )


def entries_html(rows, show_book=True):
    out = []
    for q in rows:
        bits = []
        if show_book:
            bits.append(E(q["book"]))
        if q.get("d"):
            bits.append(q["d"])
        if q.get("c"):
            bits.append(E(q["c"]))
        out.append(f'<blockquote>{E(q["x"])}</blockquote>'
                   f'<p class="meta">{" · ".join(bits)}</p>')
    return "".join(out)


def build():
    db = load()
    books, concepts, vocab = db["b"], db.get("c", []), db.get("v", [])
    clabel = {c["id"]: c["l"] for c in concepts}

    flat = []
    for b in books:
        for e in b["e"]:
            flat.append({**e, "book": b["t"], "author": b["a"]})

    files, spine, nav = {}, [], []

    # ---- 扉页 ----
    s = db["s"]
    files["title.xhtml"] = page(TITLE, f"""
      <h1 style="page-break-before:auto">{TITLE}</h1>
      <p class="lead">{s['after_dedupe']} 条摘录 · {s['books']} 本书 · {s['words']} 个生词<br/>
      {(s['first'] or '')[:7]} 至 {(s['last'] or '')[:7]}<br/>
      来自 Kindle 与 Apple Books · 导出于 {datetime.now():%Y-%m-%d}</p>
      <p class="note">卷一按知识点重排，同一个主题下能看到不同的书怎么讲同一件事；
      卷二按书；卷三是查过的生词。</p>""")
    spine.append("title.xhtml")
    nav.append(("扉页", "title.xhtml"))

    # ---- 卷一：按知识点 ----
    by_concept = defaultdict(list)
    for q in flat:
        for cid in q.get("k", []):
            by_concept[cid].append(q)

    order = sorted(by_concept, key=lambda c: -len(by_concept[c]))
    for n, cid in enumerate(order):
        rows = by_concept[cid]
        grouped = defaultdict(list)
        for q in rows:
            grouped[q["book"]].append(q)
        body = [f'<h1>{E(clabel.get(cid, cid))}</h1>',
                f'<p class="lead">{len(rows)} 条 · 横跨 {len(grouped)} 本书</p>']
        for bk, items in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
            body.append(f"<h2>{E(bk)}</h2>")
            body.append(entries_html(items, show_book=False))
        fn = f"c{n:02d}.xhtml"
        files[fn] = page(clabel.get(cid, cid), "".join(body))
        spine.append(fn)
        nav.append(("　" + clabel.get(cid, cid) + f"（{len(rows)}）", fn))

    # ---- 卷二：按书（只收够厚的，否则目录几百条没法翻）----
    thick = [b for b in books if len(b["e"]) >= 10]
    for n, b in enumerate(thick):
        rows = [{**e, "book": b["t"], "author": b["a"]} for e in b["e"]]
        body = [f'<h1>{E(b["t"])}</h1>',
                f'<p class="lead">{E(b["a"] or "佚名")} · {len(rows)} 条</p>',
                entries_html(rows, show_book=False)]
        fn = f"b{n:03d}.xhtml"
        files[fn] = page(b["t"], "".join(body))
        spine.append(fn)
        nav.append(("　" + b["t"][:28] + f"（{len(rows)}）", fn))

    # ---- 卷三：单词本 ----
    body = ['<h1>单词本</h1>', f'<p class="lead">{len(vocab)} 个词</p>', "<dl>"]
    for v in vocab:
        extra = f'（查过 {v["n"]} 次）' if v.get("n", 1) > 1 else ""
        body.append(f'<dt class="w">{E(v["w"])}</dt>'
                    f'<dd class="z">{E(v["z"])}{extra}<br/>'
                    f'<span class="note">{E(v["b"])} · {v.get("d","")}</span></dd>')
    body.append("</dl>")
    files["vocab.xhtml"] = page("单词本", "".join(body))
    spine.append("vocab.xhtml")
    nav.append(("单词本", "vocab.xhtml"))

    # ---- 目录分隔标题 ----
    marks = {"c00.xhtml": "卷一 · 按知识点", "b000.xhtml": "卷二 · 按书"}
    toc = []
    for label, fn in nav:
        if fn in marks:
            toc.append((marks[fn], fn))
        toc.append((label, fn))

    # ---- 打包 ----
    uid = "urn:uuid:kindle-highlights-" + datetime.now().strftime("%Y%m%d")
    manifest = "".join(
        f'<item id="i{i}" href="{fn}" media-type="application/xhtml+xml"/>'
        for i, fn in enumerate(spine))
    manifest += '<item id="css" href="style.css" media-type="text/css"/>'
    manifest += '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
    spine_xml = "".join(f'<itemref idref="i{i}"/>' for i in range(len(spine)))

    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bid" version="2.0">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"
          xmlns:opf="http://www.idpf.org/2007/opf">
  <dc:title>{E(TITLE)}</dc:title>
  <dc:creator opf:role="aut">Reader</dc:creator>
  <dc:language>zh-CN</dc:language>
  <dc:identifier id="bid">{uid}</dc:identifier>
  <dc:date>{datetime.now():%Y-%m-%d}</dc:date>
</metadata>
<manifest>{manifest}</manifest>
<spine toc="ncx">{spine_xml}</spine>
</package>"""

    points = "".join(
        f'<navPoint id="n{i}" playOrder="{i + 1}"><navLabel><text>{E(t)}</text></navLabel>'
        f'<content src="{fn}"/></navPoint>'
        for i, (t, fn) in enumerate(toc))
    ncx = f"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
<head><meta name="dtb:uid" content="{uid}"/></head>
<docTitle><text>{E(TITLE)}</text></docTitle>
<navMap>{points}</navMap></ncx>"""

    out = HERE / "读书高亮.epub"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        # mimetype 必须是压缩包里第一个且不压缩，否则部分阅读器不认
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip",
                   compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0"?>\n<container version="1.0" '
                   'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OEBPS/content.opf" '
                   'media-type="application/oebps-package+xml"/></rootfiles></container>')
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/toc.ncx", ncx)
        z.writestr("OEBPS/style.css", CSS)
        for fn, data in files.items():
            z.writestr("OEBPS/" + fn, data)

    print(f"写入 {out} ({out.stat().st_size / 1024:.0f} KB)")
    print(f"卷一 {len(order)} 章 · 卷二 {len(thick)} 本 · 卷三 {len(vocab)} 词 · 目录 {len(toc)} 项")
    return out


if __name__ == "__main__":
    build()
