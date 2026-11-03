#!/usr/bin/env python3
"""
CloudStream Master Repository Merger
=====================================
Fetches CloudStream extension repositories, aggregates all plugins,
resolves duplicates by highest version number, and generates a valid
unified master.json / repo.json / plugins.json for CloudStream 3 & 4.
Zero external dependencies required (uses standard library urllib).
"""

import os
import sys
import json
import ssl
import time
import argparse
from typing import List, Dict, Any, Tuple
import urllib.request
import urllib.error

# 11 Source Repositories provided by user
DEFAULT_REPOSITORIES = [
    {
        "name": "CSX (Megix)",
        "url": "https://raw.githubusercontent.com/SaurabhKaperwan/CSX/builds/CS.json"
    },
    {
        "name": "Phisher Repo",
        "url": "https://raw.githubusercontent.com/phisher98/cloudstream-extensions-phisher/refs/heads/builds/repo.json"
    },
    {
        "name": "CNC Repo (All Language)",
        "url": "https://raw.githubusercontent.com/NivinCNC/CNCVerse-Cloud-Stream-Extension/refs/heads/builds/CNC.json"
    },
    {
        "name": "Cinephile",
        "url": "https://raw.githubusercontent.com/rockhero1234/cinephile/refs/heads/builds/repo.json"
    },
    {
        "name": "Raghav Repo",
        "url": "https://raw.githubusercontent.com/KSHITIJ8473/raghav/builds/repo.json"
    },
    {
        "name": "AllForU",
        "url": "https://raw.githubusercontent.com/RVRBEAST76/allforu-repo/builds/repo.json"
    },
    {
        "name": "FLUMMOX Repo",
        "url": "https://raw.githubusercontent.com/FlummoxGamer/FLUMMOX-Repo/builds/repo.json"
    },
    {
        "name": "Desi Extensions",
        "url": "https://raw.githubusercontent.com/Faisal0786/Desi/main/repo.json"
    },
    {
        "name": "NetMirror",
        "url": "https://raw.githubusercontent.com/Sushan64/NetMirror-Extension/refs/heads/builds/Netflix.json"
    },
    {
        "name": "Xtron Repo",
        "url": "https://raw.githubusercontent.com/MrXtron/CloudStream-Extension/refs/heads/builds/repo.json"
    },
    {
        "name": "Eclipsia",
        "url": "https://cs.eclipsia.dpdns.org/repo.json"
    }
]

# SSL Context for HTTPS requests
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "CloudStream/4.0 (GitHubActions-UnifiedRepoMerger)",
    "Accept": "application/json, text/plain, */*"
}

def fetch_json(url: str, timeout: int = 15, retries: int = 2) -> Any:
    """Fetch JSON from a URL with retry logic and timeout."""
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
                raw_bytes = resp.read()
                return json.loads(raw_bytes.decode('utf-8'))
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise last_err

def parse_int_version(val: Any) -> int:
    """Safely parse version integer."""
    if isinstance(val, int):
        return val
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return 0

def merge_repositories(
    repos: List[Dict[str, str]],
    repo_name: str,
    repo_desc: str,
    repo_icon: str,
    raw_base_url: str
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
    """
    Fetches all repositories and sub-pluginLists,
    deduplicates by internalName keeping highest version,
    and constructs standard CloudStream repository objects.
    """
    raw_plugins = []
    source_stats = []

    print(f"[*] Starting aggregation across {len(repos)} repositories...")

    for repo in repos:
        name = repo.get("name", "Unknown Repo")
        url = repo.get("url", "")
        print(f"\n[+] Fetching repository: {name}")
        print(f"    URL: {url}")

        try:
            repo_meta = fetch_json(url)
            plugin_urls = []

            if isinstance(repo_meta, list):
                # Repo directly provides a list of plugins
                print(f"    -> Direct list format: {len(repo_meta)} plugins found")
                for p in repo_meta:
                    p["_source_repo"] = name
                    raw_plugins.append(p)
                source_stats.append({
                    "name": name,
                    "url": url,
                    "status": "success",
                    "plugins_count": len(repo_meta)
                })
                continue

            elif isinstance(repo_meta, dict):
                # Standard CloudStream repo with pluginLists
                pl = repo_meta.get("pluginLists", [])
                if isinstance(pl, list) and pl:
                    plugin_urls = pl
                elif "plugins" in repo_meta and isinstance(repo_meta["plugins"], list):
                    for p in repo_meta["plugins"]:
                        p["_source_repo"] = name
                        raw_plugins.append(p)
                    source_stats.append({
                        "name": name,
                        "url": url,
                        "status": "success",
                        "plugins_count": len(repo_meta["plugins"])
                    })
                    continue

            found_count = 0
            for p_url in plugin_urls:
                try:
                    p_data = fetch_json(p_url)
                    if isinstance(p_data, list):
                        print(f"    -> Fetched sub-list ({p_url.split('/')[-1]}): {len(p_data)} plugins")
                        found_count += len(p_data)
                        for p in p_data:
                            p["_source_repo"] = name
                            raw_plugins.append(p)
                    else:
                        print(f"    [!] Sub-list returned non-array: {p_url}")
                except Exception as sub_err:
                    print(f"    [!] Failed sub-list {p_url}: {sub_err}")

            source_stats.append({
                "name": name,
                "url": url,
                "status": "success",
                "plugins_count": found_count
            })

        except Exception as err:
            print(f"    [-] FAILED to fetch repo {name}: {err}")
            source_stats.append({
                "name": name,
                "url": url,
                "status": "failed",
                "error": str(err),
                "plugins_count": 0
            })

    print(f"\n[*] Total plugins gathered (with duplicates): {len(raw_plugins)}")

    # Deduplicate by internalName / identifier
    by_identifier: Dict[str, List[Dict[str, Any]]] = {}
    for p in raw_plugins:
        key = (p.get("internalName") or p.get("name") or "").strip().lower()
        if not key:
            continue
        if key not in by_identifier:
            by_identifier[key] = []
        by_identifier[key].append(p)

    merged_plugins = []
    conflict_log = []

    for key, candidates in by_identifier.items():
        if len(candidates) == 1:
            chosen = dict(candidates[0])
            source = chosen.pop("_source_repo", None)
            chosen["repositoryName"] = source or chosen.get("repositoryName", "")
            merged_plugins.append(chosen)
        else:
            # Sort by version descending (highest version number wins)
            candidates.sort(key=lambda x: parse_int_version(x.get("version", 0)), reverse=True)
            chosen = dict(candidates[0])
            source = chosen.pop("_source_repo", None)
            chosen["repositoryName"] = source or chosen.get("repositoryName", "")
            merged_plugins.append(chosen)

            # Record conflict for logging
            conflict_log.append({
                "plugin": chosen.get("name") or key,
                "winner": {
                    "source": source,
                    "version": parse_int_version(chosen.get("version", 0))
                },
                "superseded": [
                    {
                        "source": c.get("_source_repo"),
                        "version": parse_int_version(c.get("version", 0))
                    }
                    for c in candidates[1:]
                ]
            })

    # Sort merged plugins alphabetically by name
    merged_plugins.sort(key=lambda x: (x.get("name") or "").lower())

    print(f"[*] Deduplicated to {len(merged_plugins)} unique plugins.")
    print(f"[*] Resolved {len(conflict_log)} duplicate conflicts.")

    # Manifest pointing to plugins.json
    plugins_target_url = f"{raw_base_url.rstrip('/')}/plugins.json" if raw_base_url else "plugins.json"
    repo_manifest = {
        "name": repo_name,
        "description": f"{repo_desc} ({len(merged_plugins)} extensions from {len(repos)} repositories)",
        "manifestVersion": 2,
        "iconUrl": repo_icon,
        "pluginLists": [
            plugins_target_url
        ]
    }

    # Combined master.json (CloudStream accepts both manifest format with pluginLists and plugins array)
    master_json_format = {
        "name": repo_name,
        "description": f"{repo_desc} ({len(merged_plugins)} extensions from {len(repos)} repositories)",
        "manifestVersion": 2,
        "iconUrl": repo_icon,
        "pluginLists": [
            plugins_target_url
        ],
        "plugins": merged_plugins
    }

    report = {
        "total_sources": len(repos),
        "successful_sources": len([s for s in source_stats if s["status"] == "success"]),
        "failed_sources": len([s for s in source_stats if s["status"] == "failed"]),
        "raw_plugins": len(raw_plugins),
        "unique_plugins": len(merged_plugins),
        "duplicates_resolved": len(conflict_log),
        "source_stats": source_stats,
        "conflict_log": conflict_log
    }

    return repo_manifest, merged_plugins, master_json_format, report

def write_step_summary(report: Dict[str, Any]):
    """Output summary table to GITHUB_STEP_SUMMARY if running inside GitHub Actions."""
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_file:
        return

    try:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write("## 🚀 CloudStream Master Repository Build Summary\n\n")
            f.write(f"- **Unique Plugins Available**: `{report['unique_plugins']}`\n")
            f.write(f"- **Total Raw Extensions Scanned**: `{report['raw_plugins']}`\n")
            f.write(f"- **Duplicate Versions Resolved**: `{report['duplicates_resolved']}`\n")
            f.write(f"- **Active Source Repositories**: `{report['successful_sources']}/{report['total_sources']}`\n\n")

            f.write("### 📦 Source Repositories\n\n")
            f.write("| Repository | Status | Plugins Fetched |\n")
            f.write("| :--- | :---: | :---: |\n")
            for s in report.get("source_stats", []):
                icon = "✅" if s["status"] == "success" else "❌"
                f.write(f"| {s['name']} | {icon} {s['status'].upper()} | {s.get('plugins_count', 0)} |\n")
            f.write("\n")

            if report.get("conflict_log"):
                f.write("### ⚡ Resolved Duplicate Conflicts (Top 10)\n\n")
                f.write("| Extension | Selected (Highest Ver) | Superseded Repos |\n")
                f.write("| :--- | :--- | :--- |\n")
                for c in report["conflict_log"][:10]:
                    w = f"**{c['winner']['source']}** (v{c['winner']['version']})"
                    superseded = ", ".join([f"{s['source']} (v{s['version']})" for s in c["superseded"]])
                    f.write(f"| {c['plugin']} | {w} | {superseded} |\n")
                f.write("\n")
    except Exception as e:
        print(f"[!] Could not write to GITHUB_STEP_SUMMARY: {e}")

def main():
    parser = argparse.ArgumentParser(description="Merge multiple CloudStream extension repositories into master.json")
    parser.add_argument("--repo-name", default="Master CloudStream Unified Repo", help="Name of unified repository")
    parser.add_argument("--repo-desc", default="Unified multi-source CloudStream repository", help="Description")
    parser.add_argument("--repo-icon", default="https://raw.githubusercontent.com/LagradOst/CloudStream-3/master/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png", help="Icon URL")
    parser.add_argument("--raw-base-url", default="", help="Base raw GitHub URL (e.g., https://raw.githubusercontent.com/USER/REPO/main)")
    parser.add_argument("--output-dir", default=".", help="Directory to save generated JSON files")
    parser.add_argument("--custom-sources-file", default=None, help="Optional JSON file with custom repository list")

    args = parser.parse_args()

    # Determine raw_base_url automatically if running in GitHub Actions
    raw_base_url = args.raw_base_url
    if not raw_base_url and os.environ.get("GITHUB_REPOSITORY"):
        gh_repo = os.environ.get("GITHUB_REPOSITORY")
        gh_ref = os.environ.get("GITHUB_REF_NAME", "main")
        raw_base_url = f"https://raw.githubusercontent.com/{gh_repo}/{gh_ref}"
        print(f"[*] Detected GitHub Actions environment: {raw_base_url}")

    repos = DEFAULT_REPOSITORIES
    if args.custom_sources_file and os.path.isfile(args.custom_sources_file):
        with open(args.custom_sources_file, "r", encoding="utf-8") as f:
            repos = json.load(f)
            print(f"[*] Loaded {len(repos)} repositories from {args.custom_sources_file}")

    repo_manifest, plugins_list, master_json, report = merge_repositories(
        repos=repos,
        repo_name=args.repo_name,
        repo_desc=args.repo_desc,
        repo_icon=args.repo_icon,
        raw_base_url=raw_base_url
    )

    out_dir = args.output_dir
    os.makedirs(out_dir, exist_ok=True)

    # 1. repo.json (Manifest pointing to plugins.json)
    repo_file = os.path.join(out_dir, "repo.json")
    with open(repo_file, "w", encoding="utf-8") as f:
        json.dump(repo_manifest, f, indent=2, ensure_ascii=False)
    print(f"[✓] Saved manifest: {repo_file}")

    # 2. plugins.json (List of all deduplicated plugins)
    plugins_file = os.path.join(out_dir, "plugins.json")
    with open(plugins_file, "w", encoding="utf-8") as f:
        json.dump(plugins_list, f, indent=2, ensure_ascii=False)
    print(f"[✓] Saved plugin array: {plugins_file}")

    # 3. master.json (Direct plugins array AND compatible format for direct URL usage)
    master_file = os.path.join(out_dir, "master.json")
    with open(master_file, "w", encoding="utf-8") as f:
        json.dump(master_json, f, indent=2, ensure_ascii=False)
    print(f"[✓] Saved master file: {master_file}")

    # Write GitHub Actions step summary if available
    write_step_summary(report)

    print("\n🎉 CloudStream Master Repository successfully generated!")
    print(f"   Total Unique Plugins: {len(plugins_list)}")
    print(f"   Add to CloudStream: {raw_base_url + '/repo.json' if raw_base_url else 'https://raw.githubusercontent.com/<YOUR_USER>/<YOUR_REPO>/main/repo.json'}")

if __name__ == "__main__":
    main()
