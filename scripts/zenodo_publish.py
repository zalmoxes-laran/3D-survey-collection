#!/usr/bin/env python3
"""Publish a new version of 3D Survey Collection to Zenodo via the deposit API.

Runs in CI for STABLE tags only (the release.yml `zenodo` job). It archives the
source archive of the tag as a new version under the existing concept DOI,
bypassing the GitHub->Zenodo webhook.

Design / robustness:
  * Idempotent: if the concept already has a version equal to TAG, exit 0.
  * Non-blocking: standalone job, so if it fails the GitHub Release and its
    download links are unaffected -- just archive that stable manually.
  * Uses the deposit API (which returns real error messages), not the webhook.
  * If ZENODO_TOKEN is empty/missing it SKIPS (exit 0) instead of failing, so
    tagging a stable before the secret is configured won't break the build.

Env:
  ZENODO_TOKEN    Zenodo personal token (scopes: deposit:write, deposit:actions)
  ZENODO_CONCEPT  concept record id (numeric) for 3D Survey Collection
  TAG             the git tag, e.g. v1.7.0
  SRC_ZIP         path to the source archive to upload
Reads .zenodo.json (repo root) for the deposition metadata.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://zenodo.org/api"
TOKEN = os.environ.get("ZENODO_TOKEN", "").strip()
CONCEPT = os.environ.get("ZENODO_CONCEPT", "").strip()
TAG = os.environ.get("TAG", "").strip()
SRC_ZIP = os.environ.get("SRC_ZIP", "").strip()

if not TOKEN:
    print("ZENODO_TOKEN not set -> skipping Zenodo archival "
          "(configure the repo secret to enable it).")
    sys.exit(0)
for _name, _val in (("ZENODO_CONCEPT", CONCEPT), ("TAG", TAG), ("SRC_ZIP", SRC_ZIP)):
    if not _val:
        print(f"ERROR: {_name} not set", file=sys.stderr)
        sys.exit(1)


def api(method, url, data=None, ctype=None):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    if ctype:
        headers["Content-Type"] = ctype
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            return exc.code, json.loads(body or b"{}")
        except Exception:
            return exc.code, {"_raw": body.decode("utf-8", "replace")}


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


# 1. Resolve concept -> latest record; idempotency check.
st, rec = api("GET", f"{API}/records/{CONCEPT}")
if st != 200:
    die(f"cannot resolve concept {CONCEPT}: HTTP {st} {rec}")
latest_id = rec["id"]
st, vers = api("GET", f"{API}/records/{latest_id}/versions?size=200&allversions=true")
have = {v.get("metadata", {}).get("version")
        for v in vers.get("hits", {}).get("hits", [])}
if TAG in have:
    print(f"Version {TAG} already archived on concept {CONCEPT} -> nothing to do.")
    sys.exit(0)

# 2. Metadata from .zenodo.json.
with open(".zenodo.json", encoding="utf-8") as fh:
    meta = json.load(fh)
meta["version"] = TAG

# 3. Create a new-version draft from the latest deposition.
st, nv = api("POST", f"{API}/deposit/depositions/{latest_id}/actions/newversion")
if st not in (200, 201):
    die(f"newversion failed: HTTP {st} {nv}")
draft_url = nv.get("links", {}).get("latest_draft")
if not draft_url:
    die(f"no latest_draft link returned: {nv}")
st, draft = api("GET", draft_url)
if st != 200:
    die(f"get draft failed: HTTP {st} {draft}")
draft_id = draft["id"]
bucket = draft["links"]["bucket"]

# 4. Set metadata.
st, up = api("PUT", f"{API}/deposit/depositions/{draft_id}",
             data=json.dumps({"metadata": meta}).encode("utf-8"),
             ctype="application/json")
if st != 200:
    die(f"metadata update failed: HTTP {st} {up}")

# 5. Drop inherited files (the previous version's source archive).
for f in draft.get("files", []):
    api("DELETE", f"{API}/deposit/depositions/{draft_id}/files/{f.get('id')}")

# 6. Upload the new source archive to the draft's bucket.
fname = os.path.basename(SRC_ZIP)
with open(SRC_ZIP, "rb") as fh:
    blob = fh.read()
st, _ = api("PUT", f"{bucket}/{urllib.parse.quote(fname)}",
            data=blob, ctype="application/octet-stream")
if st not in (200, 201):
    die(f"file upload failed for {fname}: HTTP {st}")
print(f"Uploaded {fname} ({len(blob)} bytes)")

# 7. Publish.
st, pub = api("POST", f"{API}/deposit/depositions/{draft_id}/actions/publish")
if st not in (200, 202):
    die(f"publish failed: HTTP {st} {pub}")
print("Published new version:", pub.get("doi") or pub.get("doi_url") or draft_id)
