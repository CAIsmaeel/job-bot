"""Tells Bing (and other IndexNow search engines) about every page in the sitemap.
Runs after a deploy. Sends at most once a day: only when the UTC hour is 2 or 3,
or when FORCE_INDEXNOW=1 (the site workflow sets this). Never fails the deploy."""
import os, re, json, sys, datetime, urllib.request
KEY = "f7845e75c758b05791ba71e8a5d57258"
HOST = "finrehearse.pages.dev"
def main():
    if os.environ.get("FORCE_INDEXNOW") != "1" and datetime.datetime.utcnow().hour not in (2, 3):
        print("indexnow: not this hour"); return
    p = "/tmp/deploy/sitemap.xml"
    if not os.path.exists(p):
        print("indexnow: no sitemap"); return
    urls = re.findall(r"<loc>([^<]+)</loc>", open(p).read())
    body = json.dumps({"host": HOST, "key": KEY, "keyLocation": f"https://{HOST}/{KEY}.txt", "urlList": urls[:10000]}).encode()
    req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body, headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print("indexnow:", r.status, len(urls), "urls")
    except Exception as e:
        print("indexnow: failed", e)
if __name__ == "__main__":
    try: main()
    except Exception as e: print("indexnow: error", e)
    sys.exit(0)
