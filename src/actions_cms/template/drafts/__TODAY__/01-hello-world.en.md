---
title: "First post: how this site works"
date: __TODAY__
rubric: guide
tags: [actions_cms]
summary: "The site is built from Markdown files by GitHub Actions: a draft arrives in a pull request, and merging it publishes the post to GitHub Pages."
status: draft
---

This is a sample post. It sits in `drafts/` as a draft and publishes itself as soon as it reaches the `main` branch.

<!-- more -->

## How a post gets published

1. A draft goes to `drafts/<date>/NN-slug.md` and a pull request is opened.
2. The check on the pull request finds mistakes before publication: an unknown rubric, a summary that is too long, a site that no longer builds.
3. Merging is the approval. The draft moves to `docs/blog/posts/`, the site is rebuilt and deployed to GitHub Pages.

## What a draft consists of

The file starts with a block holding the title, date, rubric, summary and status. The rubrics and their names on the site are listed in `cms.yaml`.

The first paragraph is the lead: it shows in the list of posts. The line `<!-- more -->` must follow it, and then comes the main text.

The address of a post comes from its file name, so the name is latin: `01-hello-world.md` becomes `/blog/<date>/hello-world/`.

When you no longer need this sample, delete its file from `docs/blog/posts/` and run `cms index sync`.
