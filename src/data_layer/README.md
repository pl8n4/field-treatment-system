# data_layer

Farm records, label knowledge, and weather — components 1–5 of
[system-spec.md](../../development_documentation/system-spec.md). Every function
returns Pydantic models from [schemas.py](schemas.py); nothing in here calls an
LLM.

## Farm records — [records.py](records.py)

- **`list_fields()` / `list_products()` / `list_applications()`** — every row of
  the matching JSON file, validated. Parsed once and cached; call freely.
- **`find_field(text)` / `find_product(text)`** — resolve free text to one
  record, or `None`. Ids match by exact equality, names by case-insensitive
  substring (`"hartley north"`, `"enlist"`). A miss and an ambiguous match
  (`"hartley"` hits two fields) both return `None`, and both mean the same
  thing: ask the user which one they meant.
- **`applications_for(field_id, *, product=None, season_year=None)`** — spray
  history for one field. `field_id` is exact — pass `field.id`, not a name.
- **`seasonal_total_applied(field_id, product, season_year)`** — fl oz/acre of
  one product already applied this season; compare against
  `max_seasonal_fl_oz_per_acre`.

## Label search — [retriever.py](retriever.py)

- **`search(query, *, product=None, k=4, fetch_k=20, lambda_mult=0.5)`** — the
  `k` most relevant, mutually non-redundant label chunks (cosine similarity,
  then MMR re-ranking; `lambda_mult` trades relevance at 1.0 against diversity
  at 0.0). Pass `product=product.name` to stay inside one label — usually what
  you want, since a restriction belongs to one product, not all five. An
  unknown name returns `[]`. Each chunk carries `product`, `epa_reg_no`, and
  `page` for citations. First call loads the embedding model (a few seconds).
- **`vector_store()`** — the underlying LangChain Chroma store, for
  `.as_retriever()` composition.
- **`rebuild()`** — drop and re-ingest `data/labels/`. Run
  `python -m data_layer.retriever` after changing the PDFs; currently 297 pages
  → 1,506 chunks. The store is gitignored, so everyone builds their own.

## Weather — [weather.py](weather.py)

- **`get_forecast(latitude, longitude, target_date)`** — Open-Meteo daily
  forecast for one point and date: high temp (°F), max wind speed (mph),
  dominant wind direction, precipitation probability. Raises
  `WeatherUnavailable` when the forecast can't be had — network failure, bad
  response, or a date beyond the ~16-day horizon. No fallback: an uncheckable
  spray date routes to insufficient information, never to a pass.

## Schema semantics — [schemas.py](schemas.py)

- **`None` on any `ProductLimits` limit means the label sets no such
  restriction** — skip that check, don't fail it. `allowed_traits` is `None`
  (never `[]`) for Delaro Complete and Paraquat, where trait tolerance is
  meaningless. `supported_crops` comes from the label's crop-use sections only,
  field and row crops only.
- **Compare growth stages by index into `SOYBEAN_STAGES`**, never as strings —
  `"V4" < "R1"` is `False` even though V4 comes first. Stage values are plain
  `str`, not validated against the tuple.
- **`TraitPackage`** members carry comments listing what each stack tolerates,
  which explains every `allowed_traits` list in `products.json`.

## Test fixtures

The records are seeded to trip specific rules, so the rule engine has real
cases to test against:

| Records | Outcome |
|---|---|
| F-02 (enlist_e3, V3) + Enlist One | Clean — trait OK, inside VE–R1, 0 applied |
| F-01 (xtendflex) + Enlist One | Trait violation |
| F-05 (conventional) + any herbicide | Fails all three |
| F-03 + Roundup PowerMax 3 | 64.0 applied against a 60.0 seasonal cap, 2 applications |
| F-08 (R5) + Roundup PowerMax 3 | Past the VE–R2 window |
| F-09 (310 ft) / F-03 (165 ft) | Tightest sensitive-site distances |
| any field + Delaro Complete | No trait restriction, no stage window |
| `get_forecast(..., today + 60d)` | `WeatherUnavailable` |

Traits: F-01/06/09 xtendflex · F-02/07/10 enlist_e3 · F-03/08 rr2x · F-04
libertylink · F-05 conventional.
