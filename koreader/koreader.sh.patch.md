# koreader.sh 防火墙补丁

在 `/mnt/us/koreader/koreader.sh` 中现有 `iptables -A INPUT -i wlan0 -p udp --dport 8134 -j ACCEPT` 之后加一行：

```sh
iptables -I INPUT 1 -p tcp --dport 8080 ! -i lo -j DROP
```

作用：HTTP inspector（8080，无鉴权）只能从 Kindle 本机回环访问；电脑通过 SSH 隧道/在 SSH 里 `curl 127.0.0.1:8080` 调用。
可用 `scripts/patch_koreader_sh.sh` 自动添加（会先备份为 koreader.sh.bak）。
