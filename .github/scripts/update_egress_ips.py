#!/usr/bin/env python3
"""Sync public/egress-ips.json and deployment/connectivity/egress-ips.mdx
against the live AWS NAT Gateway / GCP Cloud NAT egress IPs. Fails loudly
instead of publishing a partial or empty list - this page is used for
customer firewall allowlists.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# Must live under public/ - Mintlify does not serve static files placed in a
# folder that also contains .mdx pages, they 404 despite being on main.
JSON_PATH = REPO_ROOT / "public/egress-ips.json"
MDX_PATH = REPO_ROOT / "deployment/connectivity/egress-ips.mdx"

GCP_PROJECT = "popsink-production-438615"
GCP_ROUTER_NAME_FILTER = "name~'^production-.*-router$'"

# Human-friendly location labels, hand-maintained - not derivable from the APIs.
LOCATIONS = {
    ("aws", "eu-west-3"): "France (Paris)",
    ("aws", "us-east-1"): "US (Northern Virginia)",
    ("gcp", "europe-west1"): "Belgium (St. Ghislain)",
    ("gcp", "europe-west9"): "France (Paris)",
    ("gcp", "us-east1"): "US (South Carolina)",
    ("gcp", "us-east4"): "US (Northern Virginia)",
    ("gcp", "us-east5"): "US (Columbus, Ohio)",
}

# MDX has no HTML-comment syntax - `<!--` is parsed as the start of a JSX tag
# and breaks the build. JSX-style comments are the only kind MDX tolerates.
TABLE_START = "{/* EGRESS_IPS_TABLE:START */}"
TABLE_END = "{/* EGRESS_IPS_TABLE:END */}"


def run_json(cmd: list[str]):
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def fetch_aws_addresses() -> list[dict]:
    regions = run_json(
        ["aws", "ec2", "describe-regions", "--query", "Regions[].RegionName", "--output", "json"]
    )
    addresses = []
    for region in regions:
        ips = run_json(
            [
                "aws", "ec2", "describe-nat-gateways",
                "--region", region,
                "--filter", "Name=state,Values=available",
                "--query", "NatGateways[].NatGatewayAddresses[].PublicIp",
                "--output", "json",
            ]
        )
        for ip in ips:
            addresses.append({"provider": "aws", "region": region, "ip": ip})
    return addresses


def fetch_gcp_addresses() -> list[dict]:
    """Read the IPs each Cloud NAT is actually using, rather than guessing from
    reserved address names - this is the real egress path, and survives renames
    and rotations of the underlying reserved addresses.
    """
    routers = run_json(
        [
            "gcloud", "compute", "routers", "list",
            "--project", GCP_PROJECT,
            "--filter", GCP_ROUTER_NAME_FILTER,
            "--format", "json",
        ]
    )
    addresses = []
    for router in routers:
        region = router["region"].rstrip("/").split("/")[-1]
        status = run_json(
            [
                "gcloud", "compute", "routers", "get-status", router["name"],
                "--region", region,
                "--project", GCP_PROJECT,
                "--format", "json",
            ]
        )
        for nat in status.get("result", {}).get("natStatus", []):
            ips = nat.get("userAllocatedNatIps", []) + nat.get("autoAllocatedNatIps", [])
            for ip in ips:
                addresses.append({"provider": "gcp", "region": region, "ip": ip})
    return addresses


def validate(addresses: list[dict]) -> None:
    if not addresses:
        sys.exit("::error::No egress IPs retrieved from either provider - aborting")

    providers = {a["provider"] for a in addresses}
    if providers != {"aws", "gcp"}:
        sys.exit(f"::error::Expected addresses from both aws and gcp, got: {sorted(providers)} - aborting")

    for addr in addresses:
        key = (addr["provider"], addr["region"])
        if key not in LOCATIONS:
            sys.exit(
                f"::error::No location label for {addr['provider']}/{addr['region']} "
                f"- add it to LOCATIONS in this script before it can be published"
            )


def group_by_region(addresses: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for a in addresses:
        grouped.setdefault((a["provider"], a["region"]), []).append(a["ip"])
    return [
        {"provider": provider, "region": region, "location": LOCATIONS[(provider, region)], "ips": sorted(ips)}
        for (provider, region), ips in sorted(grouped.items())
    ]


def load_existing_regions() -> list[dict] | None:
    if not JSON_PATH.exists():
        return None
    with JSON_PATH.open() as f:
        return json.load(f).get("regions")


def render_table(regions: list[dict], updated_at: str) -> str:
    header = "| Provider | Region | Location | Egress IPs |\n| --- | --- | --- | --- |"
    rows = [
        f"| {r['provider'].upper()} | `{r['region']}` | {r['location']} | "
        + "<br />".join(f"`{ip}`" for ip in r["ips"])
        + " |"
        for r in regions
    ]
    date = updated_at.split("T")[0]
    return "\n".join([TABLE_START, header, *rows, "", f"*Last updated: {date}*", TABLE_END])


def update_mdx(regions: list[dict], updated_at: str) -> None:
    content = MDX_PATH.read_text()
    if TABLE_START not in content or TABLE_END not in content:
        sys.exit(f"::error::{MDX_PATH} is missing the {TABLE_START} / {TABLE_END} markers")
    pattern = re.compile(re.escape(TABLE_START) + r".*?" + re.escape(TABLE_END), re.DOTALL)
    new_content = pattern.sub(render_table(regions, updated_at), content, count=1)
    MDX_PATH.write_text(new_content)


def main() -> None:
    addresses = fetch_aws_addresses() + fetch_gcp_addresses()
    validate(addresses)
    regions = group_by_region(addresses)

    existing = load_existing_regions()
    changed = existing != regions

    github_output = os.environ.get("GITHUB_OUTPUT")
    if not changed:
        print("No change in the published egress IP list - skipping.")
        if github_output:
            with open(github_output, "a") as fh:
                print("changed=false", file=fh)
        return

    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {"updated_at": updated_at, "regions": regions}

    JSON_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    update_mdx(regions, updated_at)

    print(f"Egress IP list changed ({len(addresses)} addresses in {len(regions)} regions) - files updated.")
    if github_output:
        with open(github_output, "a") as fh:
            print("changed=true", file=fh)


if __name__ == "__main__":
    main()
