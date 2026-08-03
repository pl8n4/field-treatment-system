# data_layer

Components 1–5 of [system-spec.md](../../development_documentation/system-spec.md): label corpus, vector store,
retriever, farm records, weather. Everything returns Pydantic models from
[schemas.py](schemas.py).

## records.py

`list_fields()`, `list_products()`, and `list_applications()` each return every row
of the matching JSON file as a validated tuple. Parsed once and cached, so call
them freely.

**`find_field(name_or_id) -> FarmField | None`**

Resolves free text to one field, matching case-insensitively against both `id` and
`name`, partial matches included. Returns `None` when nothing matches and also when
several things do — `find_field("Hartley")` hits Hartley North and Hartley South,
so it refuses rather than picking one. Both outcomes mean the same thing to you:
there isn't enough to proceed on, so ask which field was meant.

**`find_product(name) -> ProductLimits | None`**

Same resolution against product names. `find_product("Enlist")` works because only
one product contains that string; anything matching two products returns `None`.

**`applications_for(field_id, *, product=None, season_year=None) -> list[Application]`**

Spray history for one field, narrowed to a product and/or a season when you pass
them. `field_id` is an exact match — pass `field.id`, not a name.

**`seasonal_total_applied(field_id, product, season_year) -> float`**

Sums `rate_fl_oz_per_acre` across that field's applications of one product in one
season. This is the number to compare against `max_seasonal_fl_oz_per_acre`.
`product` is the exact `ProductLimits.name`.

## retriever.py

**`search(query, *, product=None, k=4, fetch_k=20, lambda_mult=0.5) -> list[LabelChunk]`**

Semantic search over the chunked label PDFs. Pulls `fetch_k` chunks by cosine
similarity, then MMR re-ranks them down to `k` that are relevant *and* not
redundant with each other; `lambda_mult` trades relevance (1.0) against diversity
(0.0).

`product` narrows the search to one label's chunks, which is usually what you want
— a temperature restriction belongs to one product, not to all five. It's an exact
match on `ProductLimits.name`, so pass `product.name`. A name that doesn't match
returns `[]` rather than raising.

Each `LabelChunk` carries `product`, `epa_reg_no`, and `page`, which is what you
cite. First call loads the embedding model and takes a few seconds; cached after.

**`vector_store() -> Chroma`**

The underlying LangChain store, if you need `.as_retriever()` to compose it into a
chain. Ingests the corpus on first call when the store is empty.

**`rebuild() -> int`**

Drops the collection and re-ingests `data/labels/`. Returns the chunk count.

## weather.py

**`get_forecast(latitude, longitude, target_date) -> WeatherForecast`**

Daily forecast for one point and date from Open-Meteo: high temp (°F), max wind
speed (mph), dominant wind direction (degrees), and precipitation probability.
Those are the values the wind, temperature, and buffer rules read.

Raises `WeatherUnavailable` on network failure, an error response, or a date
outside Open-Meteo's ~16-day horizon. There's no fallback and no cached value — a
spray date that far out genuinely can't be checked, so it should route to
insufficient information rather than being treated as a pass.

## schemas.py

**`ProductLimits`** holds one label's rules as structured numbers. `None` on any
limit means the label sets no such restriction, so skip that check rather than
failing it. That includes `allowed_traits`, which is `None` for Delaro Complete (a
fungicide) and Paraquat (a harvest-aid desiccant applied to kill the crop) — trait
tolerance is meaningless for both. It is never an empty list.

**`SOYBEAN_STAGES`** is the growth-stage order: `VE, VC, V1…V8, R1…R8`. Compare
stages by index into this tuple, never as strings — `"V4" < "R1"` is `False` even
though V4 comes first. Stage values on `FarmField` and `ProductLimits` are plain
`str` and aren't validated against it.

**`TraitPackage`** enumerates the herbicide-tolerance stacks. The comment on each
member lists what that stack tolerates, which is what explains every
`allowed_traits` list in `products.json`.

## Test fixtures

Records that already trip specific rules, so the rule engine has cases to test
against without inventing data.

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

## Rebuilding

Run `python -m data_layer.retriever` after changing `data/labels/`. Currently 297
pages → 1,417 chunks. The store is gitignored, so everyone builds their own.
