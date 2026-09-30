# Optional semantic enrichment

Conversion, inspection, chapter inspection, bundle writing, and bundle validation are local operations. They do not require JEV.

## Explicit cloud gate

JEV-backed enrichment can send selected document text and context to the configured backend. It requires an explicit `--yes-cloud` acknowledgement:

```bash
ssmdconvert enrich book.ssmd \
  -o book.enriched.ssmd \
  --speakers \
  --yes-cloud
```

Without the acknowledgement, the command stops before enrichment.

## Speaker attribution

Speaker attribution begins with deterministic local discovery. Obvious attributions can remain local. Ambiguous dialogue can be submitted to JEV against the finite cast discovered from the document. The returned decision report retains confidence information.

## Voice casting

Voice casting requires a caller-supplied finite inventory. For example:

```json
{
  "af_bella": "English female voice; warm and conversational",
  "am_adam": "English male voice; neutral adult narrator"
}
```

Use the inventory with a provider:

```bash
ssmdconvert enrich book.ssmd \
  -o book.voiced.ssmd \
  --speakers \
  --voices voices.json \
  --provider kokoro \
  --yes-cloud
```

Provider voice IDs come from the supplied inventory. JEV is not asked to invent IDs.

## Decision report

Use `--report` to save an audit and debugging artifact containing semantic decisions, confidence, and backend metadata:

```bash
ssmdconvert enrich book.ssmd \
  -o book.enriched.ssmd \
  --speakers \
  --yes-cloud \
  --report decisions.json
```

The report records decisions; it is not a deterministic proof of correctness.
