#!/usr/bin/env python3
"""Collect artifacts, build release.json and render release notes for <repo>-<tag>.

    release.py collect <raw> <out>    validate out-* artifact dirs in <raw>, forbid duplicate
                                      names and move the files into <out>
    release.py json <dir>             release.json for the files in <dir>, from the environment:
                                      REPO TAG COMMIT TAG_OBJECT OBJECT_FORMAT SIGNER SOURCE_BASE
                                      RUN_URL ATTESTATION_URL GITHUB_SHA GITHUB_WORKFLOW_REF
    release.py notes <release.json>   the notes (Markdown); NOTES = the changelog section or tag
                                      message, GITHUB_REPOSITORY = this repo

The notes come from release.json alone (plus NOTES), so published releases can be re-rendered
from their own release.json.
"""

import hashlib
import json
import os
import re
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")


def sha256(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def collect(raw: Path, out: Path) -> None:
    if not raw.is_dir():
        sys.exit(f"::error::{raw}: no release artifacts found")
    entries = sorted(raw.iterdir())
    if not entries:
        sys.exit("::error::no release artifacts found")
    out.mkdir(parents=True, exist_ok=True)
    # download-artifact extracts a single matching artifact directly into `raw`, and creates one
    # subdirectory per artifact when multiple match.
    if all(p.is_dir() and not p.is_symlink() for p in entries):
        buckets = [(b.name, sorted(b.iterdir())) for b in entries]
    elif all(p.is_file() and not p.is_symlink() for p in entries):
        buckets = [(raw.name, entries)]
    else:
        bad = next(p for p in entries if p.is_symlink() or not p.is_dir())
        sys.exit(f"::error::unexpected entry '{bad.name}' in downloaded artifacts")
    seen: dict[str, str] = {}
    for name, files in buckets:
        for p in files:
            if p.is_symlink() or not p.is_file():
                sys.exit(f"::error::{name}/{p.name}: only regular files are allowed")
            if not NAME_RE.match(p.name) or p.name == "release.json":
                sys.exit(f"::error::bad file name '{p.name}' in {name}")
            if p.name in seen:
                sys.exit(f"::error::duplicate artifact file '{p.name}' (in {seen[p.name]} and {name})")
            seen[p.name] = name
            p.rename(out / p.name)
    if not seen:
        sys.exit("::error::no release artifacts found")


def release_json(out: Path) -> str:
    e = os.environ
    files = sorted(out.iterdir())
    if not files:
        sys.exit("::error::no release artifacts found")
    assets = [{"name": p.name, "size": p.stat().st_size, "sha256": sha256(p)} for p in files]
    return json.dumps(
        {
            "repo": e["REPO"],
            "tag": e["TAG"],
            "source": f"{e['SOURCE_BASE']}/{e['REPO']}",
            "commit": e["COMMIT"],
            "tag_object": e["TAG_OBJECT"],
            "object_format": e["OBJECT_FORMAT"],
            "signer": e["SIGNER"],
            "builder_commit": e["GITHUB_SHA"],
            "workflow": e["GITHUB_WORKFLOW_REF"],
            "run": e["RUN_URL"],
            "attestation": e["ATTESTATION_URL"],
            "assets": assets,
        },
        indent=2,
    )


def notes(release: dict) -> str:
    """What changed, then where it came from. Install instructions belong in the repo's README."""
    e = os.environ
    repo, tag, source, commit, signer, builder_commit, run = (
        release[k] for k in ("repo", "tag", "source", "commit", "signer", "builder_commit", "run")
    )
    builder = e["GITHUB_REPOSITORY"]
    out = []

    text = e.get("NOTES", "").strip()
    # A tag message that only repeats the name and version says nothing.
    if text and text not in {f"{repo} {tag.removeprefix('v')}", f"{repo} {tag}"}:
        out += [text, ""]

    signers = f"https://github.com/{builder}/blob/{builder_commit}/allowed_signers"
    kind = Path(release["workflow"].split("@")[0]).stem
    row = [
        f"[`{tag}`]({source}/tag/?h={tag}) at [`{commit[:12]}`]({source}/commit/?id={commit})",
        f"[`{signer}`]({signers})",
        f"[`{kind}.yml`]({run})",
    ]
    # The example names a real file: x86_64 if there is one, else the first.
    example = next((a["name"] for a in release["assets"] if "x86_64" in a["name"]), release["assets"][0]["name"])
    out += [
        "## Provenance",
        "",
        f"| [{source.split('://')[-1]}]({source}) | Signed by | Built by |",
        "|---|---|---|",
        f"| {' | '.join(row)} |",
        "",
        f"Check any file against its [build provenance attestation]({release['attestation']}):",
        "",
        "```sh",
        f"gh attestation verify {example} --repo {builder}",
        "```",
    ]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    match sys.argv[1:]:
        case ["collect", raw, out]:
            collect(Path(raw), Path(out))
        case ["json", out]:
            print(release_json(Path(out)))
        case ["notes", path]:
            sys.stdout.write(notes(json.loads(Path(path).read_text())))
        case _:
            sys.exit(__doc__)
