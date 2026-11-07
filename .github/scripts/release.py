#!/usr/bin/env python3
"""release.json and the release notes for <repo>-<tag>.

    release.py json <dir>             release.json for the files in <dir>, from the environment:
                                      REPO TAG COMMIT TAG_OBJECT OBJECT_FORMAT SOURCE_BASE RUN_URL
                                      ATTESTATION_URL GITHUB_WORKFLOW_REF
    release.py notes <release.json>   the notes (Markdown); NOTES = the changelog section or tag
                                      message, SIGNER = the allowed_signers principal,
                                      GITHUB_REPOSITORY = this repo

The notes come from release.json alone (plus NOTES and SIGNER), so published releases can be
re-rendered from their own release.json.
"""

import hashlib
import json
import os
import sys
from pathlib import Path


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


def notes(release: dict) -> str:
    """What changed, then where it came from. Install instructions belong in the repo's README."""
    e = os.environ
    repo, tag, source, commit, run = (release[k] for k in ("repo", "tag", "source", "commit", "run"))
    builder = e["GITHUB_REPOSITORY"]
    out = []

    text = e.get("NOTES", "").strip()
    # A tag message that only repeats the name and version says nothing.
    if text and text not in {f"{repo} {tag.removeprefix('v')}", f"{repo} {tag}"}:
        out += [text, ""]

    signers = f"https://github.com/{builder}/blob/main/allowed_signers"
    principal = e.get("SIGNER", "").strip()
    kind = Path(release["workflow"].split("@")[0]).stem
    row = [
        f"[`{tag}`]({source}/tag/?h={tag}) at [`{commit[:12]}`]({source}/commit/?id={commit})",
        f"[`{principal}`]({signers})" if principal else "",
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
        case ["json", out]:
            print(release_json(Path(out)))
        case ["notes", path]:
            sys.stdout.write(notes(json.loads(Path(path).read_text())))
        case _:
            sys.exit(__doc__)
