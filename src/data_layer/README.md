# data_layer

Farm records, label knowledge, and weather — components 1–5 of
[system-spec.md](../../development_documentation/system-spec.md). Every function
returns Pydantic models from [schemas.py](schemas.py)

## Farm records — [records.py](records.py)

- **`list_fields()` / `list_products()` / `list_applications()`** — every row of
  the matching JSON file, validated.
- **`find_field(text)` / `find_product(text)`** — resolve free text to one
  record, or `None`. Ids match by exact equality, names by case-insensitive
  substring. A miss and an ambiguous match both return `None`, and it 
  means to ask the user which one they meant.
- **`applications_for(field_id, *, product=None, season_year=None)`** — spray
  history for one field. `field_id` is exact — pass `field.id`, not a name.
- **`seasonal_total_applied(field_id, product, season_year)`** — fl oz/acre of
  one product already applied this season; compare against
  `max_seasonal_fl_oz_per_acre`.

## Label search — [retriever.py](retriever.py)

- **`search(query, *, product=None, crop=None, k=4, fetch_k=20,
  lambda_mult=0.5)`** — the `k` most relevant, mutually non-redundant label
  chunks (cosine similarity, then MMR re-ranking). An unknown name returns `[]`.
  - **`product=product.name`** stays inside one label
  - **`crop=field.crop`** stays inside the directions that govern the crop in
    the ground. 
- **`vector_store()`** — the underlying LangChain Chroma store, for
  `.as_retriever()` composition.
- **`rebuild()`** — drop and re-ingest `data/labels/`. Run
  `python -m data_layer.retriever` after changing the PDFs; currently 297 pages
  → 1,480 chunks. The store is gitignored, so everyone builds their own.

## Label structure — [corpus.py](corpus.py)

A label is not a flat document, and treating it as one is how a citation ends up
pointing at the wrong crop. Ingest tags every chunk with where it sits:

- **EPA cover letters are dropped.** Every PPLS download opens with the agency's
  approval letter to the registrant.
- **`part`** — the top-level division of a master label, read from the running
  header. The Roundup master label is 171 pages: `I. DIRECTIONS FOR USE WITH
  FOOD AND FEED CROPS` runs to page 115, and `II. DIRECTIONS FOR USE ON
  INDUSTRIAL, TURF AND ORNAMENTAL SITES` covers 116–167. Blank on the labels
  that have no such division.
- **`section`** — nearest preceding heading (`7.5 Surfactants`). Best-effort and
  often blank; it describes a citation and no rule ever reads it.
- **`crop_scope`** — which crops a chunk may be cited for: `"non-crop"` under an
  industrial/turf part, `"general"` when no crop governs it, otherwise the crop
  names joined by `+`. Compare with **`scope_covers(scope, crop)`**.

  A chunk that names no crop takes the crop named above it **on the same page**,
  because that is how directions read — a crop heading, then the rates and
  intervals under it, which never repeat the name. Delaro's 35-day wheat
  pre-harvest interval says only "wheat" a few lines up, and scoring each chunk
  on its own 900 characters left it citable as a soybean restriction. The
  context resets at the page break, and product-wide topics
  (`GLOBAL_TOPIC_PATTERN`: storage, first aid, PPE, re-entry, drift, nozzles)
  stay `"general"` wherever they are printed — Enlist puts its boom-height limit
  directly under a list of drift-susceptible crops.

The filter cuts Roundup from 842 citable chunks to 340 for a soybean field,
while leaving the ~8 pages that carry the actual soybean directions intact.

## Weather — [weather.py](weather.py)

- **`get_forecast(latitude, longitude, target_date)`** — Open-Meteo daily
  forecast for one point and date: high temp (°F), max wind speed (mph),
  dominant wind direction, precipitation probability. Raises
  `WeatherUnavailable` when the forecast fails — network failure, bad
  response

## Schema semantics — [schemas.py](schemas.py)

- **`None` on any `ProductLimits` limit means the label sets no such
  restriction** — skip that check, don't fail it. `allowed_traits` is `None`
  for Delaro Complete and Paraquat, where trait tolerance is meaningless. 
  `supported_crops` comes from the label's crop-use sections only,
  field and row crops only.
- **`default_rate_fl_oz_per_acre` is a starting point, `max_` is the
  ceiling.** Use the default when the request names no rate. Each default
  is the lowest rate its label gives for the ordinary broadcast soybean use.
- **`FarmField.acres` The total acres in the field.** Can be used as a max or backup value if user does
  not provide information in the request. 
- **Compare growth stages with `stage_position(stage)`**, never as strings —
  `"V4" < "R1"` is `False` even though V4 comes first. It returns a season
  position (`VE`, `VC`, `V1`…`Vn`, `R1`…`R8`) and `None` for anything it does
  not recognise, which a caller must treat as uncheckable rather than in-window.
  `SOYBEAN_STAGES` is a listing of the stages the five labels name, not the
  ordering — stage values are plain `str` and are not validated against it.
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
