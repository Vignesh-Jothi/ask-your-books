# Open Knowledge Format (OKF)

OKF is the single machine-readable contract for everything that moves through
Ask Your Books, at two levels:

| Level | What it covers | Where it lives |
|-------|----------------|----------------|
| **Application (app-level)** | Every payload in/out of the agent & API: chat requests, chat responses, tool calls, metric results, eval cases | `okf/schemas/*.json` (JSON Schema) + `src/okf/envelope.py` |
| **Data (data-level)** | The canonical data dictionary of the accounting domain: entities, fields, units, relations — consumed by humans, the prompt builder and the schema-context generator | `okf/data/entity_catalog.json` |

## Envelope

Every app-level payload uses one envelope so tooling / logging / the frontend
can treat all messages uniformly:

```json
{
  "okf": "1.0",
  "kind": "chat.request",
  "schema": "chat.request.json",
  "ts": "2026-10-01T09:30:00Z",
  "org_id": "ORG1",
  "trace_id": "t_8f2c...",
  "data": { "...": "kind-specific payload" }
}
```

Rules:

1. `okf` is always `"1.0"`.
2. `kind` names the payload type; `schema` names the JSON Schema file under `okf/schemas/`.
3. `ts` is ISO-8601 UTC.
4. `org_id` is the **tenant** the payload belongs to. It is always set by
   server-side code from the authenticated user — never taken from model output
   or request body.
5. `trace_id` links every message of one chat turn (request, tool calls,
   response) for log correlation.
6. Amounts are **integer paise** (`112233` = ₹1,122.33) unless a field is
   explicitly declared `"format": "inr"` (presentation-only). No floats for money.

`src/okf/envelope.py` provides `pack()` / `unpack()` and validates `data`
against the JSON Schema on the way in/out where cheap to do so.

## Data-level OKF

`okf/data/entity_catalog.json` is the single data dictionary. It powers:

- the **schema-context prompt** sent to the LLM (so the model sees a curated
  column list, not a raw DDL dump),
- the **docs** (`docs/03_data_model.md`),
- future tooling (data lineage, report builders).

One catalog, every consumer reads it. That is the "easy access" contract:
add a column once, in one file, and every consumer sees it.

## How to extend

- **New API payload** → add `okf/schemas/<kind>.json`, add the pydantic twin in
  `src/api/models.py`, register kind in `src/okf/envelope.py::KINDS`.
- **New entity/column** → update `okf/data/entity_catalog.json`, then
  `seed.py` + `src/db/queries.py` + prompt template in `src/llm/prompts.py`
  (which reads the catalog automatically).
- See `docs/02_architecture.md` and `A_TO_Z_GUIDE.md` for walkthroughs.