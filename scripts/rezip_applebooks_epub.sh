#!/usr/bin/env bash
# Apple Books 里的 .epub 在磁盘上其实是「文件夹」，要重新打包成标准 EPUB 才能推到 Kindle。
# 用法: ./rezip_applebooks_epub.sh "<某书.epub 文件夹>" [输出目录，默认 ~/Downloads/kindle-books]
set -euo pipefail
SRC="${1:?给出 .epub 文件夹路径}"; OUT="${2:-$HOME/Downloads/kindle-books}"
[ -d "$SRC" ] || { echo "不是文件夹，本来就是标准 epub，直接用即可"; exit 0; }
mkdir -p "$OUT"; DST="$OUT/$(basename "$SRC")"; rm -f "$DST"
cd "$SRC"
export COPYFILE_DISABLE=1
zip -X0 "$DST" mimetype                         # mimetype 必须第一个且不压缩
zip -Xr9D "$DST" . -x mimetype -x '.*' -x '__MACOSX/*' -x 'iTunesMetadata*.plist'
echo "→ $DST"
