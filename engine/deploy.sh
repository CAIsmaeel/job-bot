#!/usr/bin/env bash
# Puts the website (site/) plus the latest jobs page on Cloudflare Pages.
# Needs secrets CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID. Does nothing if they are missing.
set -e
if [ -z "$CLOUDFLARE_API_TOKEN" ] || [ -z "$CLOUDFLARE_ACCOUNT_ID" ]; then echo "deploy: skipped (no Cloudflare secrets)"; exit 0; fi
PROJECT="${PAGES_PROJECT:-finrehearse}"
rm -rf /tmp/deploy && cp -r site /tmp/deploy && mkdir -p /tmp/deploy/jobs
[ -f engine/out/site/index.html ] && cp engine/out/site/index.html /tmp/deploy/jobs/index.html
[ -d engine/out/seo ] && cp -r engine/out/seo/. /tmp/deploy/
npx --yes wrangler@3 pages project create "$PROJECT" --production-branch main >/dev/null 2>&1 || true
npx --yes wrangler@3 pages deploy /tmp/deploy --project-name "$PROJECT" --branch main --commit-dirty=true 2>&1 | tee /tmp/deploy.log | tail -5

# old address -> new address (one small redirect site on the old project)
mkdir -p /tmp/oldsite && printf '/* https://finrehearse.pages.dev/:splat 301\n' > /tmp/oldsite/_redirects && printf '<meta http-equiv="refresh" content="0;url=https://finrehearse.pages.dev/">' > /tmp/oldsite/index.html
npx --yes wrangler@3 pages deploy /tmp/oldsite --project-name ledgerlab --branch main --commit-dirty=true 2>&1 | tail -2 || true

# tell Bing / IndexNow about the pages (once a day, never fails the deploy)
python3 engine/indexnow.py || true
