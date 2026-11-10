"""The `cms` command.

Exit codes: 0 — done; 1 — the content has problems (or `dedup` found a match);
2 — the configuration or the invocation is wrong.
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
from pathlib import Path

from . import __version__, config, dedup, generators, index, promote, validate
from .collect import feeds as feeds_collector
from .collect import sites as sites_collector
from .errors import CmsError, ConfigError, ContentError, Problem
from .init import LANGS, default_engine_ref, init

NETWORK_TIMEOUT = 30  # seconds; feedparser has none of its own


def _escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _annotate(problem: Problem) -> None:
    """Show the problem on the pull request when running inside GitHub Actions."""
    if os.environ.get("GITHUB_ACTIONS") != "true" or not problem.path:
        return
    workspace = Path(os.environ.get("GITHUB_WORKSPACE") or Path.cwd()).resolve()
    path = problem.path.resolve()
    if path.is_relative_to(workspace):
        path = path.relative_to(workspace)
    file = _escape(path.as_posix()).replace(":", "%3A").replace(",", "%2C")
    print(f"::error file={file}::{_escape(problem.message)}")


def _report(site: config.Site | None, problems: list[Problem]) -> None:
    for problem in problems:
        where = site.show(problem.path) if site and problem.path else problem.path
        print(f"{where}: {problem.message}" if where else problem.message, file=sys.stderr)
        _annotate(problem)


def cmd_init(args: argparse.Namespace) -> int:
    written, skipped = init(
        Path(args.dir),
        name=args.name,
        repo=args.repo,
        description=args.description,
        site_url=args.site_url,
        lang=args.lang,
        engine_ref=args.engine_ref,
        force=args.force,
    )
    for path in skipped:
        print(f"skip   {path} (exists; --force to overwrite)")
    print(f"{args.dir}: {len(written)} files written, {len(skipped)} skipped. Next steps are in {args.dir}/README.md")
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    site = config.load(args.root)
    socket.setdefaulttimeout(NETWORK_TIMEOUT)
    collectors = {
        "feeds": (site.feeds.config, lambda: feeds_collector.collect(site, args.hours)),
        "sites": (site.sites.config, lambda: sites_collector.collect(site)),
    }
    for name in [args.what] if args.what else list(collectors):
        cfg, run = collectors[name]
        if not args.what and not cfg.is_file():
            print(f"{name}: {site.show(cfg)} not found, skipped")
            continue
        run()
    return 0


def cmd_dedup(args: argparse.Namespace) -> int:
    hits = dedup.similar(config.load(args.root), args.title, args.threshold)
    for ratio, item in hits:
        print(f"{ratio:.2f}  {item['date']}  {item['title']}  ({item['path']})")
    return 1 if hits else 0


def cmd_index_sync(args: argparse.Namespace) -> int:
    site = config.load(args.root)
    added, removed = index.sync(site)
    for slug in added:
        print(f"+ {slug}")
    for slug in removed:
        print(f"- {slug}")
    print(f"{site.show(site.index)}: +{len(added)} -{len(removed)}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    site = config.load(args.root)
    problems = validate.static(site)
    if problems:
        _report(site, problems)
        return 1
    drafts = len(list(site.drafts.glob("*/*.md")))
    print(f"{drafts} draft(s) OK")
    if args.build:
        ok, output = validate.preview_build(site)
        print(output, end="" if output.endswith("\n") else "\n")
        if not ok:
            print("preview build failed", file=sys.stderr)
            return 1
        print("preview build OK")
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    site = config.load(args.root)
    moves = promote.promote(site, approve_all=args.all)
    for move in moves:
        print(f"{site.show(move.draft)} -> {site.show(move.target)}")
    if not moves:
        print("no drafts to publish" if args.all else "no approved drafts")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    site = config.load(args.root)
    return 1 if generators.get(site.generator).build(site).returncode else 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="cms", description="A GitHub-Actions-driven CMS for static sites.")
    ap.add_argument("--version", action="version", version=f"actions_cms {__version__}")
    ap.add_argument("--root", help="site root (default: the nearest folder with cms.yaml, from here upwards)")
    # the same option after the subcommand must not reset a value given before it
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="command", required=True, metavar="command")

    p = sub.add_parser("init", help="create a new site from the template")
    p.add_argument("dir")
    p.add_argument("--name", required=True, help="site title")
    p.add_argument("--repo", required=True, help="GitHub repository of the site: owner/name")
    p.add_argument("--description", default="", help="one-line site description")
    p.add_argument("--site-url", help="public URL (default: the GitHub Pages URL of --repo)")
    p.add_argument("--lang", default="ru", choices=sorted(LANGS), help="site language (default: ru)")
    p.add_argument("--engine-ref", help=f"actions_cms ref the workflows use (default: {default_engine_ref()})")
    p.add_argument("--force", action="store_true", help="overwrite existing files")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("collect", parents=[common], help="collect raw material into the inbox")
    p.add_argument("what", nargs="?", choices=["feeds", "sites"], help="one collector (default: every configured one)")
    p.add_argument("--hours", type=int, help="max age of feed items (default: collect.feeds.hours)")
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("dedup", parents=[common], help="exit 1 if a similar title is already in the index")
    p.add_argument("title")
    p.add_argument("--threshold", type=float, default=0.75)
    p.set_defaults(func=cmd_dedup)

    p = sub.add_parser("index", help="maintain the article index")
    isub = p.add_subparsers(dest="index_command", required=True, metavar="action")
    p = isub.add_parser("sync", parents=[common], help="rebuild the index from posts and drafts")
    p.set_defaults(func=cmd_index_sync)

    p = sub.add_parser("validate", parents=[common], help="check the drafts and the site configuration")
    p.add_argument("--build", action="store_true", help="also publish into a temporary copy and build it strictly")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("promote", parents=[common], help="move drafts to posts and update the index")
    p.add_argument("--all", action="store_true", help="publish every draft (a merged PR is the approval)")
    p.set_defaults(func=cmd_promote)

    p = sub.add_parser("build", parents=[common], help="build the site strictly")
    p.set_defaults(func=cmd_build)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except ContentError as e:
        site = None
        try:
            site = config.load(getattr(args, "root", None))
        except ConfigError:
            pass
        _report(site, e.problems)
        return 1
    except CmsError as e:
        print(f"cms: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
