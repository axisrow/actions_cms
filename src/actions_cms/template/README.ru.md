# __SITE_NAME__

Сайт на MkDocs Material. Статьи приходят pull request'ами, публикацию на GitHub Pages делает движок [actions_cms](https://github.com/__ENGINE_REPO__).

Адрес сайта: __SITE_URL__

## Один раз после создания репозитория

1. Запушьте содержимое этой папки в ветку `main` репозитория `__REPO__`.
2. **Settings → Pages → Source: GitHub Actions.**
3. **Settings → Actions → General → Workflow permissions: Read and write permissions** — workflow коммитят в репозиторий.

Первый же push опубликует пример статьи из `drafts/`.

## Как выходит статья

1. Черновик кладут в `drafts/<партия>/NN-slug.md` и открывают pull request. Партия — любая папка, обычно дата; `NN` — порядковый номер; `slug` — латиницей, из него получится адрес статьи.
2. Workflow `Check` проверяет черновики и пробно собирает сайт с ними.
3. Merge — это одобрение. Workflow `Publish` переносит все черновики из `main` в `docs/blog/posts/`, обновляет `content/index.json` и выкладывает сайт.

Неудачный черновик удаляют из pull request до merge. Опубликованную статью правят прямо в `docs/blog/posts/`.

## Черновик

```markdown
---
title: "Заголовок"
date: 2026-01-31
rubric: news
tags: [тег, ещё тег]
summary: "Анонс для списка статей и RSS, не длиннее 280 знаков."
status: draft
---

Лид: один-два предложения.

<!-- more -->

## Первый раздел

Основной текст.
```

| Поле | Правило |
|---|---|
| `title`, `date`, `rubric`, `summary`, `status` | Обязательны |
| `date` | Без кавычек, `ГГГГ-ММ-ДД` |
| `rubric` | Одна из рубрик в `cms.yaml`; категория на сайте подставится сама |
| `slug` | Не указывают: он берётся из имени файла |
| `<!-- more -->` | Обязателен после лида |

## Сбор сырья

Workflow `Collect` каждые 6 часов складывает свежие материалы в `inbox/`: записи RSS-лент из `config/sources.yaml` и новые ссылки из разделов сайтов из `config/sites.yaml`. Пока оба списка пусты, он ничего не делает. Файлы в `inbox/` пишет робот — руками их не правят.

## Локально

```bash
pip install "git+https://github.com/__ENGINE_REPO__@__ENGINE_REF__" -r requirements.txt

cms validate --build        # проверить черновики и пробно собрать сайт
cms dedup "Заголовок"       # код выхода 1, если похожая статья уже есть
cms index sync              # пересобрать content/index.json по файлам
cms collect                 # собрать сырьё в inbox/
mkdocs serve                # посмотреть сайт на http://127.0.0.1:8000
```

## Что где лежит

| Путь | Назначение |
|---|---|
| `cms.yaml` | Настройки движка: рубрики, пути, сбор сырья |
| `mkdocs.yml` | Настройки сайта: название, тема, плагины |
| `drafts/` | Черновики, ждущие публикации |
| `docs/blog/posts/` | Опубликованные статьи |
| `content/index.json` | Реестр всех статей; его ведёт движок |
| `config/` | Источники для сбора сырья |
| `inbox/` | Собранное сырьё |
| `.github/workflows/` | Расписания и триггеры: `collect`, `check`, `publish`, `pages` |
