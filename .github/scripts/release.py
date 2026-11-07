#!/usr/bin/env python3
"""release.json and the release notes for <repo>-<tag>.

    release.py json <dir>             release.json for the files in <dir>, from the environment:
                                      REPO TAG COMMIT TAG_OBJECT OBJECT_FORMAT SOURCE_BASE RUN_URL
                                      ATTESTATION_URL GITHUB_WORKFLOW_REF
    release.py notes <release.json>   the notes (Markdown); NOTES = the changelog section or tag
                                      message, SIGNER = "<principal> <key type> <fingerprint>",
                                      GITHUB_REPOSITORY = this repo

The notes come from release.json alone (plus NOTES and SIGNER), so published releases can be
re-rendered from their own release.json.
"""

import hashlib
import json
import os
import sys
from pathlib import Path

TARGETS = {"x86_64-unknown-linux-gnu": "x86_64 Linux", "aarch64-unknown-linux-gnu": "aarch64 Linux"}


def release_json(out: Path) -> str:
    e = os.environ
    assets = [
        {"name": p.name, "size": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in sorted(out.iterdir())
    ]
    return json.dumps(
        {
            "repo": e["REPO"],
            "tag": e["TAG"],
            "source": f"{e['SOURCE_BASE']}/{e['REPO']}",
            "commit": e["COMMIT"],
            "tag_object": e["TAG_OBJECT"],
            "object_format": e["OBJECT_FORMAT"],
            "workflow": e["GITHUB_WORKFLOW_REF"],
            "run": e["RUN_URL"],
            "attestation": e["ATTESTATION_URL"],
            "assets": assets,
        },
        indent=2,
    )


def size(n: int) -> str:
    for unit in ("B", "KiB", "MiB"):
        if n < 1024 or unit == "MiB":
            return f"{n} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    raise AssertionError


def install(kind: str, assets: list[dict], url) -> list[str]:
    """Shell lines for the files a workflow's default build makes; none for custom .release output."""
    if kind == "bun":
        return [f"bun add {url(a)}" for a in assets if a["name"].endswith(".tgz")]
    if kind == "uv":
        return [f"uv pip install {url(a)}" for a in assets if a["name"].endswith(".whl")]
    if kind == "rust":
        lines = []
        for target, platform in TARGETS.items():
            for a in assets:
                if a["name"].endswith(f"-{target}.tar.gz"):
                    lines += [f"# {platform}", f"curl -fsSL {url(a)} | tar -xz"]
        return lines
    return []


def notes(release: dict) -> str:
    e = os.environ
    repo, tag, source = release["repo"], release["tag"], release["source"]
    version = tag.removeprefix("v")
    builder = e["GITHUB_REPOSITORY"]
    assets = release["assets"]
    kind = Path(release["workflow"].split("@")[0]).stem

    def url(a: dict) -> str:
        return f"https://github.com/{builder}/releases/download/{repo}-{tag}/{a['name']}"

    out = []
    text = e.get("NOTES", "").strip()
    # A tag message that only repeats the name and version says nothing.
    if text and text not in {f"{repo} {version}", f"{repo} {tag}", tag, version}:
        out += [text, ""]

    if lines := install(kind, assets, url):
        out += ["## Install", "", "```sh", *lines, "```", ""]

    out += ["## Downloads", "", "| File | Size |", "|---|--:|"]
    out += [f"| [{a['name']}]({url(a)}) | {size(a['size'])} |" for a in assets]
    out += ["", "<details><summary>SHA-256</summary>", "", "```"]
    out += [f"{a['sha256']}  {a['name']}" for a in assets]
    out += ["```", "", "</details>", ""]

    commit = release["commit"]
    fmt = release.get("object_format", "sha1").upper().replace("SHA", "SHA-")
    # The verify example names a real file: x86_64 if there is one, else the first.
    example = next((a["name"] for a in assets if "x86_64" in a["name"]), assets[0]["name"])
    out += ["## Provenance", ""]
    out.append(
        f"- Source: tag [`{tag}`]({source}/tag/?h={tag}) of [{source.split('://')[-1]}]({source}),"
        f" commit [`{commit[:12]}`]({source}/commit/?id={commit}) ({fmt})"
    )
    if signer := e.get("SIGNER", "").split():
        principal, *key, fingerprint = signer
        out.append(
            f"- Tag signed by `{principal}` ({' '.join(key)} `{fingerprint}`), checked against"
            f" [`allowed_signers`](https://github.com/{builder}/blob/main/allowed_signers)"
        )
    run = release["run"]
    out.append(f"- Built from a clean runner by `{kind}.yml`, [run {run.rsplit('/', 1)[-1]}]({run})")
    out.append(f"- [Build provenance attestation]({release['attestation']}) (Sigstore). Verify a download:")
    out += ["", "  ```sh", f"  gh attestation verify {example} --repo {builder}", "  ```"]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    match sys.argv[1:]:
        case ["json", out]:
            print(release_json(Path(out)))
        case ["notes", path]:
            sys.stdout.write(notes(json.loads(Path(path).read_text())))
        case _:
            sys.exit(__doc__)
