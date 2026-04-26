# AJ spec.md — `pul-catalog-mcp`

A FastMCP server that exposes the Princeton University Library (PUL) catalog as a small set of tools an LLM can call to search, browse, and fetch bibliographic records.

Status: draft v0.2. Both major design decisions (tool granularity and whether to ship a skill) are resolved; see §3 and §5.

---

## 1\. Background: what the catalog actually is

PUL's public catalog at `https://catalog.princeton.edu` runs on **Orangelight**, their fork of [Project Blacklight](https://projectblacklight.org/) (a Ruby-on-Rails discovery layer over Apache Solr). Source: [https://github.com/pulibrary/orangelight](https://github.com/pulibrary/orangelight).

Blacklight ships with a built-in JSON-API endpoint. There is no separate "developer API" to register for, no API key, and no published rate limit. The same URLs that serve the HTML UI return JSON when given `.json` (or `format=json`):

HTML:  https://catalog.princeton.edu/?q=plasma+physics

JSON:  https://catalog.princeton.edu/catalog.json?q=plasma+physics

HTML:  https://catalog.princeton.edu/catalog/9987870933506421

JSON:  https://catalog.princeton.edu/catalog/9987870933506421.json

This is the contract we're building against. It's well-suited to read-only tooling: stable URL shape, stable JSON-API envelope (Blacklight follows the JSON:API spec), public, no auth.

### What's covered

The catalog combines records from PUL's Alma ILS, the ReCAP shared collection (partner materials from Columbia, NYPL, Harvard, etc.), and theses and dissertations from DataSpace. Formats include books, journals, scores, manuscripts, maps, audio/video, theses, and more.

### What's *not* covered (out of scope for this MCP)

- **Article-level search** — articles, chapters, and database content live in PUL's "articles+" bento and are powered by a different backend (Summon / Primo). Out of scope for v1.  
- **Patron-account actions** — holds, renewals, fines. These require CAS authentication and are out of scope.  
- **Full-text** — the catalog returns metadata and links, not the contents of works.  
- **Princeton Public Library** (a separate institution at `catalog.princetonlibrary.org`). Different system entirely; ignore.

---

## 2\. The Blacklight JSON API, in just enough detail

### 2.1 Endpoints

| Purpose | Method | Path |
| :---- | :---- | :---- |
| Search | GET | `/catalog.json` |
| Single record (show) | GET | `/catalog/{id}.json` |
| Facet drill-down | GET | `/catalog/facet/{facet_field}.json` |
| Suggest (typeahead) | GET | `/catalog/suggest?q={prefix}` |

All return JSON. The `id` for a record is the Alma MMS ID (e.g. `9987870933506421`); shorter legacy bib IDs (e.g. `9987870`) also resolve.

### 2.2 Search parameters

Standard Blacklight query params (all optional):

| Param | Meaning |
| :---- | :---- |
| `q` | Query string. Supports phrases (`"..."`), boolean (`AND OR NOT`), wildcards (`*`), and exclusion (`-term`). |
| `search_field` | Which field to search. See §2.3. |
| `f[FACET][]` | Apply a facet filter. Repeatable. See §2.4. URL-encode the brackets. |
| `range[YEAR][begin]` / `range[YEAR][end]` | Date-range filter on `pub_date_start_sort`. |
| `sort` | `score desc, pub_date_start_sort desc, title_sort asc` (default by relevance) — see §2.5. |
| `per_page` | Results per page (default 10, cap at \~100). |
| `page` | 1-indexed page number. |

Composability rules:

- `q` defaults to `*:*` (match-all) if omitted, which is useful for pure facet browsing.  
- Multiple `f[X][]=A&f[X][]=B` against the *same* facet are OR'd. Filters across *different* facets are AND'd. (This matches Blacklight semantics; the catalog's help page also notes that facets added from the advanced search form are inclusive/OR.)  
- Boolean operators in `q` (`AND`, `OR`, `NOT`) must be uppercase.

### 2.3 Search fields (the `search_field=` values)

Pulled from the live catalog UI — `https://catalog.princeton.edu/help` and `/advanced`:

| `search_field` token | Label in UI | Notes |
| :---- | :---- | :---- |
| `all_fields` | Keyword (default) | Default if omitted. |
| `title` | Title (keyword) |  |
| `author` | Author (keyword) |  |
| `subject` | Subject (keyword) |  |
| `left_anchor` | Title starts with | Anchored to the start of the field; respects MARC 245 non-filing characters (skips initial articles like "The"). |
| `series_title` | Series title | Advanced search only. |
| `publisher` | Publisher | Advanced search only. |
| `notes` | Notes | Advanced search only. |
| `isbn` | ISBN |  |
| `issn` | ISSN |  |

There are also three *browse* indexes (alphabetic browse, not keyword search) exposed at separate paths — see §2.6.

The exact token strings above are derived from Orangelight's `CatalogController` configuration and the user-facing help page. We should verify them at implementation time by hitting `/catalog.json?search_field=X` and confirming we get a 200, and write down the canonical list as a fixture in `tests/fixtures/search_fields.json`.

### 2.4 Facets

Common facet field names (verify at implementation time):

| Facet field | What it constrains |
| :---- | :---- |
| `format` | Book, Journal, Score, Map, Manuscript, Audio, Video, Senior Thesis, etc. |
| `language_facet` | Language of the work |
| `author_s` | Author/creator |
| `subject_topic_facet` | LCSH topical subject |
| `subject_era_facet` | Era |
| `subject_geo_facet` | Geographic subject |
| `pub_date_start_sort` | Publication year (also accessible via `range[]`) |
| `location` | Library location (e.g. Firestone, Mendel Music, Marquand, ReCAP) |
| `advanced_location_s` | Holding library |
| `access_facet` | "In the Library" / "Online" |
| `recently_added_facet` | `weeks_2`, `months_2`, etc. |

Example: scores in German held in Mendel Music, published since 1990:

/catalog.json

  ?q=beethoven+symphonies

  \&f\[format\]\[\]=Score

  \&f\[language\_facet\]\[\]=German

  \&f\[location\]\[\]=Mendel%20Music%20Library

  \&range\[pub\_date\_start\_sort\]\[begin\]=1990

The *complete* facet list and value vocabularies are best discovered at runtime — Blacklight's `included` block in the JSON response enumerates which facets and values came back for any given search. We'll surface that via a `list_facets` tool.

### 2.5 Sort options

Standard Blacklight sort tokens (verify against the live API):

- `relevance` (default; aliases to `score desc, pub_date_start_sort desc, title_sort asc`)  
- `pub_date_sort desc` — newest first  
- `pub_date_sort asc` — oldest first  
- `title_sort asc` / `title_sort desc`  
- `author_sort asc`

### 2.6 The browse endpoints (alphabetic, not keyword)

Orangelight adds three browse indexes the keyword API doesn't replace:

/browse/names             \# author/name browse

/browse/subjects          \# subject browse

/browse/call\_numbers      \# LC call number browse

These accept `q` (the prefix to scroll to) and `rpp` (results per page) and return paginated lists. They're how you walk the alphabet — useful for "find all subjects starting with 'Ottoman'" or "what's shelved next to PN842 .S539". They render HTML by default; check whether `.json` works at implementation time. If not, we either screen-scrape (yuck) or omit browse from v1.

### 2.7 Response shape

A search response is JSON:API-shaped:

{

  "links": { "self": "...", "next": "...", "prev": "..." },

  "meta": {

    "pages": { "current\_page": 1, "next\_page": 2, "total\_pages": 988,

               "limit\_value": 10, "total\_count": 9871 }

  },

  "data": \[

    {

      "id": "9987870933506421",

      "type": "Document",

      "attributes": {

        "title\_display": "...",

        "author\_display": \["..."\],

        "format": \["Book"\],

        "pub\_date\_display": \["1987"\],

        "language\_facet": \["English"\],

        // many more fields, prefixed/suffixed by Solr type:

        // \*\_display (single value, for display)

        // \*\_facet   (string, for faceting)

        // \*\_t / \*\_tsim (text, searchable)

        // \*\_s / \*\_ssim (string)

      },

      "links": { "self": "https://catalog.princeton.edu/catalog/9987870933506421" }

    },

    ...

  \],

  "included": \[

    // facet results, search-field metadata, sort options

  \]

}

A single record (`/catalog/{id}.json`) returns `{"data": {...}, "included": [...]}` with the fuller field set including holdings/availability hints.

### 2.8 What we do NOT get from this endpoint

- **Real-time availability** (is this copy on the shelf? when is it due back?) is fetched separately by Orangelight from PUL's Bibdata service (`https://bibdata.princeton.edu`). v1 omits availability; we link to the catalog page instead.  
- **Holdings detail** (specific copy locations, call numbers per copy) — same story. Mention this limitation in the tool docstring.  
- **MARC** — available via `/catalog/{id}.marc` (binary) or `.marcxml`. v1 doesn't expose these; add later if needed.

---

## 3\. Tool surface

We expose a set of **typed, narrow tools** rather than a single flexible `search`. Each tool maps to a specific intent ("find by author", "find by subject", "browse the call-number shelf") and to a specific Blacklight `search_field` or browse index. Rationale:

- Tool names are themselves the model's hint about which one to call. A model picking between `search_author` and `search_subject` is making a choice it understands; a model picking between `field="author"` and `field="subject"` is filling in a string it has to remember.  
- Per-tool docstrings can be short, targeted, and include a worked example that's actually relevant to that tool.  
- Per-tool parameter validation is tighter (an ISBN tool can validate the check digit; a year-range tool can reject `end < begin`).  
- When a tool starts misbehaving in practice, we revise just that tool's docstring or shape without rippling.

The trade-off is more surface area for the host to load and a bit of duplication in the implementation. We mitigate the latter by funneling every tool through one private `_search()` helper that does the actual HTTP call.

### 3.1 The toolset

All search tools share a common return shape (§3.2) and a common set of optional refinement params: `format`, `language`, `location`, `online_only`, `year_range`, `sort`, `per_page`, `page`. The differences are in what `query` *means* and which `search_field` gets sent to Blacklight.

| Tool | Maps to | What `query` means |
| :---- | :---- | :---- |
| `search_keyword` | `search_field=all_fields` | Free-text across title, author, subject, notes, etc. |
| `search_title` | `search_field=title` | Words that should appear in the title. |
| `search_title_starts_with` | `search_field=left_anchor` | Anchored prefix of the title; skips MARC non-filing characters ("The", "A", "Le", etc.). |
| `search_author` | `search_field=author` | Author / creator name (any order). |
| `search_subject` | `search_field=subject` | LCSH-style subject heading or topic words. |
| `search_publisher` | `search_field=publisher` | Publisher name. |
| `search_series` | `search_field=series_title` | Series title. |
| `search_isbn` | `search_field=isbn` | ISBN-10 or ISBN-13. Validates check digit. |
| `search_issn` | `search_field=issn` | ISSN. Validates format. |
| `browse_names` | `/browse/names` | Alphabetic walk through the authority list of names. |
| `browse_subjects` | `/browse/subjects` | Alphabetic walk through the subject authority list. |
| `browse_call_number` | `/browse/call_numbers` | Walk the LC call-number shelf. Useful for "what's near PN842 .S539". |
| `get_record` | `/catalog/{id}.json` | Fetch full metadata for one MMS ID. |
| `list_facets` | `/catalog/facet/{field}.json` | Enumerate facet values, optionally constrained. |

Notes on the browse tools: they hit `/browse/{index}` and accept `q` (the prefix to scroll to) and `rpp`. **Verify at implementation time** whether they speak JSON; if not, drop them from v1 rather than scrape HTML.

### 3.2 Common refinement parameters

Every search tool accepts:

- `format` (str | list\[str\]) — `"Book"`, `"Journal"`, `"Score"`, `"Map"`, `"Manuscript"`, `"Audio"`, `"Video"`, `"Senior Thesis"`, etc. Sent as `f[format][]=...`. Multiple values OR.  
- `language` (str | list\[str\]) — e.g. `"English"`, `"French"`, `"Arabic"`. Sent as `f[language_facet][]=...`.  
- `location` (str | list\[str\]) — library location, e.g. `"Firestone Library"`, `"Mendel Music Library"`, `"Marquand Library"`, `"ReCAP"`.  
- `online_only` (bool) — shorthand for `f[access_facet][]=Online`.  
- `year_range` (tuple\[int | None, int | None\]) — inclusive `(begin, end)`. Sent as `range[pub_date_start_sort][begin]/[end]`. Validates `begin <= end` when both are set.  
- `sort` (Literal) — one of `"relevance"` (default), `"newest"`, `"oldest"`, `"title_asc"`, `"title_desc"`, `"author_asc"`. Translates to the underlying Blacklight sort tokens.  
- `per_page` (int, default 10, max 100), `page` (int, default 1).

### 3.3 Common return shape

{

  "total": 9871,

  "page": 1,

  "per\_page": 10,

  "results": \[

    {

      "id": "9987870933506421",

      "title": "...",

      "authors": \["..."\],

      "format": \["Book"\],

      "pub\_date": "1987",

      "language": \["English"\],

      "url": "https://catalog.princeton.edu/catalog/9987870933506421"

    },

    ...

  \],

  "facets": {

    // top facet values from this result set, for follow-up refinement

    "format": \[{"value": "Book", "count": 7234}, ...\],

    "language\_facet": \[...\],

    "location": \[...\]

  },

  "next\_page": 2 | null

}

The `facets` block is the key affordance: it tells the model "there were 9871 hits, here's how to narrow them" so a follow-up call can populate `format=` / `language=` / `location=` without guessing.

### 3.4 What we deliberately don't expose

- **A raw `search()` tool that takes a `field=` string.** The whole point of the typed split is to avoid that.  
- **Raw Solr params** (`fq`, `qf`, `pf`, custom `qt` handlers). They give more power but invite breakage when Princeton retunes their index. The named search fields and facets are the stable contract.  
- **Bookmarks, saved searches, email this record** — Blacklight UI features that require auth or a session.  
- **Free-form HTML scraping fallbacks.** If the JSON API doesn't return something, we tell the user and link to the page.

### 3.5 Implementation note

Despite the surface fan-out, internally there's one `_search(field, query, **refinements)` helper that all `search_*` tools delegate to. The typed tools are thin wrappers: parameter validation, a fixed `field` value, and a docstring tailored to that intent. Adding `search_call_number_keyword` later is a 10-line PR, not a refactor.

---

## 4\. Implementation notes

### 4.1 Stack

- **Python 3.11+**  
- **FastMCP** (`fastmcp`) for the MCP server scaffold  
- **httpx** for HTTP, with `httpx.AsyncClient(http2=True, timeout=15)` and retry on 5xx/429 via `tenacity`  
- **pydantic** v2 for parameter and response models

### 4.2 HTTP client conventions

- Single shared `AsyncClient` per server process.  
- `User-Agent: pul-catalog-mcp/0.1 (+contact-email-or-repo-url)` — be a good citizen; PUL has no published rate limit but also no obligation to serve us.  
- Retry: `stop_after_attempt(3)`, exponential backoff starting at 0.5s, retry only on 429/5xx and `httpx.TransportError`.  
- Local in-process LRU cache (e.g. `cachetools.TTLCache(maxsize=512, ttl=300)`) keyed on the canonical query URL. Cuts duplicate calls when the model iterates on filters.

### 4.3 Parameter encoding

Blacklight expects bracketed array params (`f[format][]=Book`). `httpx` handles this if we pass a `list[tuple[str, str]]` to `params=` rather than a `dict`. Build the encoded params in a small helper and unit-test it.

### 4.4 Field normalization

Solr field names leak implementation detail (`title_display`, `author_citation_display`, `pub_date_start_sort`). The tool layer should rename to: `title`, `authors`, `pub_date`, `language`, `format`, `subjects`, `url`. Keep the originals in a `_raw` sub-key for power users.

### 4.5 Errors

- `404` from `get_record` → return a structured "not found" object, don't raise. The model handles this better than a stack trace.  
- Network/5xx after retries → raise an MCP `ToolError` with a short diagnostic.  
- Empty result set is not an error — return `total: 0, results: []` plus any facets returned (often there are none) and a hint to broaden the query.

### 4.6 Tests

- **Unit:** parameter encoding, response normalization, sort/filter validation. Mock HTTP with `respx`.  
- **Integration (opt-in via env var):** small set of canonical queries hit the live endpoint, snapshot the structural shape (not the data, which changes). Run nightly, not on every PR.  
- **Fixtures:** capture one search response, one record response, one facet response, one empty response, one 404, one Unicode-heavy record (CJK, RTL, diacritics).

### 4.7 Project layout

pul-catalog-mcp/

├── spec.md                          \# this file

├── pyproject.toml

├── README.md

├── src/pul\_catalog\_mcp/

│   ├── \_\_init\_\_.py

│   ├── server.py                    \# FastMCP entrypoint, @mcp.tool defs

│   ├── client.py                    \# httpx wrapper, retries, cache

│   ├── models.py                    \# pydantic schemas

│   ├── normalize.py                 \# Solr-field \-\> nice-field renaming

│   └── fields.py                    \# canonical search\_field \+ facet lists

├── evals/                           \# see §5 — drives the skill/no-skill call

│   ├── prompts.yaml                 \# \~20 representative user requests

│   └── run\_eval.py

└── tests/

    ├── fixtures/

    └── test\_\*.py

---

## 5\. Skill: deferred until evals show it's needed

We're not writing a `SKILL.md` for v1. The typed-tool design from §3 is the first line of defense — tool names like `search_author` and `search_title_starts_with` carry intent the way a `field=` parameter doesn't, and per-tool docstrings can be tight and example-driven without a separate document.

That said, "tools alone are enough" is a hypothesis, not a conclusion. Blacklight has small quirks that could trip the model up — uppercase boolean operators, OR-within-facet vs. AND-across-facets, when to reach for `search_title_starts_with` vs. `search_title`, when to use `browse_subjects` instead of `search_subject`. We decide whether to add a skill by running a small eval *after* the MCP works end-to-end, not by guessing now.

### 5.1 The eval

`evals/prompts.yaml` holds \~20 user requests covering the failure modes we'd expect a skill to fix. Each entry has a prompt and a coarse-grained expectation about which tool(s) should fire and roughly what params:

\- id: known\_title\_full

  prompt: "Does Princeton have 'The Brothers Karamazov' by Dostoevsky?"

  \# NB: this is the title+author case from §6.1 — there's no clean

  \# "right" tool for this in v1. The eval should record what the model

  \# actually picks; if a single tool dominates and works, we may not

  \# need a dedicated find\_book(). If the model thrashes between

  \# search\_title, search\_author, and search\_keyword, that's the signal

  \# to add it.

  expect:

    tool\_in: \[search\_keyword, search\_title, search\_author\]

    params\_contain\_any: \["brothers karamazov", "dostoevsky"\]

    notes: "open case — see §6.1"

\- id: known\_title\_prefix

  prompt: "I'm looking for a book whose title starts with 'Algorithms to Live By'."

  expect:

    tool: search\_title\_starts\_with

\- id: topical\_with\_format\_narrowing

  prompt: "What scores does the library have for Beethoven symphonies?"

  expect:

    tool\_in: \[search\_keyword, search\_author, search\_subject\]

    params\_contain\_any: \["beethoven"\]

    refinement\_contains: {format: "Score"}

\- id: shelf\_neighbors

  prompt: "What's shelved near call number PN842 .S539 2006?"

  expect:

    tool: browse\_call\_number

\- id: boolean\_query

  prompt: "Books about activism but not in Indiana."

  expect:

    tool: search\_keyword

    query\_uses\_uppercase\_boolean: true

\# ...and so on, \~20 prompts covering author/subject/ISBN/ISSN/series/

\# online-only/year-range/cross-format cases.

The runner sends each prompt to the MCP host with our tools loaded (no skill), records which tool got called and with what params, and compares to the expectation. We tolerate fuzzy matches; the goal is to catch *systematic* misuse, not to pin down exact wording.

### 5.2 Decision rule

- **≥ 90% pass rate**: ship without a skill. Re-run the eval after any significant tool-shape change.  
- **75-89% pass rate**: tighten docstrings on the failing tools first, re-run. If that gets us above 90%, ship. If not, write the skill.  
- **\< 75% pass rate**: write the skill. The failing prompts become the skill's worked examples, which is the right way to write one anyway.

### 5.3 Other things the eval catches besides "do we need a skill"

- Tools whose names are confusable (the model keeps picking `search_keyword` when `search_subject` is right → rename or split).  
- Refinement params the model forgets to use (everyone passes `query` but no one passes `format` → bury the example deeper in the docstring, or reorder).  
- Params we shouldn't have shipped (no eval prompt ever uses `search_publisher` → maybe drop it, or it lives in advanced-only mode).

---

## 6\. Open questions for the next pass

1. **Combined "title words \+ author name" search.** This is one of the most common real user needs ("does Princeton have *Brothers Karamazov* by Dostoevsky?") and the current toolset doesn't have a clean answer for it. Three viable approaches when we revisit:  
     
   - A dedicated `find_book(title=None, author=None)` tool that uses Blacklight's multi-clause advanced-search URL syntax (`clause[0][field]=title&clause[0][query]=...&clause[1][field]=author&clause[1][query]=...&op=AND`) to AND the two fields together.  
   - Optional `author=` kwarg on `search_title` (and symmetric `title=` on `search_author`), implemented the same way under the hood.  
   - Lean on `search_keyword` and Blacklight's relevance ranking, which already boosts title and author matches. Often "good enough" but fails on titles with common words or authors with common names.

   

   We deferred this because it deserves its own eval pass — pasting "brothers karamazov dostoevsky" into `search_keyword` works surprisingly well in practice, and we shouldn't add a tool until we've measured how often it fails. The eval prompt set in §5.1 should include several known-item lookups to give us that signal.

   

2. Do we want `format=marcxml` exposure for users who want to round-trip records into Zotero / a reference manager? Easy to add as a `get_record_marc(id)` tool.  
     
3. Should the search tools accept an optional `fields` whitelist so callers can trim the response? (Saves tokens when the model is iterating through many results.)  
     
4. The `next_page` field in the response shape (§3.3) hands the model a pre-baked next-page indicator. Should we go further and return a full `next_call: {tool: "...", params: {...}}` blob so pagination is literally copy-paste? Risks coupling tool output to tool API.  
     
5. Worth adding `find_similar(id)` that does a Solr `more_like_this` query? Blacklight supports MLT but it's not always wired into the public endpoint — verify before promising it.  
     
6. Do `browse_names` / `browse_subjects` / `browse_call_number` actually speak JSON, or do we need to drop them from v1? First implementation task to verify.  
     
7. Should `search_isbn` / `search_issn` *normalize* the input (strip hyphens, validate check digit, accept ISBN-10 ↔ ISBN-13) or pass through raw? Lean toward normalize — librarians and end users paste both forms.

---

## 7\. References

- PUL catalog: [https://catalog.princeton.edu](https://catalog.princeton.edu)  
- PUL catalog help (search-field tokens, query syntax): [https://catalog.princeton.edu/help](https://catalog.princeton.edu/help)  
- PUL catalog advanced search (field list): [https://catalog.princeton.edu/advanced](https://catalog.princeton.edu/advanced)  
- Orangelight source: [https://github.com/pulibrary/orangelight](https://github.com/pulibrary/orangelight)  
- Blacklight JSON API: [https://github.com/projectblacklight/blacklight/wiki/JSON-API](https://github.com/projectblacklight/blacklight/wiki/JSON-API)  
- Blacklight configuration / Solr params: [https://workshop.projectblacklight.org/v7.11.1/apis/](https://workshop.projectblacklight.org/v7.11.1/apis/)  
- FastMCP: [https://github.com/jlowin/fastmcp](https://github.com/jlowin/fastmcp)

