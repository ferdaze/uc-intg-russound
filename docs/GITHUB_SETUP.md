# GitHub setup guide

Getting this repository onto GitHub and producing your first automated release.

---

## Step 1 — Get the code into the repo

`github.com/ferdaze/uc-intg-russound` already exists and is empty, so there's
nothing to merge around.

```bash
# Somewhere sensible on your machine
git clone https://github.com/ferdaze/uc-intg-russound.git
cd uc-intg-russound

# Copy in the contents of the archive you downloaded
# (everything including .github/ and .gitignore)

git add .
git commit -m "Initial commit: Russound RIO integration for Unfolded Circle Remote"
git branch -M main
git push -u origin main
```

Double-check that hidden files made it in — `.github/workflows/build.yml` is easy
to miss when copying with a file manager:

```bash
git ls-files | grep -E "^\.github|^\.gitignore"
```

You should see `.github/workflows/build.yml` and `.gitignore`.

---

## Step 2 — Check Actions permissions

The release job needs to create releases and upload assets.

1. Repo → **Settings → Actions → General**.
2. Under **Workflow permissions**, select **Read and write permissions**.
3. Save.

Without this the build succeeds but the release step fails with a 403.

The workflow uses the built-in `GITHUB_TOKEN`. You do **not** need a personal
access token or any repository secrets.

---

## Step 3 — Verify the build before tagging

Don't tag first and debug later. Run the workflow manually:

1. Repo → **Actions** tab.
2. If prompted to enable workflows, click **I understand my workflows, go ahead and enable them**.
3. Select **Build & Release** in the left sidebar.
4. Click **Run workflow**, enter `0.1.0` as the version, and run it.

This runs the tests and the aarch64 build but skips the release step, so you get
a downloadable artifact without creating a public release. Roughly 8–12 minutes,
most of it QEMU emulating aarch64.

When it's green, download the artifact from the run summary page and check it:

```bash
tar tzf uc-intg-russound-0.1.0-aarch64.tar.gz | head
```

You want to see `./driver.json` and `./bin/driver`.

---

## Step 4 — Cut the release

The workflow refuses to build if the tag and `driver.json` disagree, so bump the
version in one place and keep them in step.

```bash
# 1. Make sure driver.json says the version you're releasing
jq .version driver.json          # -> "0.1.0"

# 2. Make sure CHANGELOG.md has a matching "## v0.1.0" heading
#    (the release notes are pulled from that section)

# 3. Tag and push
git tag v0.1.0
git push origin v0.1.0
```

Pushing the tag triggers the full pipeline: test → build → release. When it
finishes, the release appears under **Releases** with the `.tar.gz` and a
`.hash` file containing its SHA-256.

---

## Step 5 — Install it on the Remote

See [USER_GUIDE.md](USER_GUIDE.md). Short version: download the `.tar.gz` from
the release and upload it in the web configurator under
**Integrations → Add new → Install custom**.

---

## Releasing an update later

```bash
# 1. Bump the version in driver.json AND pyproject.toml
# 2. Add a "## v0.2.0" section at the top of CHANGELOG.md
git add . && git commit -m "Release v0.2.0"
git push

git tag v0.2.0
git push origin v0.2.0
```

On the Remote, tick **Update existing driver** when uploading (needs firmware
2.9.3+). On older firmware, delete the instance and then the driver first.

---

## What the workflow does

| Job | What happens |
|---|---|
| `test` | Installs dependencies on Python 3.11 and runs the test suite against a mock RIO server |
| `build` | Checks tag/manifest versions match, runs PyInstaller inside Unfolded Circle's aarch64 image under QEMU, assembles the tar.gz, fails if it exceeds the Remote's 100 MB limit |
| `release` | Only on tag pushes: creates the GitHub release with notes from CHANGELOG.md and attaches the archive plus a SHA-256 hash |

**On Docker:** the driver itself is not a container — it's a plain binary that
runs natively on the Remote. Docker appears in the build only because
PyInstaller can't cross-compile, so the aarch64 binary has to be produced inside
an aarch64 environment. Nothing container-related ends up in the release.

---

## Optional: a custom driver icon

By default the integration uses the built-in `uc:integration` icon. To use
your own:

1. Make a 90×90 pixel PNG or JPG, 16 KB maximum.
2. Put it in the repo root, e.g. `russound.png`.
3. In `driver.json`, change `"icon": "uc:integration"` to `"icon": "custom:russound.png"`.
4. Add a copy step to the workflow's **Assemble installation archive** stage:
   ```yaml
   cp russound.png artifacts/
   ```

The icon must sit in the archive root next to `driver.json`.

---

## Things that will bite you

**`driver_id` collisions.** This project uses `russound`. If an older Russound
integration is still installed on your Remote, remove it before installing this
one — same `driver_id` means the Remote treats them as the same driver.

**Builder image tag.** The workflow pins
`unfoldedcircle/r2-pyinstaller:3.11.13-0.7.0`. If Docker Hub reports that tag as
missing, check the
[available tags](https://hub.docker.com/r/unfoldedcircle/r2-pyinstaller/tags)
and update `PYTHON_VER` in `.github/workflows/build.yml`.

**Version drift.** `driver.json` is the source of truth for the build. Forgetting
to bump it before tagging now fails the build with a clear message instead of
shipping a mislabelled archive.

**Dependency pins.** `ucapi-framework` 1.9.7 requires `ucapi` 0.7.0 or newer.
Don't downgrade `ucapi` on its own, and if you bump the framework, check its
requirements first.
