# Publish to GitHub

The project is ready to publish from this folder or from the extracted
`dist/cs2-tradeup-bot.zip`. The ZIP contains source, tests and documentation;
it excludes credentials, runtime data, virtual environments and Git history.

## 1. Create an empty repository

Install [Git](https://git-scm.com/downloads), sign into GitHub and create a new
repository named `cs2-tradeup-bot`. Choose **Public** to share it with everyone.
Leave GitHub's **Add a README**, **Add .gitignore** and **Choose a license**
options empty; these files already exist here.

## 2. Initialize and review locally

Open PowerShell in the project folder (the folder containing `main.py`):

```powershell
git init -b main
git add .
git status --short
git diff --cached --stat
git ls-files .env data .venv dist
```

The last command should list only `data/.gitkeep`. `.env.example` is intentionally
public and contains blank credential fields. Your `.env`, cached listings,
saved queues and generated ZIP must not be staged. If they appear, stop and
remove them from the index with `git restore --staged <path>` after an existing
commit, or `git rm --cached <path>` before the initial commit; this leaves the
working file on disk. Rotate any credentials that were already published.

## 3. Commit and push

Replace `YOUR_USERNAME` with your actual GitHub username:

```powershell
git commit -m "Initial public release"
git remote add origin https://github.com/YOUR_USERNAME/cs2-tradeup-bot.git
git push -u origin main
```

If Git asks for an identity, set your name and GitHub email locally, then retry
the commit:

```powershell
git config user.name "Your Name"
git config user.email "YOUR_GITHUB_EMAIL"
```

Complete the Git credential manager/browser sign-in if prompted. An account
password is not used for HTTPS Git authentication. If `origin` already exists,
inspect `git remote -v` and use `git remote set-url origin <your-repository-url>`
only if you need to change it. Do not force-push to resolve an unexpected error.

These steps follow GitHub's [guide to adding local code](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)
and [remote repository guide](https://docs.github.com/en/get-started/git-basics/managing-remote-repositories).

## 4. Share and update

Check the **Actions** tab for the test and Docker build results. Share your
repository URL. Everyone supplies their own API key and optional Discord webhook.
GitHub hosts the code; it does not keep this bot running. Run it on a computer or
server with Docker or Python.

For later changes:

```powershell
git add .
git diff --cached --stat
git commit -m "Describe your change"
git push
```

To regenerate the clean source ZIP locally:

```powershell
python scripts/package_release.py
```

You can attach that ZIP to a GitHub Release. Cached third-party data is not
redistributed, and the MIT license covers this repository's code, not external
services, trademarks or data.
