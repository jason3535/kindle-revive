#!/usr/bin/env python3
"""Apple Books -> KOReader(Kindle) 阅读进度同步。

Apple Books 的最后阅读位置是 EPUB CFI(AEAnnotation 库里 ZANNOTATIONTYPE=3 的记录),
KOReader(crengine)用 XPointer。两者描述同一棵 DOM,借助本地同一份 EPUB 换算。
跳转走 KOReader HTTP inspector(经 SSH 访问回环口):先 switchDocument 打开书,
再调 rolling:onGotoXPointer——不改 .sdr 进度文件,避免被正在运行的 KOReader 覆盖。

用法:
  sync_progress.py plan          只显示换算结果
  sync_progress.py push [书名关键字]  打开书并跳到 Apple Books 的位置
"""
import glob
import os
import re
import sqlite3
import subprocess
import sys
import time
import zipfile
from urllib.parse import quote

from lxml import etree

BOOKS_DIR = os.path.expanduser("~/Downloads/kindle-books")   # 推到 Kindle 的那份 EPUB
KINDLE_DIR = "/mnt/us/documents/llm"
IBOOKS = os.path.expanduser("~/Library/Containers/com.apple.iBooksX/Data/Documents")
KINDLE_HOST = os.environ.get("KINDLE_HOST", "kindle.local")  # 设成你 Kindle 的局域网 IP
SSH = ["ssh", "-i", os.path.expanduser("~/.config/mcp-show-on-kindle/id_ed25519"),
       "-o", "IdentitiesOnly=yes", "-p", "2222", "-o", "ConnectTimeout=10",
       "-o", "UserKnownHostsFile=" + os.path.expanduser("~/.config/mcp-show-on-kindle/known_hosts"),
       "-o", "HostKeyAlias=kindle", f"root@{KINDLE_HOST}"]
INSPECTOR = "http://127.0.0.1:8080/koreader"


def ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def apple_positions():
    """{title: (progress, cfi, modified_unix)}"""
    lib = glob.glob(f"{IBOOKS}/BKLibrary/BKLibrary*.sqlite")[0]
    ann = glob.glob(f"{IBOOKS}/AEAnnotation/AEAnnotation*.sqlite")[0]
    titles = {aid: (t, p) for aid, t, p in ro(lib).execute(
        "select ZASSETID, ZTITLE, ZREADINGPROGRESS from ZBKLIBRARYASSET")}
    out = {}
    for aid, cfi, mod in ro(ann).execute(
            "select ZANNOTATIONASSETID, ZANNOTATIONLOCATION, ZANNOTATIONMODIFICATIONDATE "
            "from ZAEANNOTATION where ZANNOTATIONTYPE=3 and ZANNOTATIONDELETED=0"):
        if aid in titles and cfi:
            title, prog = titles[aid]
            out[title] = (prog or 0.0, cfi, (mod or 0) + 978307200)
    return out


class Epub:
    def __init__(self, path):
        self.path = path
        self.z = zipfile.ZipFile(path)
        container = etree.fromstring(self.z.read("META-INF/container.xml"))
        self.opf_path = container.xpath("//*[local-name()='rootfile']/@full-path")[0]
        opf = etree.fromstring(self.z.read(self.opf_path))
        self.title = (opf.xpath("//*[local-name()='title']/text()") or [""])[0].strip()
        manifest = {i.get("id"): i.get("href") for i in opf.xpath("//*[local-name()='item']")}
        base = os.path.dirname(self.opf_path)
        self.spine = [(ref.get("idref"), os.path.normpath(os.path.join(base, manifest[ref.get("idref")])))
                      for ref in opf.xpath("//*[local-name()='itemref']")]

    def doc(self, href):
        parser = etree.XMLParser(recover=True, resolve_entities=False)
        return etree.fromstring(self.z.read(href.replace(os.sep, "/")), parser)


def parse_cfi(cfi):
    """'epubcfi(/6/34[chap14]!/4/2[x]/1,:0,:1)' -> (spine_step, spine_id, [(step, id)], offset)"""
    body = re.match(r"epubcfi\((.*)\)$", cfi).group(1)
    if "," in body:                       # 区间 CFI:取起点 = 公共父路径 + 起始局部路径
        parent, start, _ = body.split(",", 2)
        body = parent + start
    offset = None
    m = re.search(r":(\d+)$", body)
    if m:
        offset, body = int(m.group(1)), body[:m.start()]
    pkg, content = body.split("!", 1)
    steps = re.findall(r"/(\d+)(?:\[([^\]]*)\])?", pkg)
    spine_step, spine_id = int(steps[-1][0]), steps[-1][1] or None
    csteps = [(int(n), i or None) for n, i in re.findall(r"/(\d+)(?:\[([^\]]*)\])?", content)]
    return spine_step, spine_id, csteps, offset


def local(el):
    return etree.QName(el).localname.lower()


def cfi_to_xpointer(epub, cfi):
    spine_step, spine_id, csteps, _ = parse_cfi(cfi)
    idx = spine_step // 2                 # CFI /6/N -> spine 第 N/2 项(1 起)
    if spine_id:                          # 以 id 断言为准,防 spine 计数偏差
        ids = [i for i, _ in epub.spine]
        if spine_id in ids:
            idx = ids.index(spine_id) + 1
    root = epub.doc(epub.spine[idx - 1][1])

    node = root
    for step, el_id in csteps:
        if step % 2:                      # 奇数 = 文本节点位置,定位到其父元素即可
            break
        kids = [c for c in node if isinstance(c.tag, str)]
        nxt = kids[step // 2 - 1] if step // 2 - 1 < len(kids) else None
        if el_id and (nxt is None or nxt.get("id") != el_id):
            hit = root.xpath(f"//*[@id='{el_id}']")
            nxt = hit[0] if hit else nxt
        if nxt is None:
            break
        node = nxt

    # crengine 路径:/body/DocFragment[n]/body/... ;同名兄弟多于一个时才带 [i]
    chain = []
    n = node
    while n is not None and local(n) != "body":
        chain.append(n)
        n = n.getparent()
    parts = []
    for el in reversed(chain):
        same = [s for s in el.getparent() if isinstance(s.tag, str) and local(s) == local(el)]
        parts.append(local(el) + (f"[{same.index(el) + 1}]" if len(same) > 1 else ""))
    xp = f"/body/DocFragment[{idx}]/body" + "".join("/" + p for p in parts)
    label = (node.get("id") or "".join(node.itertext()).strip())[:40]
    return xp, label


def ssh(cmd, timeout=40):
    return subprocess.run(SSH + [cmd], capture_output=True, timeout=timeout)


def inspector(path):
    r = ssh(f"wget -q -O- -T 15 '{INSPECTOR}/{path}'")
    return r.returncode, r.stdout.decode(errors="replace").strip()


def arg(s):
    return quote(f'"{s}"', safe="")


def push(kindle_path, xp):
    code, cur = inspector("ui/document/file")
    if cur.strip('"') != kindle_path:
        for method in ("switchDocument", "openFile"):
            inspector(f"ui/{method}/{arg(kindle_path)}/")
        for _ in range(10):
            time.sleep(2)
            code, cur = inspector("ui/document/file")
            if code == 0 and cur.strip('"') == kindle_path:
                break
        else:
            return "KOReader 没有打开这本书"
    # 直接调 ReaderRolling:onGotoXPointer;event/GotoXPointer 实测发出去但不生效。
    # 刚打开的书可能还在排版,跳完回读位置,不对就重试
    frag = xp.split("/body", 2)[1]        # /DocFragment[n]
    for _ in range(6):
        inspector(f"ui/rolling/onGotoXPointer/{arg(xp)}/")
        time.sleep(2)
        code, now = inspector("ui/rolling/xpointer")
        if frag in now:
            _, page = inspector("ui/view/state/page")
            return f"✓ 已跳到 {now}(第 {page} 页)"
    return f"✗ 跳转没生效,当前位置 {now}"


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "plan"
    kw = sys.argv[2] if len(sys.argv) > 2 else ""
    apple = apple_positions()
    for path in sorted(glob.glob(f"{BOOKS_DIR}/*.epub")):
        ep = Epub(path)
        if kw and kw not in ep.title and kw not in os.path.basename(path):
            continue
        if ep.title not in apple:
            print(f"- {ep.title}: Apple Books 里没有阅读位置,跳过")
            continue
        prog, cfi, mod = apple[ep.title]
        xp, label = cfi_to_xpointer(ep, cfi)
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(mod))
        print(f"* {ep.title}\n  Apple: {prog:.1%}  {when}  {cfi}\n  → {xp}   «{label}»")
        if mode == "push":
            print("  " + push(f"{KINDLE_DIR}/{os.path.basename(path)}", xp))


if __name__ == "__main__":
    main()
