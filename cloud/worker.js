// kindle-sync — 一个给 KOReader 用的极简云端中转(Cloudflare Worker + KV)。
//
// 1. 进度:完整实现 KOReader「进度同步」插件(kosync)的四个接口,Kindle 不用改任何代码,
//    只要把「自定义同步服务器」指到这里。
// 2. 划线:给 hlsync.koplugin(本仓库 plugin/hlsync.koplugin)用的两个接口,
//    Kindle 关书/休眠时把整本书的 annotations 快照推上来,电脑端 GET 拉走。
// 3. 云端书架:电脑 PUT /books/<文件名> 上传 EPUB/PDF(切块存 KV,免费额度 1 GB),
//    设备上的 hlsync 插件联网时拉清单、补下载,不用设备和电脑同网、也不用插线。
//
// 单用户:凭据放在 Worker secrets 里(SYNC_USER / SYNC_KEY,KEY = md5(密码) 的小写十六进制,
// 和 kosync 插件存在设置里的 userkey 一致)。所有接口都要 x-auth-user / x-auth-key 两个头。
//
// 与官方 koreader-sync-server 的唯一扩展:PUT /syncs/progress 允许带 timestamp(秒),
// 电脑端推 Apple Books 进度时用它填"真实阅读时刻",kosync 据此判断谁更新。

const CHUNK = 20 * 1024 * 1024;   // 书切块大小,KV 单值上限 25 MiB
const JSON_HEADERS = { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" };

function reply(status, obj) {
  return new Response(JSON.stringify(obj), { status, headers: JSON_HEADERS });
}

function authed(req, env) {
  return req.headers.get("x-auth-user") === env.SYNC_USER && req.headers.get("x-auth-key") === env.SYNC_KEY;
}

async function readJson(req) {
  try { return await req.json(); } catch { return null; }
}

async function listAll(env, prefix) {
  const out = [];
  let cursor;
  do {
    const page = await env.KV.list({ prefix, cursor });
    for (const k of page.keys) {
      const v = await env.KV.get(k.name, "json");
      if (v) out.push(v);
    }
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  return out;
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";
    const m = req.method;

    if (path === "/" && m === "GET") return reply(200, { service: "kindle-sync", ok: true });

    // kosync: 注册。单用户部署,只认 secrets 里那一对,别的一律 402(插件会把它显示为"用户已存在")
    if (path === "/users/create" && m === "POST") {
      const b = await readJson(req);
      if (b && b.username === env.SYNC_USER && md5(String(b.password)) === env.SYNC_KEY) return reply(201, { username: b.username });
      return reply(402, { message: "registration disabled: single-user server" });
    }

    if (!authed(req, env)) return reply(401, { message: "Unauthorized" });

    if (path === "/users/auth" && m === "GET") return reply(200, { authorized: "OK" });

    // kosync: 推进度
    if (path === "/syncs/progress" && m === "PUT") {
      const b = await readJson(req);
      if (!b || !b.document || b.progress == null || b.percentage == null || !b.device) return reply(400, { message: "missing fields" });
      const ts = Number.isFinite(+b.timestamp) && +b.timestamp > 0 ? Math.floor(+b.timestamp) : Math.floor(Date.now() / 1000);
      const rec = {
        document: String(b.document), progress: String(b.progress), percentage: +b.percentage,
        device: String(b.device), device_id: b.device_id ? String(b.device_id) : "",
        metadata: b.metadata || undefined, timestamp: ts,
      };
      await env.KV.put("p:" + rec.document, JSON.stringify(rec));
      return reply(200, { document: rec.document, timestamp: ts });
    }

    // kosync: 拉进度。没有记录时返回 200 + 只有 document 字段(插件据此提示"没有进度")
    let mm = path.match(/^\/syncs\/progress\/([^/]+)$/);
    if (mm && m === "GET") {
      const rec = await env.KV.get("p:" + mm[1], "json");
      return reply(200, rec || { document: mm[1] });
    }

    // 扩展:列出全部进度(电脑端看总览)
    if (path === "/progress" && m === "GET") return reply(200, await listAll(env, "p:"));

    // 划线快照:整本覆盖写(幂等),电脑端整份拉
    mm = path.match(/^\/hl\/([^/]+)$/);
    if (mm && m === "PUT") {
      const b = await readJson(req);
      if (!b || !Array.isArray(b.annotations)) return reply(400, { message: "annotations[] required" });
      const rec = { ...b, document: mm[1], received_at: Math.floor(Date.now() / 1000) };
      await env.KV.put("h:" + mm[1], JSON.stringify(rec));
      return reply(200, { document: mm[1], count: b.annotations.length });
    }
    if (mm && m === "GET") {
      const rec = await env.KV.get("h:" + mm[1], "json");
      return rec ? reply(200, rec) : reply(404, { message: "not found" });
    }
    if (path === "/hl" && m === "GET") return reply(200, await listAll(env, "h:"));

    // 云端书架:书存在同一个 KV 里,按 20 MB 切块(KV 单值上限 25 MiB)。
    //   bm:<文件名>        元数据 {name,size,chunks,uploaded}
    //   bc:<文件名>:<序号>  内容块
    // 电脑 PUT 上传,设备上的 hlsync 插件 GET /books 拿清单,缺的再 GET /books/<文件名> 下载。
    if (path === "/books" && m === "GET") {
      const out = await listAll(env, "bm:");
      return reply(200, out.map(({ name, size, uploaded }) => ({ name, size, uploaded })));
    }
    mm = path.match(/^\/books\/(.+)$/);
    if (mm) {
      let name;
      try { name = decodeURIComponent(mm[1]); } catch { return reply(400, { message: "bad name" }); }
      if (name.includes("/") || name.includes("..") || name.length > 200) return reply(400, { message: "bad name" });
      const metaKey = "bm:" + name;
      if (m === "PUT") {
        const buf = new Uint8Array(await req.arrayBuffer());
        if (!buf.length) return reply(400, { message: "empty body" });
        const old = await env.KV.get(metaKey, "json");
        const n = Math.ceil(buf.length / CHUNK);
        for (let i = 0; i < n; i++) await env.KV.put(`bc:${name}:${i}`, buf.subarray(i * CHUNK, (i + 1) * CHUNK));
        if (old && old.chunks > n) for (let i = n; i < old.chunks; i++) await env.KV.delete(`bc:${name}:${i}`);
        const meta = { name, size: buf.length, chunks: n, uploaded: Math.floor(Date.now() / 1000) };
        await env.KV.put(metaKey, JSON.stringify(meta));   // 元数据最后写:写到一半失败时清单里看不到半本书
        return reply(200, meta);
      }
      if (m === "GET" || m === "HEAD") {
        const meta = await env.KV.get(metaKey, "json");
        if (!meta) return reply(404, { message: "not found" });
        const headers = {
          "content-length": String(meta.size), "content-type": "application/octet-stream",
          "content-disposition": "attachment; filename*=UTF-8''" + encodeURIComponent(name), "cache-control": "no-store",
        };
        if (m === "HEAD") return new Response(null, { status: 200, headers });
        let i = 0;
        const body = new ReadableStream({
          async pull(ctrl) {
            if (i >= meta.chunks) return ctrl.close();
            const part = await env.KV.get(`bc:${name}:${i++}`, "arrayBuffer");
            if (!part) return ctrl.error(new Error("missing chunk"));
            ctrl.enqueue(new Uint8Array(part));
          },
        });
        return new Response(body, { status: 200, headers });
      }
      if (m === "DELETE") {
        const meta = await env.KV.get(metaKey, "json");
        if (meta) {
          await env.KV.delete(metaKey);
          for (let i = 0; i < meta.chunks; i++) await env.KV.delete(`bc:${name}:${i}`);
        }
        return reply(200, { name, deleted: !!meta });
      }
    }

    return reply(404, { message: "not found" });
  },
};

// 紧凑版 MD5(Workers 的 WebCrypto 不含 MD5),只用于 /users/create 核对密码
function md5(str) {
  const bytes = new TextEncoder().encode(str);
  const K = new Uint32Array(64), S = [7,12,17,22,7,12,17,22,7,12,17,22,7,12,17,22,5,9,14,20,5,9,14,20,5,9,14,20,5,9,14,20,4,11,16,23,4,11,16,23,4,11,16,23,4,11,16,23,6,10,15,21,6,10,15,21,6,10,15,21,6,10,15,21];
  for (let i = 0; i < 64; i++) K[i] = Math.floor(Math.abs(Math.sin(i + 1)) * 2 ** 32);
  const len = bytes.length, padded = new Uint8Array(((len + 8) >> 6 << 6) + 64);
  padded.set(bytes); padded[len] = 0x80;
  const dv = new DataView(padded.buffer);
  dv.setUint32(padded.length - 8, (len * 8) >>> 0, true);
  dv.setUint32(padded.length - 4, Math.floor(len * 8 / 2 ** 32), true);
  let a0 = 0x67452301, b0 = 0xefcdab89, c0 = 0x98badcfe, d0 = 0x10325476;
  const rotl = (x, c) => (x << c) | (x >>> (32 - c));
  for (let off = 0; off < padded.length; off += 64) {
    const M = new Uint32Array(16);
    for (let i = 0; i < 16; i++) M[i] = dv.getUint32(off + i * 4, true);
    let A = a0, B = b0, C = c0, D = d0;
    for (let i = 0; i < 64; i++) {
      let F, g;
      if (i < 16) { F = (B & C) | (~B & D); g = i; }
      else if (i < 32) { F = (D & B) | (~D & C); g = (5 * i + 1) % 16; }
      else if (i < 48) { F = B ^ C ^ D; g = (3 * i + 5) % 16; }
      else { F = C ^ (B | ~D); g = (7 * i) % 16; }
      F = (F + A + K[i] + M[g]) >>> 0;
      A = D; D = C; C = B; B = (B + rotl(F, S[i])) >>> 0;
    }
    a0 = (a0 + A) >>> 0; b0 = (b0 + B) >>> 0; c0 = (c0 + C) >>> 0; d0 = (d0 + D) >>> 0;
  }
  return [a0, b0, c0, d0].map(v => { const b = new Uint8Array(4); new DataView(b.buffer).setUint32(0, v, true); return [...b].map(x => x.toString(16).padStart(2, "0")).join(""); }).join("");
}
