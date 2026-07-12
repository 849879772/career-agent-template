# Repository Guidelines

## Project Structure & Module Organization

This Python recruitment intelligence system starts in `main.py`, crawls target career sites, analyzes jobs, stores state, and generates HTML reports.

- `crawlers/`: one crawler module per company or platform. New crawlers should subclass `BaseCrawler` from `crawlers/base.py` and be registered in `crawlers/__init__.py`.
- `analyzer.py`, `db.py`, `reporter.py`, `notifier.py`: analysis, SQLite persistence, report generation, and Feishu notification logic.
- `webapp.py`: local Flask application for managing applications.
- `profile.yaml`: user skills, target roles, scoring weights, and thresholds.
- `config.yaml`: companies, crawler keys, and model runtime configuration.
- `data/`: SQLite database and JSON/YAML runtime data. Treat `data/jobs.db` as stateful.
- `reports/`: generated HTML reports.
- `tests/`: pytest unit tests. `temp_test/` contains exploratory scripts and is not collected by pytest.

## Build, Test, and Development Commands

```bash
pip install -r requirements.txt
playwright install chromium
python main.py
python -m pytest
python -m pytest tests/test_db.py
python tests/smoke_crawlers.py unitree
python webapp.py
```

- Install dependencies before crawling; Playwright Chromium is required for rendered career pages.
- `python main.py` runs the full crawl, analyze, report, and notify pipeline.
- `python -m pytest` runs formal tests from `tests/` only, as configured in `pytest.ini`.
- `tests/smoke_crawlers.py` performs real website checks and may take several minutes.

## Coding Style & Naming Conventions

Use standard Python style with 4-space indentation, clear function names, and focused modules. Name crawler files after their crawler key, for example `crawlers/unitree.py` with `crawler: unitree` in `config.yaml`. Return normalized job dictionaries via base crawler helpers where possible. Avoid manual edits to generated outputs unless the task is about reports or data migration.

## Testing Guidelines

Add or update pytest tests in `tests/` for parser, database, analyzer, reporter, and notifier changes. Test files should follow `test_*.py`; test functions should use `test_*`. For crawler behavior, prefer deterministic unit tests with saved HTML snippets when possible, and use smoke scripts only for live-site validation.

## Company Integration Tracking

When adding or verifying company crawlers, always update `outputs/company_integration_status.md` before finishing. Treat this as the single source of truth for company integration status.

- Use the local Codex skill `recruitment-crawler-integration` for company onboarding, campus URL validation, failed-candidate handling, and crawler status maintenance.
- Follow the canonical workflow in `docs/crawling_process.md`. If you discover a better crawler strategy, Firecrawl/Crawl4AI usage pattern, validation rule, or integration shortcut, update that document in the same turn and tell the user what changed.
- Add verified crawler entries to `config.yaml` only after a real crawler run returns job rows from the correct campus recruitment page.
- Record successful additions under `Newly Added And Connected`.
- Move aliases or duplicates already covered by config into the covered/removed state instead of leaving them in the pending list.
- Keep unresolved companies under `Not Connected / Needs URL Search Or Verification`.
- Put unusable links, such as personal centers, delivery records, success pages, third-party pages, forms, or WeChat-only entries, under `Has URL But Cannot Be Used Directly`.
- Add a short reason under `Excluded Or Needs Attention` when a candidate fails validation, for example: returned 0 jobs, social jobs only, internships only, product/navigation text, category cards instead of jobs, wrong company, or requires a narrower parser.

## Commit & Pull Request Guidelines

Git history uses Conventional Commit-style messages, often scoped: `feat(config): ...`, `feat(crawlers): ...`, `chore: ...`. Keep commits focused and mention affected crawler/platform names. Pull requests should include purpose, test commands run, changed environment variables, and screenshots or report links for HTML changes.

## Security & Configuration Tips

Do not commit secrets. Required runtime variables include `DEEPSEEK_API_KEY`; `FEISHU_WEBHOOK` is optional for notifications. Preserve the local merge convention for `data/jobs.db`: use normal pull-then-push flow and avoid force-pushes, because CI also updates database state.
