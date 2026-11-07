# cgit-release-builder

Builds, attests and publishes releases of signed tags from [git.vkut.me](https://git.vkut.me).
The repositories live there (SHA-256, plain git + cgit); this repo only runs their release
builds on GitHub Actions and keeps the results as GitHub releases named `<repo>-<tag>`.

## How a release happens

1. A signed `v*` tag is pushed to a repository on git.vkut.me with releases enabled
   (`ssh git@… release <repo> bun|uv|rust`).
2. The server starts that language's workflow with the repo and tag.
3. **build** (read-only token) clones the tag over HTTPS and checks that it is an annotated tag
   signed by a key in [`allowed_signers`](allowed_signers), that it isn't released yet, and that
   `CHANGES.md`/`CHANGELOG.md` (if present) has a `## [<version>]` section. Then it builds:

   | Workflow | Build |
   |---|---|
   | [`bun`](.github/workflows/bun.yml) | Bun from `packageManager`; `package.json` version must match the tag; `bun install --frozen-lockfile --ignore-scripts`; `typecheck` and `test` scripts if defined; then the `release` script if defined (writes to `$OUT`), else `build` (if defined) + `bun pm pack` |
   | [`uv`](.github/workflows/uv.yml) | project version must match the tag; `uv build` (sdist + wheel) |
   | [`rust`](.github/workflows/rust.yml) | per target (x86_64 and aarch64 Linux, native runners); toolchain from `rust-toolchain.toml`, else stable; `Cargo.toml` version must match the tag; `cargo test` + `cargo build --release --locked`; each binary as `<bin>-<version>-<target>.tar.gz` with README/licence files |

   An executable `.release` script in the repo replaces the build step of any workflow. It runs
   in the source checkout and gets `OUT` (directory for the files to publish: regular files only,
   tar directories), `TAG`, `VERSION` (tag without the `v`), `SOURCE_DATE_EPOCH` (commit time)
   and, for rust, `TARGET`.
4. **publish** ([`_publish.yml`](.github/workflows/_publish.yml), the only job with write
   access) attests the files with
   [artifact attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations)
   (Sigstore) and creates the release with them and `release.json` (source, commit, run,
   attestation, sha256 of every file), which git.vkut.me reads to show download buttons.

Release builds start from a fresh runner with no caches.

## Verify a download

```sh
gh attestation verify ausculto-0.3.1.tgz --repo v-kut/cgit-release-builder
```

The attestation names the workflow and its inputs (repo, tag); `release.json` and the release
notes name the source commit on git.vkut.me, whose tag is signed by `code@vkut.me`.
