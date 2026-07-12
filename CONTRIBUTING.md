# Contributing to NeuroWeave

Thanks for considering a contribution. This project favors small, well-tested changes over large
speculative ones — see the design philosophy below before opening a big PR.

## Setup

```bash
git clone <your-fork-url>
cd NextWeave
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set OPENAI_API_KEY at minimum
docker compose up -d postgres redis
alembic upgrade head
uvicorn app.main:app --reload
```

Run the test suite before and after your change:
```bash
pytest tests/ -v
pytest sdk/python/tests/ -v
cd sdk/typescript && npx tsc -p tsconfig.json --noEmit
```

## Design philosophy (read before adding a subsystem)

- **Heuristics in hot paths, LLM calls only where their cost is justified.** The live chat path
  (`RuntimeOrchestrator.chat()`) intentionally uses heuristic scoring instead of an LLM call for
  latency reasons. If you're adding something to a hot path, default to the same tradeoff unless
  you have a specific reason not to.
- **Soft-delete by default.** Memories move through a lifecycle (active → dormant → archived →
  forgotten) and are never physically removed. The one exception is `DataDeletionService`, which
  exists specifically for GDPR-style user-requested erasure — don't add a second hard-delete path
  elsewhere without a similarly explicit justification.
- **Fail open on non-critical dependencies.** LLM provider failures fall back to a deterministic
  echo provider; missing Celery broker never fails a chat request. If you add a call to an
  external or optional service from a path that should still work without it, follow this
  pattern.
- **Don't fake results.** The benchmark suite explicitly raises `NotImplementedError` for
  strategies it can't actually run (Mem0/Zep) rather than fabricating comparison numbers. Apply
  the same standard anywhere you're tempted to stub a result instead of implementing or clearly
  erroring.
- **Test with more than mocks.** Every existing subsystem has both unit tests and was verified
  with a live end-to-end run against a real (SQLite is fine) database before being considered
  done. Please do the same for new subsystems.

## Where things live

See [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md) for the full architecture, pipeline, API
reference, and database schema. `docs/archive/` has the original build logs for each subsystem
if you want implementation-level detail, including specific bugs that were found and fixed.

## Pull requests

- Keep PRs scoped to one subsystem or fix where possible.
- Include or update tests for anything you change.
- Run the full test suite and note the result in your PR description.
- If you're adding a new framework integration (LlamaIndex, CrewAI, AutoGen, etc.), follow the
  shape of `sdk/python/neurowave/integrations/langchain.py` — wrap `NeuroWeaveClient`, don't
  duplicate pipeline logic.

## Reporting issues

Open a GitHub issue with steps to reproduce. For security-sensitive issues, please avoid filing
a public issue — see the repository's security policy (or contact the maintainers directly) if
one is configured.
