# Development

## Commands

```bash
make install-dev
make test
make lint
make typecheck
make run
```

## Local Database

The default database URL is in-memory SQLite:

```text
sqlite+pysqlite:///:memory:
```

For PostgreSQL, set:

```text
DEALERAI_DATABASE_URL=postgresql+psycopg://dealerai:dealerai@localhost:5432/dealerai_ops
```

## Docker

```bash
docker compose up --build
```

The compose file starts the API and a local PostgreSQL instance with development-only credentials.

## Synthetic Seed Data

```bash
python -m dealerai_ops.scripts.seed_synthetic_data --reset
```

The default generator is deterministic and creates the Phase 2 dataset size required for local
analytics and later ML experiments. Override `DEALERAI_DATABASE_URL` or pass `--database-url` to seed
a different database.

## No-Show Model Training

```bash
python -m dealerai_ops.scripts.train_no_show_model
```

This writes `model.joblib`, `feature_schema.json`, `metadata.json`, and `metrics.json` under
`DEALERAI_NO_SHOW_MODEL_DIR`. The default path is ignored by Git so regenerated model binaries are not
committed accidentally.

## Tool Layer

The Phase 4 tools can be called directly from Python through `ToolExecutor`. They require a SQLAlchemy
session and can optionally receive an authorization hook and no-show prediction service.

```python
from dealerai_ops.tools import ToolContext, ToolExecutor

executor = ToolExecutor(session)
result = executor.execute(
    "lookup_customer",
    {"customer_id": "cus_00000001"},
    ToolContext(request_id="local-request-0001"),
)
```

## Retrieval

The local retriever indexes the synthetic markdown corpus without paid APIs:

```python
from dealerai_ops.rag import build_local_retriever

retriever = build_local_retriever("knowledge")
chunks = retriever.retrieve("Does booking require confirmation?", top_k=5)
```
