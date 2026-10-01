#!/usr/bin/env python3
"""Sync public/data-plane-chart-releases.json and
changelog/data-plane-chart.mdx against the data-plane Helm chart versions
published on oci://ghcr.io/popsink/charts/data-plane.

For each chart version: when it was pushed, and which component versions it
ships (data-plane image, broker image, Kotatsu image, Kora sub-chart). Versions
already in the JSON are reused as long as their manifest digest is unchanged,
so a daily run only downloads the charts pushed (or re-pushed) since.
"""
import io
import json
import os
import re
import sys
import tarfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# Must live under public/ - Mintlify does not serve static files placed in a
# folder that also contains .mdx pages, they 404 despite being on main.
JSON_PATH = REPO_ROOT / "public/data-plane-chart-releases.json"
MDX_PATH = REPO_ROOT / "changelog/data-plane-chart.mdx"
# Per-version release notes, written weekly by Popsink/data-plane's
# weekly_changelog.py - linked from the table when present.
NOTES_DIR = REPO_ROOT / "changelog/data-plane"

REGISTRY = "https://ghcr.io"
REPOSITORY = "popsink/charts/data-plane"
MANIFEST_MEDIA_TYPE = "application/vnd.oci.image.manifest.v1+json"
CHART_LAYER_MEDIA_TYPE = "application/vnd.cncf.helm.chart.content.v1.tar+gzip"
VERSION_RE = re.compile(r"^0\.1\.0-alpha\.(\d+)$")

# values.yaml key paths of the images the chart ships, in table column order.
IMAGE_PATHS = {
    "data_plane": ("image", "tag"),
    "broker": ("tansu", "image", "tag"),
    "kotatsu": ("kotatsu", "image", "tag"),
}

# MDX has no HTML-comment syntax - `<!--` is parsed as the start of a JSX tag
# and breaks the build. JSX-style comments are the only kind MDX tolerates.
TABLE_START = "{/* CHART_RELEASES_TABLE:START */}"
TABLE_END = "{/* CHART_RELEASES_TABLE:END */}"


def registry_token() -> str:
    # The chart is public: an anonymous pull token is all the API needs.
    url = f"{REGISTRY}/token?scope=repository:{REPOSITORY}:pull"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.load(resp)["token"]


def registry_get(token: str, path: str, accept: str | None = None, method: str = "GET"):
    req = urllib.request.Request(f"{REGISTRY}/v2/{REPOSITORY}/{path}", method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if accept:
        req.add_header("Accept", accept)
    return urllib.request.urlopen(req, timeout=60)


def list_versions(token: str) -> list[str]:
    tags, last = [], None
    while True:
        query = "n=1000" + (f"&last={last}" if last else "")
        with registry_get(token, f"tags/list?{query}") as resp:
            page = json.load(resp).get("tags") or []
        tags += page
        if len(page) < 1000:
            break
        last = page[-1]
    # Only 0.1.0-alpha.N is a published release line; anything else (a test
    # push, a digest-only tag) is not something a customer installs.
    return sorted((t for t in tags if VERSION_RE.match(t)), key=alpha_number)


def alpha_number(version: str) -> int:
    return int(VERSION_RE.match(version).group(1))


def manifest_digest(token: str, version: str) -> str:
    with registry_get(token, f"manifests/{version}", MANIFEST_MEDIA_TYPE, method="HEAD") as resp:
        return resp.headers["Docker-Content-Digest"]


def yaml_scalar(text: str, path: tuple[str, ...]) -> str | None:
    """Read one scalar out of values.yaml by its key path.

    Indentation-only, deliberately: the runner has no PyYAML, and the keys this
    script reads are plain `key: value` lines. Comments, blank lines and list
    items are skipped.
    """
    stack: list[tuple[int, str]] = []
    for line in text.splitlines():
        m = re.match(r"^(\s*)([A-Za-z0-9_.-]+):\s*(.*)$", line)
        if not m or line.lstrip().startswith("#"):
            continue
        indent, key, value = len(m.group(1)), m.group(2), m.group(3)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, key))
        if tuple(k for _, k in stack) == path:
            value = re.sub(r"\s+#.*$", "", value).strip().strip("\"'")
            return value or None
    return None


def fetch_release(token: str, version: str, digest: str) -> dict:
    with registry_get(token, f"manifests/{digest}", MANIFEST_MEDIA_TYPE) as resp:
        manifest = json.load(resp)
    layer = next(l for l in manifest["layers"] if l["mediaType"] == CHART_LAYER_MEDIA_TYPE)
    with registry_get(token, f"blobs/{layer['digest']}") as resp:
        archive = tarfile.open(fileobj=io.BytesIO(resp.read()), mode="r:gz")

    values = archive.extractfile("data-plane/values.yaml").read().decode()
    # The config blob is Chart.yaml as JSON, dependencies included.
    with registry_get(token, f"blobs/{manifest['config']['digest']}") as resp:
        chart = json.load(resp)
    kora = next((d for d in chart.get("dependencies") or [] if d.get("name") == "kora"), None)
    return {
        "version": version,
        "digest": digest,
        "published_at": manifest.get("annotations", {}).get("org.opencontainers.image.created"),
        **{name: yaml_scalar(values, path) for name, path in IMAGE_PATHS.items()},
        "kora": kora["version"] if kora else None,
    }


def load_existing() -> dict[str, dict]:
    if not JSON_PATH.exists():
        return {}
    with JSON_PATH.open() as f:
        return {r["version"]: r for r in json.load(f).get("releases", [])}


def render_cell(release: dict, previous: dict | None, key: str) -> str:
    value = release.get(key)
    if not value:
        return "—"
    # Bold what moved since the previous chart: the column an upgrader reads.
    # Plain text rather than code spans - bold does not show inside a code span.
    if previous is not None and previous.get(key) != value:
        return f"**{value}**"
    return value


def render_table(releases: list[dict]) -> str:
    header = (
        "| Chart | Published | Data plane | Broker (Tansu) | Kotatsu | Kora chart |\n"
        "| --- | --- | --- | --- | --- | --- |"
    )
    rows = []
    for i, release in enumerate(releases):
        previous = releases[i + 1] if i + 1 < len(releases) else None
        n = alpha_number(release["version"])
        chart = f"`{release['version']}`"
        if (NOTES_DIR / f"alpha-{n}.mdx").exists():
            chart = f"[{chart}](/changelog/data-plane/alpha-{n})"
        published = (release["published_at"] or "").split("T")[0] or "—"
        cells = [render_cell(release, previous, k) for k in (*IMAGE_PATHS, "kora")]
        rows.append(f"| {chart} | {published} | {' | '.join(cells)} |")
    return "\n".join([TABLE_START, header, *rows, TABLE_END])


def update_mdx(releases: list[dict]) -> bool:
    content = MDX_PATH.read_text()
    if TABLE_START not in content or TABLE_END not in content:
        sys.exit(f"::error::{MDX_PATH} is missing the {TABLE_START} / {TABLE_END} markers")
    pattern = re.compile(re.escape(TABLE_START) + r".*?" + re.escape(TABLE_END), re.DOTALL)
    new_content = pattern.sub(lambda _: render_table(releases), content, count=1)
    MDX_PATH.write_text(new_content)
    return new_content != content


def main() -> None:
    token = registry_token()
    versions = list_versions(token)
    if not versions:
        sys.exit(f"::error::No 0.1.0-alpha.N tag found on {REGISTRY}/{REPOSITORY} - aborting")

    existing = load_existing()
    with ThreadPoolExecutor(max_workers=8) as pool:
        digests = dict(zip(versions, pool.map(lambda v: manifest_digest(token, v), versions)))
        stale = [v for v in versions if existing.get(v, {}).get("digest") != digests[v]]
        fetched = {r["version"]: r for r in pool.map(lambda v: fetch_release(token, v, digests[v]), stale)}

    for version, release in fetched.items():
        if not release["data_plane"]:
            sys.exit(f"::error::No image.tag in the values.yaml of chart {version} - aborting")

    # Newest first, like the rest of the changelog.
    releases = [fetched.get(v) or existing[v] for v in reversed(versions)]
    json_changed = list(existing.values()) != releases
    # The MDX can change without the JSON: a release-notes page landing for a
    # version already listed turns its "—" into a link.
    mdx_changed = update_mdx(releases)

    github_output = os.environ.get("GITHUB_OUTPUT")
    if json_changed:
        updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload = {"updated_at": updated_at, "chart": f"oci://ghcr.io/{REPOSITORY}", "releases": releases}
        JSON_PATH.write_text(json.dumps(payload, indent=2) + "\n")

    changed = json_changed or mdx_changed
    print(
        f"{len(versions)} chart versions, {len(fetched)} fetched - "
        + ("files updated." if changed else "no change, skipping.")
    )
    if github_output:
        with open(github_output, "a") as fh:
            print(f"changed={'true' if changed else 'false'}", file=fh)


if __name__ == "__main__":
    main()
