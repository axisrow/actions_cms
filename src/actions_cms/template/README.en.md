# __SITE_NAME__

A MkDocs Material site. Posts arrive as pull requests; [actions_cms](https://github.com/__ENGINE_REPO__) publishes them to GitHub Pages.

Site address: __SITE_URL__

## Once, after creating the repository

1. Push the contents of this folder to the `main` branch of `__REPO__`.
2. **Settings → Pages → Source: GitHub Actions.**
3. **Settings → Actions → General → Workflow permissions: Read and write permissions** — the workflows commit to the repository.

The very first push publishes the sample post from `drafts/`.

## How a post gets published

1. A draft goes to `drafts/<batch>/NN-slug.md` and a pull request is opened. The batch is any folder, usually a date; `NN` is a sequence number; `slug` is latin and becomes the address of the post.
2. The `Check` workflow validates the drafts and builds the site with them as a trial.
3. Merging is the approval. The `Publish` workflow moves every draft on `main` to `docs/blog/posts/`, updates `content/index.json` and deploys the site.

Remove a draft from the pull request before merging if it should not go out. Edit a published post directly in `docs/blog/posts/`.

## A draft

```markdown
---
title: "Title"
date: 2026-01-31
rubric: news
tags: [tag, another tag]
summary: "Teaser for the list of posts and RSS, at most 280 characters."
status: draft
---

Lead: one or two sentences.

<!-- more -->

## First section

Main text.
```

| Field | Rule |
|---|---|
| `title`, `date`, `rubric`, `summary`, `status` | Required |
| `date` | Unquoted, `YYYY-MM-DD` |
| `rubric` | One of the rubrics in `cms.yaml`; the site category is filled in for you |
| `slug` | Leave it out: it comes from the file name |
| `<!-- more -->` | Required after the lead |

## Collecting raw material

Every 6 hours the `Collect` workflow puts fresh material into `inbox/`: items from the RSS feeds in `config/sources.yaml` and new links from the site sections in `config/sites.yaml`. While both lists are empty it does nothing. Files in `inbox/` are written by the bot — do not edit them by hand.

## Locally

```bash
pip install "git+https://github.com/__ENGINE_REPO__@__ENGINE_REF__" -r requirements.txt

cms validate --build        # check the drafts and build the site as a trial
cms dedup "Title"           # exit code 1 if a similar post already exists
cms index sync              # rebuild content/index.json from the files
cms collect                 # collect raw material into inbox/
mkdocs serve                # preview the site at http://127.0.0.1:8000
```

## What lives where

| Path | Purpose |
|---|---|
| `cms.yaml` | Engine settings: rubrics, paths, collectors |
| `mkdocs.yml` | Site settings: name, theme, plugins |
| `drafts/` | Drafts waiting to be published |
| `docs/blog/posts/` | Published posts |
| `content/index.json` | Registry of every post; maintained by the engine |
| `config/` | Sources for the collectors |
| `inbox/` | Collected raw material |
| `.github/workflows/` | Schedules and triggers: `collect`, `check`, `publish`, `pages` |
