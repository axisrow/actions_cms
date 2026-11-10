# actions_cms

CMS для статичных сайтов на GitHub Pages, которая целиком работает на GitHub Actions. Статья — это Markdown-файл в pull request; merge публикует её на сайте.

Сайт хранит только контент, один конфиг и четыре коротких workflow-файла. Вся механика живёт здесь и подключается как action по тегу, поэтому исправления движка доходят до сайтов без копирования кода.

```
config/*.yaml ──(Collect, по расписанию)──▶ inbox/        сырьё для статей
drafts/<партия>/NN-slug.md ──▶ pull request ──(Check)──▶ merge
        merge ──(Publish)──▶ docs/blog/posts/ + content/index.json ──(Pages)──▶ GitHub Pages
```

Генератор сайта — [MkDocs Material](https://squidfunk.github.io/mkdocs-material/) со встроенным блогом.

## Быстрый старт

> Версия 0.0.x. Пока не выпущен первый релиз, тега `v0` ещё нет: ставьте с ветки `main` (`@main` вместо `@v0`) и создавайте сайт с `--engine-ref main`.

```bash
pipx install "git+https://github.com/axisrow/actions_cms@v0"

cms init my-site --name "Мой сайт" --repo owner/my-site
cd my-site
git init -b main && git add -A && git commit -m "site"
git remote add origin git@github.com:owner/my-site.git
git push -u origin main
```

В настройках репозитория сайта, один раз:

1. **Settings → Pages → Source: GitHub Actions.**
2. **Settings → Actions → General → Workflow permissions: Read and write permissions.**

Первый push публикует пример статьи. Дальше — см. `README.md` в созданном сайте.

`cms init` принимает `--lang ru|en`, `--description`, `--site-url` (свой домен), `--engine-ref` (ветка или коммит движка вместо `v0`) и `--force`. Существующие файлы без `--force` не перезаписываются.

## Как сайт вызывает движок

```yaml
# .github/workflows/publish.yml в репозитории сайта
- uses: actions/checkout@v7
- uses: axisrow/actions_cms@v0
  with:
    run: promote --all
    commit: drafts docs content
    commit-message: "publish: {date}"
```

Action ставит Python, устанавливает CLI той же версии, что указана в `uses:`, выполняет команды и, если задано `commit`, коммитит и пушит результат.

| Вход | По умолчанию | Назначение |
|---|---|---|
| `run` | — | Команды `cms` без слова `cms`, по одной на строку. Аргументы делятся по пробелам, кавычки не поддерживаются |
| `commit` | — | Пути через пробел, которые нужно закоммитить и запушить после команд |
| `commit-message` | `cms: {datetime}` | `{date}` и `{datetime}` заменяются текущим временем UTC |
| `requirements` | — | Файл зависимостей сайта (MkDocs); ставится вместе с CLI и служит ключом кэша pip |
| `python-version` | `3.12` | |
| `working-directory` | `.` | Корень сайта, если он не в корне репозитория |

Выход `changed` равен `true`, если коммит был запушен.

Push выдерживает гонку с другим workflow: при отказе делается `pull --rebase` и новая попытка, до пяти раз. Если на сервере изменились те же файлы, шаг завершается ошибкой и ничего не пушит.

Расписания, фильтры путей, права и `concurrency` остаются в workflow-файлах сайта — их правят там.

## `cms.yaml`

Лежит в корне сайта. Обязательны только `rubrics`.

```yaml
generator: mkdocs-material

rubrics:                    # рубрика из front-matter → категория на сайте (null — без категории)
  news: Новости
  guide: Гайды

paths:
  drafts: drafts            # drafts/<партия>/NN-slug.md
  posts: docs/blog/posts
  index: content/index.json

required: [summary]         # сверх всегда обязательных title, date, rubric, status
summary_max: 280            # 0 — без ограничения

collect:
  feeds:
    config: config/sources.yaml
    inbox: inbox/news
    hours: 48               # брать записи не старше
    # user_agent: ...       # по умолчанию — собственный User-Agent feedparser
  sites:
    config: config/sites.yaml
    inbox: inbox/sites
    user_agent: "Mozilla/5.0 (compatible; actions-cms-bot/1.0)"
```

Неизвестный ключ и путь за пределами сайта — ошибка конфигурации.

## Команды

Корень сайта — ближайшая папка с `cms.yaml` вверх от текущей либо `--root DIR`.

| Команда | Что делает |
|---|---|
| `cms init DIR --name … --repo owner/name` | Создаёт сайт из шаблона |
| `cms validate [--build]` | Проверяет настройки и все черновики. `--build` публикует их во временную копию сайта и собирает её в строгом режиме; сам сайт не трогает |
| `cms promote [--all]` | Переносит черновики в посты и пересобирает индекс. `--all` — все черновики, без него — только со `status: approved` |
| `cms build` | `mkdocs build --strict` |
| `cms index sync` | Пересобирает индекс по файлам постов и черновиков |
| `cms dedup "Заголовок" [--threshold 0.75]` | Печатает похожие статьи из индекса |
| `cms collect [feeds\|sites] [--hours N]` | Собирает сырьё в inbox |

Коды выхода: `0` — выполнено; `1` — проблема в контенте (или `dedup` нашёл похожую статью); `2` — ошибка конфигурации или вызова.

## Контракт контента

Черновик — файл `drafts/<партия>/NN-slug.md`: партия — любая папка (обычно дата), `NN` — две цифры, `slug` — латиница, цифры и дефисы.

```markdown
---
title: "Заголовок"
date: 2026-01-31
rubric: news
tags: [тег]
summary: "Анонс не длиннее 280 знаков."
status: draft
---

Лид.

<!-- more -->

## Раздел

Текст.
```

`cms promote` превращает его в `docs/blog/posts/2026-01-31-slug.md`: ставит `status: approved`, дописывает `slug` (от него зависит латинский адрес `blog/2026/01/31/slug/`) и `categories` по рубрике, если автор их не указал. Тело не меняется.

Сначала проверяются все выбранные черновики, и только потом что-либо переносится. Публикация отменяется целиком, если хотя бы в одном:

- нет обязательного поля, рубрика не из `cms.yaml`, `summary` длиннее лимита, `tags` — не список;
- `date` записана строкой в кавычках;
- имя файла не латинское, или `slug` во front-matter не совпадает с именем;
- нет `<!-- more -->`, когда `mkdocs.yml` требует отсечку анонса;
- в `categories` чужая категория или нет категории своей рубрики;
- слаг уже занят другим черновиком или опубликованным постом. Слаг уникален в пределах сайта.

Опубликованный пост движок не перезаписывает: его правят прямо в `docs/blog/posts/`.

`content/index.json` — реестр всех статей: `slug`, `title`, `date`, `rubric`, `tags`, `status`, `path`. Он целиком выводится из файлов; править его руками не нужно.

## Сбор сырья

`cms collect` пишет находки в `inbox/…/<дата UTC>.json`. Недоступный источник пропускается с пометкой в журнале и не останавливает остальные.

**Ленты** (`config/sources.yaml`) → `{title, url, source, published, summary}`. Адрес не повторяется в пределах дня.

```yaml
keywords: [widget, gadget]     # для лент с filter: true — брать записи с этими словами
exclude: [advertisement]       # отбрасывать записи с этими словами во всех лентах
feeds:
  - name: Example blog
    url: https://example.com/feed.xml
    filter: true
```

**Разделы сайтов** (`config/sites.yaml`) → `{source, title, url}`. Адрес, уже попавший в любой файл inbox, больше не сообщается.

```yaml
- name: Example
  articles: https://example.com/blog/    # раздел, за статьями которого следить
  rss: https://example.com/feed/         # необязательно; пробуется первым
  keywords: [release]                    # необязательно; оставить заголовки с этими словами
```

Источники пробуются по порядку: лента сайта, ссылки в HTML раздела, карта сайта (для разделов, которые рисуют список скриптом). Файл может быть и словарём групп — берутся все списки внутри него; записи без `articles` и `rss` пропускаются.

## Версии

Сайты ссылаются на мажорный тег: `axisrow/actions_cms@v0`. Выпуск: поднять `__version__` в `src/actions_cms/__init__.py`, запушить тег `vX.Y.Z` — workflow `Release` проверит, что тег совпадает с версией, и передвинет `vX`.

Версии сторонних actions (`checkout`, `upload-pages-artifact`, `deploy-pages`) записаны в workflow-файлах сайта; шаблон включает `dependabot.yml`, который раз в месяц предлагает их обновить.

## Ограничения

- **Material for MkDocs прекращает поддержку 5 мая 2027 года**; преемник — [Zensical](https://zensical.org/). Всё, что движок знает о генераторе, собрано в `src/actions_cms/generators/mkdocs_material.py` — второй генератор добавляется рядом.
- `cms validate --build` собирает копию сайта без `.git`. Плагины MkDocs, читающие историю git, репозитория в ней не увидят.
- В workflow шаблона ветка называется `main`.
- Action вызывается из других репозиториев, поэтому репозиторий движка должен оставаться публичным (приватный доступен только вашим же приватным репозиториям).

## Перенос существующего сайта

Положите в корень `cms.yaml`, описывающий текущую раскладку, и замените шаги workflow вызовами action. Пути, имена папок inbox, файлы источников и User-Agent задаются конфигом, поэтому переносить файлы не нужно. Перед первым запуском выполните `cms validate` и `cms index sync` — они покажут расхождения.

## Разработка

```bash
pip install -e ".[dev]"
pytest
```

Сборщики тестируются на подставных лентах и страницах, без обращения к сайтам. `tests/test_e2e.py` собирает настоящий сайт из шаблона, `tests/test_commit_sh.py` гоняет скрипт коммита на локальном bare-репозитории, `tests/test_packaging.py` собирает wheel (нужен доступ к PyPI) и проверяет, что шаблон попал в него целиком.

Лицензия — MIT.
