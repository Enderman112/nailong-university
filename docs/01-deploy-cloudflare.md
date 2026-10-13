# 部署：Cloudflare Pages + 拆掉原来的 301

> **这份是给 AI agent 读的执行手册**，人也可以照着做。
> 读完这一份 + 仓库里的 `site/` 目录，就能把用户的域名从「直接 301 去学校官网」改成
> 「先显示奶龙过场页，再由页面自己跳到学校官网」。

> ### ⚠️ 域名和跳转目标都是**变量**，不是固定值
>
> 这两项**来自用户**，不要沿用本仓库实例的取值。开工前先定下来：
>
> | 变量 | 是什么 | 从哪来 |
> | --- | --- | --- |
> | `DOMAIN` | 用户的域名（中文原样写） | 问用户 |
> | `TARGET` | 页面最后跳去的网址（学校官网） | 问用户，或 `config.json` 的 `target_url` |
>
> ```bash
> export DOMAIN='用户给你的域名'            # 例：中国奶龙大学.org
> export TARGET='https://用户学校官网/'     # 例：https://www.huznu.edu.cn/
> # 中文域名要转 punycode，后面 curl 和 API 都用它
> export DOMAIN_PUNY=$(python3 -c "import sys;print(sys.argv[1].encode('idna').decode())" "$DOMAIN")
> echo "$DOMAIN_PUNY"
> ```
>
> 本手册正文里出现的 `中国奶龙大学.org`、`xn--fiqs8srwb9iv6f6w9n.org`、`https://www.huznu.edu.cn`
> 都只是**本仓库自带那份实例**的取值，用来举例；照着做时全部换成你自己的变量。

| | |
| --- | --- |
| 目标域名 | `$DOMAIN`（**由用户提供**） |
| 部署产物 | 仓库的 `site/` 目录（纯静态，没有构建步骤） |
| 页面跳转目标 | `$TARGET`（写在 `config.json` 的 `target_url`，由它生成到页面里） |
| 需要的东西 | 一个 Cloudflare 账号 + 该域名所在的 zone + 一个 API Token（见第 2 节） |

---

## 0. 先确认现状（别跳这一步）

```bash
curl -sSI "https://$DOMAIN_PUNY/" | sed -n '1p;/^[Ll]ocation/p'
```

| 看到什么 | 说明 | 下一步 |
| --- | --- | --- |
| `301` + `location: $TARGET` | 旧 301 还在，就是本手册要处理的状态 | 继续第 1 节 |
| `200` 且是奶龙页面 | 301 已经拆掉了 | 跳到第 5 节 |
| `200` 但是学校官网 | DNS 被直接指到学校了，不是 Cloudflare 重定向 | 先查 DNS（第 3.5 节） |
| `522 / 525 / 526` | 回源或证书有问题 | 先修 DNS/证书，再回来 |
| 解析不到 | DNS 没配 | 先去 Cloudflare 加 zone |

顺手把「是不是 Cloudflare 在处理」也确认一下：

```bash
curl -sSI "https://$DOMAIN_PUNY/" | grep -i '^server'
```

出现 `server: cloudflare` 基本就能确定重定向是 Cloudflare 层做的（不是注册商 URL Forwarding）。

---

## 1. 选一种工作模式

### MODE A — 只做指导（你手上没有 Cloudflare 凭据）

1. 先用第 2 节的话术向用户要 **API Token**；用户愿意给 → 转 MODE B。
2. 用户不愿意给凭据 → 按第 3、4、5、6 节的「**控制台操作**」子段落逐步引导，
   每一步都要告诉用户：**点哪里 → 应该看到什么 → 怎么确认成功**。
3. 不要凭空猜测用户的账号里有什么；让用户按第 3 节的输出念给你听。

### MODE B — 你直接做（用户给了 token）

```bash
export CLOUDFLARE_API_TOKEN='...'      # 用户建，见第 2 节
export ZONE="$DOMAIN_PUNY"
export PROJECT='nailong-university'    # Pages 项目名，随便取
```

**先跑 preflight，缺什么立刻停下来问，不要编：**

```bash
# token 是否有效
curl -sS "https://api.cloudflare.com/client/v4/user/tokens/verify" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" | jq -r '.result.status'

# zone_id（token 无效 / 权限不够这里会返回空或 403）
ZONE_ID=$(curl -sS "https://api.cloudflare.com/client/v4/zones?name=$ZONE" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" | jq -r '.result[0].id // empty')
echo "ZONE_ID=$ZONE_ID"
[ -n "$ZONE_ID" ] || { echo "拿不到 zone_id：token 缺 Zone:Read，或这个域名不在该账号下"; }

# account_id
curl -sS "https://api.cloudflare.com/client/v4/accounts" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" | jq -r '.result[] | "\(.id)  \(.name)"'
```

`tools/cf-inspect.sh` 把上面这些 + 第 3 节的排查一次性跑完：

```bash
CLOUDFLARE_API_TOKEN=... tools/cf-inspect.sh "$ZONE"
```

---

## 2. 需要的最小 API Token 权限

在 <https://dash.cloudflare.com/profile/api-tokens> → **Create Custom Token** 建，权限最小集：

| 权限 | 干什么用 | 只读够不够 |
| --- | --- | --- |
| Account → **Cloudflare Pages** → Edit | 建项目、上传产物、绑自定义域名 | 要 Edit |
| Zone → **Dynamic URL Redirects** → Edit | 找到并删掉那条 301（单条重定向规则） | 发现用 Read，删要 Edit |
| Zone → **Zone** → Read | 拿 zone_id | Read |
| Zone → **DNS** → Edit | apex 绑定 Pages 时自动改 DNS 记录 | 要 Edit |
| Account → **Mass URL Redirects** → Edit | **只有**当 301 是用「批量重定向」做的时候才需要 | 要 Edit |

Scope 记得选 **Include → Specific zone → 用户的域名**。

**要凭据时的话术**（MODE A 用）：

> 我要帮你把 `.org` 那条 301 换成跳转页，需要在 Cloudflare 建一个 API Token。
> 打开 https://dash.cloudflare.com/profile/api-tokens → Create Custom Token，按上面这张表勾权限，
> Zone Resources 选到用户的域名。建好把 token 贴给我（我只会调 Cloudflare 的 API）。
> 不想给凭据也行，我一步步告诉你点哪里。

---

## 3. 找出那条 301 藏在哪里

Cloudflare 能做「域名级 301」的地方一共 **4 处**，逐个排查。**排查阶段不要删任何东西。**

### 3.1 单条重定向规则（Redirect Rules，最常见）

```bash
# 该 zone 下所有 ruleset（重点看 phase=http_request_dynamic_redirect）
curl -sS "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/rulesets" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  | jq -r '.result[] | "\(.phase)\t\(.id)\t\(.name)"'

# 直接看重定向规则的入口 ruleset
curl -sS "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/rulesets/phases/http_request_dynamic_redirect/entrypoint" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" | jq '.result | {id, rules}'
```

命中特征：某条 rule 的 `action` 是 `redirect`，`action_parameters.from_value.target_url.value` 就是 `$TARGET`，
`status_code` 是 `301`。

> **控制台操作**：Cloudflare 控制台 → 选用户的域名 → 左侧 **规则 → 重定向规则**。
> 应该能看到一条「目标 URL = $TARGET」的规则。

**先把现状存下来再动手**（回滚要用）：

```bash
curl -sS "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/rulesets/phases/http_request_dynamic_redirect/entrypoint" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" | jq '.result' > /tmp/redirect-backup.json
cat /tmp/redirect-backup.json
```

**删掉它**——两种都行：

```bash
# A. 只删这一条规则（记下 ruleset_id 和 rule_id）
curl -sS -X DELETE "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/rulesets/$RULESET_ID/rules/$RULE_ID" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" | jq '.success'

# B. 重写整个入口 ruleset，把 rules 换成剩下的那些（原来是空的就传 []）
curl -sS -X PUT "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/rulesets/phases/http_request_dynamic_redirect/entrypoint" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H "Content-Type: application/json" \
  --data '{"rules": []}' | jq '.success, .errors'
```

规则是 Disable 而不是删也行：把该 rule 的 `enabled` 改成 `false` 再 PUT 回去。
**但如果这是 zone 里唯一的重定向规则，直接删更干净。**

> **控制台操作**：重定向规则列表 → 该规则右侧 `⋯` → **删除**（或把开关关掉）。

### 3.2 批量重定向（Bulk Redirects）——注意它挂在**账号级**

```bash
curl -sS "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/rulesets" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  | jq -r '.result[] | select(.phase=="http_request_redirect") | "\(.id)\t\(.name)"'

# 再看里面的 list
curl -sS "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/rules/lists" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  | jq -r '.result[] | "\(.id)\t\(.name)\t\(.num_items) items"'
```

> **控制台操作**：**账号**级菜单（不是 zone）→ **批量重定向**。

### 3.3 页面规则（Page Rules，老功能，仍然有效）

```bash
curl -sS "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/pagerules" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  | jq -r '.result[] | {id, target: .targets, action: .actions}'
```

命中特征：`actions` 里有 `forwarding_url`，`url` 指向学校官网。

```bash
curl -sS -X DELETE "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/pagerules/$PAGERULE_ID" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" | jq '.success'
```

> **控制台操作**：**规则 → 页面规则**。

### 3.4 Worker 路由 / Worker 里的跳转

```bash
curl -sS "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/workers/routes" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  | jq -r '.result[] | "\(.id)\t\(.pattern)\t\(.script // "-")"'
```

有路由命中这个域名 → 去看那个 Worker 的代码里有没有 `Response.redirect(..., 301)`。

### 3.5 顺带查 DNS（排除「直接指到学校」）

```bash
curl -sS "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records?per_page=100" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  | jq -r '.result[] | "\(.type)\t\(.name)\t\(.content)\tproxied=\(.proxied)"' | tee /tmp/dns-backup.txt
```

`@` 上如果是 `A` 指向 Cloudflare 的 anycast IP（`104.x` / `172.67.x`）并且 `proxied=true`，说明流量是 Cloudflare 接的，
内容由后面的规则决定 —— 这正是要拆 301 而不是改 DNS 的情况。

> 如果 `@` 是一条 `CNAME` 指向学校官网，那是真·DNS 跳转，把这行备份后删掉即可。

---

## 4. 部署 Pages

产物就在 `site/`，**不要上传 `tools/` `docs/` `assets-src/`**。

> ### 关于「首页文件」：不用指定，`index.html` 是默认约定
>
> Pages **没有**「哪个文件当首页」这个设置项。只要 `index.html` 落在**输出根目录**，
> 访问 `/` 就自动返回它。
>
> 所以要盯的不是首页文件名，而是**目录层级别多套一层**：
>
> | | 结果 |
> | --- | --- |
> | ✅ 对 | `https://<项目>.pages.dev/` 直接出奶龙页面，`/ring.webp` 也是 200 |
> | ❌ 多套一层 | `/` 返回 404，或者你得访问 `https://<项目>.pages.dev/site/` 才看得到 |
>
> 后者说明你把 `site` 这个**文件夹本身**当成了要传的东西，而不是「`site` 里的内容」。
> 页面里引用的是 `/ring.webp` 这种**绝对路径**，一旦多套一层，图和样式会全部 404。

### MODE B：命令行（推荐）

```bash
cd <仓库根目录>

# 首次：建项目
npx wrangler@latest pages project create "$PROJECT" --production-branch=main

# 上传（--commit-dirty 是因为工作区可能有未提交改动）
npx wrangler@latest pages deploy site \
  --project-name="$PROJECT" --branch=main --commit-dirty=true
```

`wrangler pages deploy site` 上传的是 **`site` 目录里的内容**，`index.html` 会直接落在根，
这正是我们要的。wrangler 认 `CLOUDFLARE_API_TOKEN` 和 `CLOUDFLARE_ACCOUNT_ID` 两个环境变量，
不用 `wrangler login`。输出里会给一个 `https://<hash>.<project>.pages.dev` 预览地址，
**先打开它确认页面正常**。

### MODE A：控制台拖拽

> Cloudflare 控制台 → **Workers & Pages** → **Create** → **Pages** → **Upload assets** →
> 项目名随意 → 把仓库里的 **`site` 文件夹拖进去** → **Deploy site**。

拖完如果 `/` 是 404，就说明被套了一层：回去改成拖 **`site` 文件夹里面的那些文件**
（`index.html`、`ring.webp`…），别拖文件夹本身。

### 如果用 Git 集成（从仓库自动构建）

| 设置项 | 填什么 |
| --- | --- |
| Framework preset | `None` |
| Build command | **留空**（这个项目没有构建步骤） |
| Build output directory | `site` |

不要图省事把 Build command 写成 `cd site` 之类 —— 没有构建步骤，只填输出目录就够了。
仓库里的 `.github/workflows/deploy-pages.yml` 走的是 wrangler 直传，不走这条路径。

### 部署完先自检目录层级

```bash
P=https://<项目>.pages.dev

curl -sSI "$P/" | head -1                                   # 期望 HTTP/2 200
curl -sS  "$P/" | grep -c '中国奶龙大学'                     # 期望 >= 1
curl -sS -o /dev/null -w '%{http_code}\n' "$P/ring.webp"    # 期望 200，不是 404
```

三条都过，说明层级没问题，可以继续绑域名了。

### 注意：Pages 对**未知路径**会回 `index.html` 且给 200

所以**不能用「curl 一下不是 404」来判断某个文件存不存在**。实测（本项目线上）：

| 请求 | 结果 |
| --- | --- |
| `/` | 200（index.html） |
| `/index.html` | 308 → `/` |
| `/rotate` | 200 |
| `/rotate.html` | 308 → `/rotate` |
| `/mascot.html`（该版式没生成时） | **200，返回的其实是 index.html** |
| `/随便什么` | **200，返回的其实是 index.html** |

这正好解释了参考站 HTML 里那句注释「任意路径都会返回本页，相对路径会在 `/a/b` 下失效」
—— 参考站也跑在 Pages 上。

要确认一个文件**真的**存在，只能比对内容，不能看状态码。
`tools/check-site.mjs` 的 `findAlt()` 就是这么做的：拉下来跟 index.html 比，
一模一样就判定为 fallback 而不是真页面。

### 两套版式谁当首页：改配置，别手动改名

| `config.json` 的 `homepage` | `/` 显示 | 另一个在 |
| --- | --- | --- |
| `"index"`（默认） | 旋转校徽环 + 倒计时（仿 中国奶龙大学.com） | `/mascot.html` |
| `"mascot"` | 校徽旁边一只奶龙 + 进度条（仿 哈尔滨奶龙大学.com） | `/rotate.html` |

```json
"homepage": "mascot"
```

然后重新生成：

```bash
python3 tools/build-site.py
```

**为什么不要手动 `mv`**：`site/*.html` 是 `templates/` + `config.json` 生成的，
你手改完下次一跑生成器就没了。生成器还会自动把「换首页后遗留的旧文件」删掉，
免得线上多一个重复页面。

### 没有 Pages 的替代方案

任何静态托管都行（GitHub Pages / Vercel / 对象存储 / 自己的虚拟主机）。
**但页面里的资源是绝对路径（`/ring.webp`）**，所以必须放在**站点根目录**；
要放子目录的话，把 `site/*.html` 里所有 `/xxx.webp` 改成相对路径。

---

## 5. 把域名绑到 Pages

**中文域名一定要填 punycode** —— 就是开头那个 `$DOMAIN_PUNY`，命令行里直接用变量。

```bash
curl -sS -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/pages/projects/$PROJECT/domains" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H "Content-Type: application/json" \
  --data "{\"name\":\"$DOMAIN_PUNY\"}" | jq '.success, .result.name, .errors'
```

> **控制台操作**：Pages 项目 → **Custom domains → Set up a domain** → 填 `$DOMAIN_PUNY`。
> 控制台会把它显示成中文，这是正常的。

**报「记录已存在 / DNS record already exists」时**：`@` 上还留着旧的 A/AAAA 记录。
先备份（第 3.5 节已经存了 `/tmp/dns-backup.txt`），删掉冲突的那条，再重试绑定。

```bash
curl -sS -X DELETE "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records/$RECORD_ID" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" | jq '.success'
```

证书是自动签的，一般 1～5 分钟。等 `https://` 打得开再继续。

---

## 6. 验收（必须全过）

```bash
# 域名用开头定义的 $DOMAIN_PUNY，跳转目标用 $TARGET

# 1) 不再是 301
curl -sSI "https://$DOMAIN_PUNY/" | sed -n '1p'         # 期望 HTTP/2 200

# 2) 返回的确实是我们的页面
curl -sS "https://$DOMAIN_PUNY/" | grep -c '中国奶龙大学'  # 期望 >= 1（关键词换成页面上那句大标题）

# 3) 页面里写死的跳转目标仍然是学校官网
curl -sS "https://$DOMAIN_PUNY/" | grep -o "$(echo "$TARGET" | sed -E 's#^https?://##; s#/$##')" | head -1

# 4) 静态资源都在（不能 404）
for f in ring.webp core.webp favicon.png og.jpg; do
  printf '%s -> ' "$f"
  curl -sS -o /dev/null -w '%{http_code}\n' "https://$DOMAIN_PUNY/$f"
done

# 5) 真浏览器：渲染 + 2.6 秒后真的跳到学校官网 + 无 console 报错
node tools/check-site.mjs "https://$DOMAIN_PUNY/" --expect "$TARGET"
```

第 5 步需要 playwright：

```bash
npm i -D playwright && npx playwright install chromium
```

全部通过才算完。**特别提醒**：curl 看第 1 步是 `200`，但浏览器里如果还是秒跳学校官网，
那说明还有**第 3 节没找全**的重定向在生效 —— 重定向规则优先于 Pages，回去继续查。

---

## 7. 回滚

```bash
# 把第 3.1 节备份的 JSON 原样 PUT 回去
jq '{rules: .rules}' /tmp/redirect-backup.json > /tmp/redirect-restore.json
curl -sS -X PUT "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/rulesets/phases/http_request_dynamic_redirect/entrypoint" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H "Content-Type: application/json" \
  --data @/tmp/redirect-restore.json | jq '.success'
```

万一备份丢了，一条等价的 301 长这样（把 `<TARGET>` 换成用户要跳的网址，
本仓库实例是 `https://www.huznu.edu.cn/`）：

```json
{
  "rules": [{
    "action": "redirect",
    "description": "redirect everything to the school site",
    "expression": "true",
    "action_parameters": {
      "from_value": {
        "status_code": 301,
        "target_url": { "value": "<TARGET>" },
        "preserve_query_string": false
      }
    }
  }]
}
```

---

## 8. 常见坑

| 症状 | 原因 | 处理 |
| --- | --- | --- |
| 控制台里找不到这个域名 | 中文域名在列表里显示为中文 | 搜 `$DOMAIN_PUNY` 的前几个字符，或直接翻列表 |
| 拆了 301 浏览器还是秒跳 | ① 还有别的重定向没拆 ② 浏览器缓存了 301 | 回到第 3 节逐项排查；用无痕/`curl` 复验 |
| zone 里翻遍了都没有 | 301 是 **Bulk Redirect（账号级）** 或 Worker 做的 | 第 3.2 / 3.4 节 |
| 绑域名报 DNS 记录冲突 | `@` 上有旧 A/AAAA | 备份后删掉再绑（第 5 节） |
| 页面出来了但样式/图片全 404 | 产物放进了子目录，或只传了 `site/*.html` | 必须把 `site/` **里的内容**传到站点根目录 |
| 分享卡片没图 | `og:image` 是绝对地址，由域名生成 | 改 `config.json` 的 `domain` 后重新生成 |
| wrangler 报 `Authentication error` | 没给 `CLOUDFLARE_ACCOUNT_ID` | 补上环境变量 |
| 想只改跳转目标 | 不用碰 Cloudflare | 改 `config.json` 的 `target_url`，跑 `tools/build-site.py --no-assets` 后重新部署 |

---

## 附：相关官方文档

- 单条重定向规则 API：<https://developers.cloudflare.com/rules/url-forwarding/single-redirects/create-api/>
- 批量重定向：<https://developers.cloudflare.com/rules/url-forwarding/bulk-redirects/create-api/>
- 页面规则：<https://developers.cloudflare.com/rules/page-rules/>
- Pages 自定义域名：<https://developers.cloudflare.com/pages/configuration/custom-domains/>
- Pages 命令行部署：<https://developers.cloudflare.com/pages/get-started/direct-upload/>
- Rulesets API：<https://developers.cloudflare.com/ruleset-engine/rulesets-api/>
