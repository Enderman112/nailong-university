# AGENTS.md

给 AI agent 的入口。**先读这一页，再按下面的路由跳到你真正需要的那份。**

## 这是什么

一个「奶龙大学」跳转页生成器 + 部署手册。用户给一所学校的**校徽**和一张**奶龙图**，
生成一个过场页：打开域名 → 显示奶龙校徽页 → 2.6 秒后跳到学校官网。

仓库自带一份已经做好的实例（`config.json` = 中国奶龙大学.org → 湖州师范大学）。

## 路由：用户想要什么 → 你该读哪份

| 用户说的话 | 你要读 | 你会做什么 |
| --- | --- | --- |
| 「给 XX 学校也整一个」「换成我们学校」 | **`docs/02-design-workflow.md`** | 先按第 0 节的清单**问用户**，填 `config.json`，跑 `tools/build-site.py` |
| 「部署上去」「怎么上线」「拆掉那个 301」 | **`docs/01-deploy-cloudflare.md`** | 判断有没有 API Token，选 MODE A（指导）或 MODE B（你用 API 直接做） |
| 「为什么是这么设计的」「参考站长什么样」 | **`docs/03-reference-notes.md`** | 逆向记录，几何参数都在这 |
| 「我要换个跳转目标 / 改文案」 | 改 `config.json`，跑 `tools/build-site.py --no-assets` | 不用碰 Cloudflare |

## 硬性约束（别违反）

1. **不要手改 `site/*.html`** —— 它们是 `templates/*.tmpl` + `config.json` 生成的，下次生成会覆盖。
   要改就改模板或 config。
2. **`config.json` 里没问过用户的项不要自己编**。学校名、奶龙大学叫什么、域名、跳转目标、
   校徽图、奶龙图 —— 这六项必须有用户的答案或明确授权，见 `docs/02-design-workflow.md` 第 0 节。
3. **奶龙图必须由用户提供**，不要自己从网上抓（版权）。
4. **`site/` 里所有资源都是绝对路径**（`/ring.webp`）→ 必须部署在**域名根目录**。
5. **部署时先拆掉旧的 301 再传页面**，否则重定向规则优先于 Pages，页面永远不显示。
6. 动 Cloudflare 之前**先备份现状**（`docs/01` 第 3.1 节有命令），并准备好回滚。

## 常用命令

```bash
# 生成整套站点（图片 + 两个页面）
python3 tools/build-site.py            # 需要 Pillow
python3 tools/build-site.py --no-assets   # 只重生成 HTML

# 本地预览
cd site && python3 -m http.server 8791
#   http://127.0.0.1:8791/index.html?stay   ← ?stay = 演示模式，不真的跳走
#   http://127.0.0.1:8791/mascot.html

# 自检（真实浏览器渲染 + 跳转验证）
node tools/check-site.mjs http://127.0.0.1:8791/

# 摸清某个域名的 Cloudflare 现状（需要 API Token）
CLOUDFLARE_API_TOKEN=... tools/cf-inspect.sh <域名>

# 部署到 Cloudflare Pages（需要 API Token + Account ID）
tools/deploy-pages.sh
```

## 目录

```
config.json            所有可配项（换学校只改这个 + 换两张图）
templates/             两个页面的模板，占位符是 {{...}}
site/                  生成的部署产物（Cloudflare Pages 就传这个目录）
tools/build-assets.py  素材流水线：校徽 → ring.webp，奶龙 → core.webp，以及 og/favicon/mascot
tools/build-site.py    调上面那个，再渲染模板 → 一条命令出全部
tools/cf-inspect.sh    列出某域名下所有可能导致跳转的 Cloudflare 配置
tools/deploy-pages.sh  wrangler 部署 + 绑域名
tools/check-site.mjs   Playwright 自检
docs/01…03             部署手册 / 设计工作流 / 逆向记录
assets-src/            原图（校徽、奶龙、抠好的奶龙）
```

## 交付前必须做的事

- 生成的图**自己看一眼**（尤其 `ring.webp` 的文字环和 `og.jpg` 的中文有没有变豆腐块）
- `node tools/check-site.mjs` 跑过
- 如果动了线上：`curl -sSI https://<域名>/ | head -1` 确认是 `200` 而不是 `301`

## 免责

与任何学校**无官方关联**。校徽取自学校公开标识，奶龙形象由用户提供。
本项目只处理「域名 → 过场页 → 学校官网」这条链路，不代表学校立场。

[![](https://img.shields.io/badge/powered_by-dsh-4D6BFE?style=flat-square&logo=deepseek&logoColor=white)](https://github.com/deepseek-ai/deepseek-harness)
