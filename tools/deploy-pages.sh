#!/usr/bin/env bash
# 把 site/ 传到 Cloudflare Pages，并按需绑定自定义域名。
# 只管部署；那条旧 301 得先按 docs/01-deploy-cloudflare.md 第 3 节拆掉，否则页面永远不显示。
#
#   CLOUDFLARE_API_TOKEN=xxx CLOUDFLARE_ACCOUNT_ID=yyy tools/deploy-pages.sh
#   BIND_DOMAIN=0 ... tools/deploy-pages.sh      # 只部署，不绑域名
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API=https://api.cloudflare.com/client/v4

: "${CLOUDFLARE_API_TOKEN:?请先 export CLOUDFLARE_API_TOKEN=...}"
: "${CLOUDFLARE_ACCOUNT_ID:?请先 export CLOUDFLARE_ACCOUNT_ID=...}"
command -v jq >/dev/null || { echo "需要 jq：brew install jq" >&2; exit 1; }

read_cfg() {
  python3 - "$ROOT" "$1" <<'PY'
import importlib.util, os, sys
root, key = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("ba", os.path.join(root, "tools", "build-assets.py"))
ba = importlib.util.module_from_spec(spec); spec.loader.exec_module(ba)
cfg = ba.load_config()
print(ba.punycode(cfg["domain"]) if key == "domain_ascii" else cfg[key])
PY
}

PROJECT="${PROJECT:-nailong-university}"
DOMAIN_ASCII="${DOMAIN_ASCII:-$(read_cfg domain_ascii)}"
SITE="$ROOT/site"

[ -f "$SITE/index.html" ] || { echo "找不到 $SITE/index.html，先跑 python3 tools/build-site.py" >&2; exit 1; }

echo "==> 项目 $PROJECT  域名 $DOMAIN_ASCII"
echo "==> 先确认线上不是还在 301"
curl -sSI --max-time 20 -A 'Mozilla/5.0' "https://$DOMAIN_ASCII/" | sed -n '1p;/^[Ll]ocation/p' | sed 's/^/    /' || true

echo "==> 建项目（已存在会报错，忽略）"
npx --yes wrangler@latest pages project create "$PROJECT" --production-branch=main || true

echo "==> 上传 site/"
npx --yes wrangler@latest pages deploy "$SITE" \
  --project-name "$PROJECT" --branch=main --commit-dirty=true

if [ "${BIND_DOMAIN:-1}" = "1" ]; then
  echo "==> 绑定自定义域名 $DOMAIN_ASCII（中文域名必须用 punycode）"
  curl -sS --max-time 30 -X POST \
    "$API/accounts/$CLOUDFLARE_ACCOUNT_ID/pages/projects/$PROJECT/domains" \
    -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H "Content-Type: application/json" \
    --data "{\"name\":\"$DOMAIN_ASCII\"}" | jq -r '"    ok=\(.success)  \(.result.name // "-")  \(.errors // [])"'
  echo "    报「记录已存在」的话：@ 上还有旧 A/AAAA，备份后删掉再重试（docs/01 第 5 节）"
fi

echo "==> 验收（证书可能要等 1~5 分钟）"
sleep 5
curl -sSI --max-time 20 -A 'Mozilla/5.0' "https://$DOMAIN_ASCII/" | sed -n '1p' | sed 's/^/    /'
echo "    期望 200；是 301 说明第 3 节的旧跳转还没拆干净"
