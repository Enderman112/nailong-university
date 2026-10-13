# 奶龙大学跳转页

打开域名 → 加载一个奶龙校徽过场页 → 约 2.6 秒后自动跳到学校官网。

这不只是一份页面，而是一个**生成器**：给一所学校的**校徽**和一张**奶龙图**，
填一份配置，就能跑出整套素材和两个页面。仓库里自带一个已经做好的实例
（`中国奶龙大学.org` → 湖州师范大学）。

| 主版式（仿 中国奶龙大学.com） | 备选版式（仿 哈尔滨奶龙大学.com） |
| --- | --- |
| ![index](docs/img/preview-index.png) | ![mascot](docs/img/preview-mascot.png) |

---

## 我该读哪份文档

| 你是 | 读这个 |
| --- | --- |
| **AI agent**（先读这个） | [`AGENTS.md`](AGENTS.md) —— 路由 + 硬性约束 |
| 想给**另一所学校**做一份 | [`docs/02-design-workflow.md`](docs/02-design-workflow.md) —— 要问用户哪些问题、怎么生成 |
| 想**部署上线 / 拆掉旧的 301** | [`docs/01-deploy-cloudflare.md`](docs/01-deploy-cloudflare.md) —— 人照着点 或 AI 拿 API Token 直接做 |
| 想知道**为什么长这样** | [`docs/03-reference-notes.md`](docs/03-reference-notes.md) —— 参考站逆向记录 |

两份工作流都写成了「AI 可以直接读、直接做」的形式：有前置检查、有确切命令、有验收标准、有回滚。

---

## 30 秒上手

```bash
python3 -m pip install Pillow

# 1) 改 config.json（要改什么见 docs/02 第 0 节的清单）
# 2) 把校徽和奶龙图放进 assets-src/
python3 tools/build-site.py      # 生成 site/ 下的全部素材和页面

# 3) 本地看效果（?stay = 演示模式，不会真的跳走）
cd site && python3 -m http.server 8791
#   http://127.0.0.1:8791/index.html?stay
#   http://127.0.0.1:8791/mascot.html
```

自检（真实 Chromium 渲染 + 验证真会跳转）：

```bash
npm i -D playwright && npx playwright install chromium
node tools/check-site.mjs http://127.0.0.1:8791/
```

部署到 Cloudflare Pages：

```bash
CLOUDFLARE_API_TOKEN=... CLOUDFLARE_ACCOUNT_ID=... tools/deploy-pages.sh
```

> ⚠️ **部署前必须先拆掉域名上那条旧的 301**。重定向规则优先于 Pages，
> 不拆的话页面永远不会显示。详见 [`docs/01-deploy-cloudflare.md`](docs/01-deploy-cloudflare.md)。

---

## 目录

```
config.json              所有可配项 —— 换学校只改这个 + 换两张原图
templates/               两个页面的模板（占位符 {{...}}）
site/                    生成出来的部署产物，Cloudflare Pages 就传这个目录
  index.html             主页面：旋转校徽环 + 倒计时 + 关于弹窗
  mascot.html            备选：卡片 + 校徽旁边的奶龙 + 进度条
  ring.webp core.webp    徽章两层（文字环 / 中心奶龙）
  favicon.png og.jpg mascot.png
tools/
  build-site.py          ← 主入口：素材 + 页面一次生成
  build-assets.py        素材流水线（校徽→环、奶龙抠图、合成 og/favicon/mascot）
  cf-inspect.sh          摸清某域名下所有可能导致跳转的 Cloudflare 配置（只读）
  deploy-pages.sh        wrangler 部署 + 绑域名
  check-site.mjs         Playwright 自检
docs/                   01 部署 / 02 设计工作流 / 03 逆向记录
assets-src/             原图（校徽、奶龙原图、抠好的奶龙）
```

---

## 换一所学校

```bash
□ 问用户：学校名 / 奶龙大学名 / 域名 / 跳转目标 / 校徽 / 奶龙 / 主色 / 校训 / 署名
□ curl 官网确认学校当前全名、校训、建校年、校徽在 logo 图里的位置
□ 两张原图丢进 assets-src/
□ 改 config.json
□ python3 tools/build-site.py
□ 亲眼看一遍 ring.webp / core.webp / og.jpg / mascot.png
□ node tools/check-site.mjs 本地跑过
□ 部署 + 拆 301
```

要问用户的清单、每项能不能自己查、以及完整原理，都在
[`docs/02-design-workflow.md`](docs/02-design-workflow.md)。

---

## 它是怎么做的（简述）

- **`ring.webp`**：从官方校徽里逐角度取最外缘 → 最小二乘拟合圆心和外径 →
  把墨色换成主色 → 挖空中心，只留会旋转的文字环。几何（外径 355、挖空到 0.686 倍）
  照抄参考站，所以能和参考站的素材直接互换。
- **`core.webp`**：奶龙原图四边洪水填充抠白底 → 反预乘去白边 → 下缘 smoothstep 淡出
  （原图往往是拦腰截断的，不淡出放进圆里像被刀切）→ 超过安全半径就整体缩小，
  免得压到会旋转的校名。
- **两个页面**：纯静态、零依赖、两个 HTML + 5 张图。主页面是「白盘 + 呼吸的奶龙 +
  无限旋转的文字环 + SVG 倒计时」，2.6 秒后 `location.replace`；点任意处立刻走；
  「关于」弹窗打开时暂停倒计时；`prefers-reduced-motion` 时关动画；没 JS 时
  `<noscript>` 里的 meta refresh 兜底。

细节和踩过的坑见 [`docs/02-design-workflow.md`](docs/02-design-workflow.md) 第 6、7 节。

---

## 免责

与任何学校**无官方关联**。校徽取自学校公开标识，奶龙形象由使用者提供。
本项目只做「域名 → 过场页 → 学校官网」这一条链路，不代表学校立场。

[![](https://img.shields.io/badge/powered_by-dsh-4D6BFE?style=flat-square&logo=deepseek&logoColor=white)](https://github.com/deepseek-ai/deepseek-harness)
