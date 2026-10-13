#!/usr/bin/env bash
# 摸清一个域名的 Cloudflare 现状 —— 「域名级 301」一共可能藏在 4 个地方，这里一次列全。
# 只读，不会改任何东西。排查完再去 docs/01-deploy-cloudflare.md 里删。
#
#   CLOUDFLARE_API_TOKEN=xxx tools/cf-inspect.sh 中国奶龙大学.org
#   CLOUDFLARE_API_TOKEN=xxx tools/cf-inspect.sh xn--fiqs8srwb9iv6f6w9n.org
set -uo pipefail

API=https://api.cloudflare.com/client/v4
DOMAIN="${1:-}"

if ! command -v jq >/dev/null; then echo "需要 jq：brew install jq" >&2; exit 1; fi
if [ -z "${CLOUDFLARE_API_TOKEN:-}" ]; then
  echo "请先 export CLOUDFLARE_API_TOKEN=...   （权限见 docs/01 第 2 节）" >&2; exit 1
fi
if [ -z "$DOMAIN" ]; then echo "用法：tools/cf-inspect.sh <域名>" >&2; exit 1; fi

# 中文域名转 punycode
ASCII=$(python3 -c "import sys; print(sys.argv[1].encode('idna').decode())" "$DOMAIN" 2>/dev/null || echo "$DOMAIN")

say() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
hdr=(-H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}")
get() { curl -sS --max-time 25 "${hdr[@]}" "$API$1"; }

say "0. 域名"
echo "输入:   $DOMAIN"
echo "punycode: $ASCII"

say "1. Token 是否有效"
get /user/tokens/verify | jq -r '"  status: \(.result.status // "-")   errors: \(.errors // [])"'

say "2. 线上实际行为（这一步不需要 token）"
curl -sSI --max-time 20 -A 'Mozilla/5.0' "https://$ASCII/" \
  | sed -n '1p;/^[Ll]ocation/p;/^[Ss]erver/p' | sed 's/^/  /'

say "3. zone_id"
ZONE_JSON=$(get "/zones?name=$ASCII")
ZONE_ID=$(echo "$ZONE_JSON" | jq -r '.result[0].id // empty')
if [ -z "$ZONE_ID" ]; then
  echo "  拿不到 zone_id —— token 缺 Zone:Read，或域名不在该账号下"
  echo "$ZONE_JSON" | jq -c '.errors' | sed 's/^/  /'
  exit 1
fi
echo "  ZONE_ID=$ZONE_ID"

say "4. account（批量重定向是账号级的，需要 account_id）"
ACCOUNTS=$(get "/accounts")
echo "$ACCOUNTS" | jq -r '.result[] | "  \(.id)  \(.name)"'
ACCOUNT_ID=$(echo "$ACCOUNTS" | jq -r '.result[0].id // empty')

say "5. DNS 记录（排除「DNS 直接指到学校」）"
get "/zones/$ZONE_ID/dns_records?per_page=100" \
  | jq -r '.result[] | "  \(.type)\t\(.name)\t\(.content)\tproxied=\(.proxied)"'
echo "  ↑ @ 上若是 Cloudflare 的 104.x / 172.67.x 且 proxied=true，说明内容由后面的规则决定"

say "6. 重定向规则 Single Redirects（zone 级，最常见）★"
get "/zones/$ZONE_ID/rulesets" \
  | jq -r '.result[] | "  phase=\(.phase)\truleset=\(.id)\t\(.name)"'
echo "  --- http_request_dynamic_redirect 入口 ---"
get "/zones/$ZONE_ID/rulesets/phases/http_request_dynamic_redirect/entrypoint" \
  | jq '.result // "（没有这个 phase 的 ruleset，说明没用单条重定向规则）"'

say "7. 页面规则 Page Rules（老功能，仍然有效）"
get "/zones/$ZONE_ID/pagerules" \
  | jq -r '.result[] | "  \(.id)\t\(.targets|tostring)\t\(.actions|tostring)"' || true
echo "  （没输出 = 没有页面规则）"

say "8. 批量重定向 Bulk Redirects（★ 账号级，在 zone 里找不到）"
if [ -n "$ACCOUNT_ID" ]; then
  get "/accounts/$ACCOUNT_ID/rulesets" \
    | jq -r '.result[] | select(.phase=="http_request_redirect") | "  phase=\(.phase)\truleset=\(.id)\t\(.name)"'
  echo "  --- URL 列表 ---"
  get "/accounts/$ACCOUNT_ID/rules/lists" \
    | jq -r '.result[] | "  \(.id)\t\(.name)\t\(.num_items) 条"' || true
else
  echo "  没有 account_id，跳过"
fi

say "9. Worker 路由"
get "/zones/$ZONE_ID/workers/routes" \
  | jq -r '.result[] | "  \(.pattern)\t-> \(.script // "-")"' || true
echo "  （没输出 = 没有 worker 路由）"

cat <<'TIP'

──────────────────────────────────────────────────────────────
结论怎么读：
  · 第 6 节出现 action=redirect 且目标是我们学校官网 → 就是它，按 docs/01 第 3.1 节删
  · 第 7 节出现 forwarding_url                        → docs/01 第 3.3 节
  · 第 8 节有 http_request_redirect 或 URL 列表       → docs/01 第 3.2 节（账号级！）
  · 第 9 节有命中该域名的路由                          → docs/01 第 3.4 节
动手删之前，先把对应那段 JSON 存一份，回滚要用。
──────────────────────────────────────────────────────────────
TIP
