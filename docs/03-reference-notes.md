# 参考站逆向记录

做这份东西之前扒了三个站点，把「到底该长什么样」钉下来。换参考站时照这份重新扒一遍即可。

## 1. `中国奶龙大学.com` —— 主版式（`index.html`）的来源

| 项 | 值 |
| --- | --- |
| 域名解析 | Squarespace 上的一条 **302** → `https://nailong.dykey.net` |
| 真正的过场页 | `https://nailong.dykey.net/`（静态，10334 字节单文件 + 4 个图） |
| 页面结构 | 白底圆盘 + 旋转文字环 + 不转的中心奶龙 + 倒计时进度环 + 右下角「关于」弹窗 |
| 停留时长 | 2.6 秒后 `location.replace`（`prefers-reduced-motion` 时 1.2 秒） |
| 离场动画 | `.wrap` scale 1.18 + 淡出 450ms，同时文字环转速 1→8 倍 |
| 跳到哪 | `https://www.dlut.edu.cn/`（大连理工大学） |
| 资源 | `ring.webp` `core.webp` `favicon.png` `og.jpg`，全部**绝对路径**引用 |

### 素材几何（本项目直接照抄）

| 文件 | 尺寸 | 关键值 |
| --- | --- | --- |
| `ring.webp` | 720×720 | 外径 **355**，中心挖空到半径 **≈243**（即 0.686 × 外径），环面是**不透明白底** + 彩色文字 |
| `core.webp` | 720×720 | 内嵌校徽中心图案 + 奶龙；奶龙离圆心最大半径 ≈215 |
| `favicon.png` | 64×64 | 只用中心部分，没有文字环 |
| `og.jpg` | 600×600 | 完整徽章放白底，没有文字 |

CSS 里 `.badge::before` 是 `inset: 1.4%` 的白色圆盘，`.ring` 用 WAAPI 做 `rotate(0→1turn)` 4000ms 无限循环，
`.core` 是 `breathe`（scale 1→1.03）1.8 秒无限循环，进度环是 `viewBox="0 0 100 100"` 的 SVG
`stroke-dashoffset: 100 → 0`，时长由 JS 注入的 `--delay` 决定。

> 复刻时注意：`.progress` 的 `inset: -5.5%`，比徽章本身大一圈，所以倒计时圆环比徽章外径更靠外。

## 2. `哈尔滨奶龙大学.com` —— 备选版式（`mascot.html`）的来源

| 项 | 值 |
| --- | --- |
| punycode | `xn--qvrq5h0gz4e1yak04fbi5e.com` |
| 结构 | 深蓝渐变背景 + 飘落雪花 + 玻璃卡片；卡片里是「校徽 + 右下角探出半只奶龙」的头图 |
| 头图 | `logo.png` 752×680，哈工大校徽 + 右下一只奶龙（奶油白 RGB，不是透明底） |
| 文案 | 标题 / 英文名 / `校训：规格严格，功夫到家` / 进度条 / 依次切换的 4 句状态 / 跳过按钮 |
| 时长 | `STEP_MS=800` × 4 句 = 3.2 秒，再停 500ms 后跳转 |
| 跳到哪 | `https://www.hit.edu.cn`（哈尔滨工业大学） |
| 署名 | 右下角 `creater:yutou sishu` |

本项目复刻时**换了配色**（深蓝 → 奶龙黄/奶油色），因为深蓝雪景是哈尔滨的梗，硬套到南方学校不搭。
雪花也换成了飘落的黄色小星点。

## 3. `中国奶龙大学.org` —— 被改造的对象

扒的时候的状态：

```
HTTP/2 301
location: https://www.huznu.edu.cn/
server: cloudflare
```

- NS 在 Cloudflare（`annalise.ns.cloudflare.com` / `clyde.ns.cloudflare.com`），A 记录是 Cloudflare 代理 IP
  （`104.21.3.18`、`172.67.130.10`）
- 所以这是一条 **Cloudflare 层的 301**，不是注册商 URL Forwarding，也不是 DNS 直接指过去
- 目标学校：**湖州师范大学**（`huznu.edu.cn`，原名湖州师范学院，校徽和官网站名都已改为「湖州师范大学」）
  - 英文名 `HUZHOU NORMAL UNIVERSITY`，校训「**明体达用**」，建校 **1916** 年
- 该域名下的 HTTPS 握手对某些客户端会失败（`sslv3 alert handshake failure`），
  用 punycode + 现代 UA 请求正常 —— **排查时优先用 punycode 形式**：

```bash
curl -sSI "https://xn--fiqs8srwb9iv6f6w9n.org/" | sed -n '1p;/^[Ll]ocation/p'
```

## 4. 顺带记下的坑

- 中文域名直接用 curl 发 `Host` 头会 400（`malformed Host header`），必须走 punycode。
- 参考站的 `core.webp` 一开始反复 `Recv failure: Connection reset`，换 UA 多试几次才下来；
  后来挂了本地代理就稳了。扒素材时遇到 reset 先重试，别急着换方案。
- 官方 `logo.png`（5660×1182）是 **P 模式带 alpha** 的 PNG，背景透明、墨色是单色（`#971E23`），
  所以「alpha 即墨量」，染色时直接用 alpha 当覆盖度即可，不需要做亮度阈值分割。
