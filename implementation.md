# Simplified Implementation Plan

## 1. Goal

Build a small facts-only mutual fund FAQ assistant that:

- Scrapes only the five approved Groww pages.
- Stores every RAG stage so it can be demonstrated.
- Uses structure-aware chunking.
- Uses `sentence-transformers/all-MiniLM-L6-v2` for embeddings.
- Stores and retrieves chunks from ChromaDB.
- Uses Groq as the initial LLM provider.
- Answers in no more than three sentences.
- Includes exactly one approved source link in every response.
- Refuses investment advice, return comparisons, and sensitive-data requests.

## 2. Implementation Flow

```text
Create project
    ↓
Scrape five approved pages
    ↓
Extract and clean page content
    ↓
Load and validate extracted documents
    ↓
Create structure-aware chunks
    ↓
Generate MiniLM embeddings
    ↓
Store chunks and embeddings in ChromaDB
    ↓
Classify query and retrieve relevant chunks
    ↓
Generate and validate the answer
    ↓
Display answer, one citation, and source date in the UI
```

## 3. Phase 1: Create the Project Directory

### 3.1 Directory structure

Create this minimal structure:

```text
grow-chatbot/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── models.py
│   ├── scraper.py
│   ├── document_loader.py
│   ├── chunker.py
│   ├── embeddings.py
│   ├── vector_store.py
│   ├── retrieval.py
│   ├── guardrails.py
│   ├── llm.py
│   └── ui.py
├── config/
│   ├── config.yaml
│   └── sources.yaml
├── data/
│   ├── raw/
│   ├── extracted/
│   ├── chunks/
│   ├── chroma/
│   └── evaluations/
├── tests/
│   ├── fixtures/
│   ├── test_scraper.py
│   ├── test_document_loader.py
│   ├── test_chunker.py
│   ├── test_vector_store.py
│   ├── test_retrieval.py
│   └── test_guardrails.py
├── .env.example
├── .gitignore
├── requirements.txt
├── ingest.py
├── README.md
├── PRD.md
├── architecture.md
└── implementation.md
```

### 3.2 Python dependencies

Add these packages to `requirements.txt`:

```text
beautifulsoup4
chromadb
groq
httpx
pydantic
pydantic-settings
pyyaml
sentence-transformers
streamlit
pytest
```

Pin exact versions after confirming the combination works locally.

### 3.3 Environment configuration

Create `.env.example`:

```dotenv
LLM_PROVIDER=groq
LLM_MODEL=qwen/qwen3.8-27b
GROQ_API_KEY=
```

The model name must come from `.env`. Validate that the configured model is currently available in Groq before running the application.

Add `.env`, Python caches, model caches, ChromaDB data, and generated artifacts to `.gitignore`.

### 3.4 Application configuration

Create `config/config.yaml`:

```yaml
scraping:
  timeout_seconds: 20
  max_retries: 2
  follow_links: false

chunking:
  target_tokens: 400
  overlap_tokens: 50

embeddings:
  model: sentence-transformers/all-MiniLM-L6-v2
  batch_size: 32

vector_db:
  provider: chroma
  collection: groww_hdfc_mf_faq
  persist_directory: data/chroma

retrieval:
  top_k: 5
  score_threshold: 0.50

response:
  max_sentences: 3
  citation_count: 1
```

### 3.5 Phase output

- Project starts without import errors.
- Configuration loads successfully.
- Secrets are not committed.
- All data directories exist.

## 4. Phase 2: Scrape the Documents

### 4.1 Approved pages

Create `config/sources.yaml` with only these five ingestion URLs:

```yaml
sources:
  - source_id: SRC-01
    title: HDFC Mutual Fund
    scheme_id: hdfc_mutual_fund
    url: https://groww.in/mutual-funds/amc/hdfc-mutual-funds

  - source_id: SRC-02
    title: HDFC Large Cap Fund Direct Growth
    scheme_id: hdfc_large_cap_direct_growth
    url: https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth

  - source_id: SRC-03
    title: HDFC Flexi Cap Direct Plan Growth
    scheme_id: hdfc_flexi_cap_direct_growth
    url: https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth

  - source_id: SRC-04
    title: HDFC ELSS Tax Saver Fund Direct Plan Growth
    scheme_id: hdfc_elss_direct_growth
    url: https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth

  - source_id: SRC-05
    title: HDFC Mid Cap Fund Direct Growth
    scheme_id: hdfc_mid_cap_direct_growth
    url: https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth
```

### 4.2 Scraper responsibilities

Implement `app/scraper.py` to:

1. Read URLs only from `sources.yaml`.
2. Reject URLs not present in the source registry.
3. Fetch the page using `httpx` with a timeout and user agent.
4. Reject redirects to an unapproved URL.
5. Reject non-HTML responses.
6. Never follow links found inside a page.
7. Store the raw HTML in `data/raw/`.
8. Extract readable content using Beautiful Soup.
9. Remove scripts, styles, navigation, footer, cookie banners, and repeated page elements.
10. Store cleaned page data in `data/extracted/`.

### 4.3 Stored document format

Save one JSON document per source:

```json
{
  "source_id": "SRC-02",
  "title": "HDFC Large Cap Fund Direct Growth",
  "scheme_id": "hdfc_large_cap_direct_growth",
  "url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
  "retrieved_at": "2026-11-24T01:00:00Z",
  "content_hash": "sha256-value",
  "sections": [
    {
      "heading": "Fund details",
      "text": "Cleaned text from the page"
    }
  ]
}
```

### 4.4 Scraping command

Use `ingest.py` as the ingestion entry point:

```text
python ingest.py --stage scrape
```

### 4.5 Scraping edge cases

| Edge case | Expected behavior |
|---|---|
| Page timeout | Retry up to the configured limit, then record an error. |
| HTTP error | Record the status and do not create a valid extracted document. |
| Redirect outside the allowlist | Reject the response. |
| Non-HTML response | Reject the response. |
| Page contains many links | Do not request any linked page. |
| Page layout changes | Store an extraction warning and fail validation if content is empty. |
| One page fails | Keep prior valid data and report the failed source. |
| Duplicate content | Reuse the content hash and avoid duplicate downstream records. |

### 4.6 Phase output

- Five raw HTML files or explicit error records.
- Five cleaned JSON documents when all pages succeed.
- Source URL, retrieval date, and content hash stored with every document.
- Proof that only five URLs were requested.

## 5. Phase 3: Load and Validate the Documents

### 5.1 Purpose

The scraping phase writes cleaned JSON files to disk. Before chunking, the application must load those files, validate their structure, and convert them into a consistent in-memory document model.

This separates file and schema problems from chunking logic.

### 5.2 Document loader responsibilities

Implement `app/document_loader.py` to:

1. Find extracted JSON files in `data/extracted/`.
2. Load files using UTF-8 encoding.
3. Validate each file against the document model in `app/models.py`.
4. Confirm the source ID exists in `config/sources.yaml`.
5. Confirm the document URL matches the trusted source registry.
6. Confirm the title, retrieval date, content hash, and sections are present.
7. Remove empty sections and normalize whitespace.
8. Reject duplicate source IDs or conflicting document versions in the same run.
9. Return a list of validated document objects to the chunker.
10. Produce a loading summary with loaded, skipped, and failed document counts.

### 5.3 Document model

Use a typed model similar to:

```python
class DocumentSection(BaseModel):
    heading: str
    text: str


class LoadedDocument(BaseModel):
    source_id: str
    title: str
    scheme_id: str | None
    url: str
    retrieved_at: datetime
    content_hash: str
    sections: list[DocumentSection]
```

The chunker should accept `LoadedDocument` objects, not read arbitrary JSON files directly.

### 5.4 Loading command

Support an explicit validation stage:

```text
python ingest.py --stage load
```

The full ingestion flow becomes:

```text
python ingest.py --stage scrape
python ingest.py --stage load
python ingest.py --stage chunk
python ingest.py --stage index
```

`load` validates the extracted files and reports whether chunking can safely continue.

### 5.5 Loading edge cases

| Edge case | Expected behavior |
|---|---|
| Extracted directory is missing | Stop with a clear instruction to run scraping first. |
| No extracted files exist | Stop; do not run chunking. |
| JSON is malformed | Reject that document and report its safe filename/source ID. |
| Required field is missing | Reject the document during schema validation. |
| Source ID is not registered | Reject the document. |
| URL does not match the registry | Reject the document as untrusted. |
| Sections are empty | Reject the document or mark it invalid for chunking. |
| One section is empty | Remove that section and retain the valid sections. |
| Same source appears twice | Use an explicit run/version rule; never merge silently. |
| Encoding is invalid | Reject the file with a readable error. |

### 5.6 Phase output

- A validated list of `LoadedDocument` objects.
- Loading summary with expected source count, loaded count, failures, and warnings.
- No unregistered, malformed, empty, or URL-mismatched document reaches chunking.
- Chunking is blocked when required documents are invalid.

## 6. Phase 4: Chunk the Documents

### 6.1 Chunking strategy

Use structure-aware chunking instead of splitting only by character count.

Keep these facts together as atomic chunks:

- Expense ratio.
- Exit load and its conditions.
- Minimum SIP amount.
- ELSS lock-in period.
- Riskometer/risk level.
- Benchmark.
- Other label-value rows.

Use heading and section boundaries for narrative content. Only use the configured token size and overlap when a section is too large.

### 6.2 Chunking steps

Implement `app/chunker.py` to:

1. Receive validated `LoadedDocument` objects from `document_loader.py`.
2. Detect headings, paragraphs, lists, tables, and label-value pairs.
3. Create one chunk for each important atomic fact.
4. Group related narrative paragraphs under the same heading.
5. Split oversized narrative chunks near sentence boundaries.
6. Add overlap only to narrative chunks.
7. Add scheme and source context to every chunk.
8. Generate a deterministic chunk ID.
9. Store chunks in `data/chunks/chunks.jsonl`.

### 6.3 Chunk format

```json
{
  "chunk_id": "chk_hash",
  "source_id": "SRC-02",
  "scheme_id": "hdfc_large_cap_direct_growth",
  "section": "Fund details",
  "fact_type": "expense_ratio",
  "text": "Scheme: HDFC Large Cap Fund Direct Growth\nExpense ratio: <source value>",
  "source_url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
  "retrieved_at": "2026-11-24T01:00:00Z"
}
```

### 6.4 Chunking command

```text
python ingest.py --stage chunk
```

### 6.5 Chunking edge cases

| Edge case | Expected behavior |
|---|---|
| Label and value are separate HTML elements | Combine them into one atomic chunk. |
| Exit-load text has multiple conditions | Keep all conditions in the same chunk. |
| Section exceeds target size | Split at sentence/paragraph boundaries. |
| Section is very short | Keep it intact; do not add unrelated content. |
| Same fact appears twice | Keep one canonical chunk or mark duplicates. |
| No scheme ID | Use the AMC-level source metadata. |
| Empty section | Skip it. |
| Changed source content | Generate new chunk IDs where content changed. |

### 6.6 Phase output

- Human-readable `chunks.jsonl`.
- Every chunk has a source, scheme, section, fact type, and date.
- Important fact labels remain paired with their values.
- No navigation or cookie-banner chunks are present.

## 7. Phase 5: Generate Embeddings

### 7.1 Embedding model

Use:

```text
sentence-transformers/all-MiniLM-L6-v2
```

The same model and normalization settings must be used during ingestion and user-query retrieval.

### 7.2 Embedding implementation

Implement `app/embeddings.py` with:

```python
class EmbeddingService:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...
```

Required behavior:

- Load the model once.
- Embed chunks in configurable batches.
- Reject empty input.
- Return vectors with a consistent dimension.
- Store the exact model name in the index metadata.
- Fail clearly if the model cannot be loaded.

### 7.3 Embedding command

Embedding can be part of the index stage:

```text
python ingest.py --stage index
```

### 7.4 Embedding edge cases

| Edge case | Expected behavior |
|---|---|
| Model is unavailable | Abort indexing without modifying the active database. |
| Empty chunk text | Reject or skip with an explicit error. |
| Vector dimension changes | Reject the existing collection as incompatible. |
| One batch fails | Abort the staging build; keep the old valid index. |
| Chunk order changes | Use chunk IDs so records are still deterministic. |

### 7.5 Phase output

- One embedding per unique chunk.
- Embedding manifest with model name, dimension, chunk count, and build date.
- No partial index activated after failure.

## 8. Phase 6: Store Data in ChromaDB

### 8.1 ChromaDB collection

Use the configured persistent collection:

```text
groww_hdfc_mf_faq
```

Store:

- Chunk ID as the record ID.
- Chunk text as the document.
- Embedding vector.
- Source ID.
- Scheme ID.
- Section.
- Fact type.
- Source URL.
- Source retrieval date.
- Embedding model name.

### 8.2 Vector-store implementation

Implement `app/vector_store.py` with methods such as:

```python
class ChromaVectorStore:
    def upsert(self, chunks, embeddings) -> None:
        ...

    def search(self, query_embedding, top_k, filters=None):
        ...

    def health_check(self) -> bool:
        ...
```

### 8.3 Safe index build

1. Create a staging collection.
2. Upsert chunks using deterministic chunk IDs.
3. Verify the stored count matches the unique chunk count.
4. Retrieve sample records and compare their metadata.
5. Run a few known search queries.
6. Write an index manifest.
7. Activate the new collection only after all checks pass.
8. Keep the previous valid collection until the new one is ready.

### 8.4 Index manifest

Store the following in `data/chroma/index_manifest.json`:

```json
{
  "collection": "groww_hdfc_mf_faq",
  "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
  "embedding_dimension": 384,
  "chunk_count": 0,
  "source_ids": ["SRC-01", "SRC-02", "SRC-03", "SRC-04", "SRC-05"],
  "created_at": "2026-11-24T01:05:00Z",
  "status": "READY"
}
```

The actual build must replace the example `chunk_count` with the real non-zero count.

### 8.5 ChromaDB edge cases

| Edge case | Expected behavior |
|---|---|
| Same ingestion runs twice | Upsert by chunk ID; do not create duplicates. |
| Embedding model differs | Reject the index at startup. |
| Stored count is wrong | Do not activate the staging collection. |
| Collection is missing/corrupt | Mark the application not ready. |
| Chunk was removed | Build a fresh staging collection without it. |
| Metadata source is unknown | Reject that record. |

### 8.6 Phase output

- Persistent ChromaDB collection.
- Valid `READY` index manifest.
- Repeat ingestion does not create duplicates.
- Known questions retrieve relevant chunks.

## 9. Phase 7: Retrieval and Answer Logic

### 9.1 Query flow

Implement this order in `app/retrieval.py` and `app/guardrails.py`:

```text
Validate question
    ↓
Check for sensitive data
    ↓
Classify advice/performance/out-of-scope intent
    ↓
Resolve scheme and requested fact
    ↓
Embed the query
    ↓
Search ChromaDB with scheme filters
    ↓
Apply relevance threshold
    ↓
Generate answer from retrieved evidence
    ↓
Validate answer and attach one trusted citation
```

### 9.2 Scheme and fact resolution

Map common scheme-name variations to canonical IDs before retrieval. Detect these fact types:

```text
expense_ratio
exit_load
minimum_sip
lock_in
riskometer
benchmark
statement_process
general
```

If multiple schemes are possible, ask one concise clarification question instead of guessing.

### 9.3 Retrieval logic

1. Load the same embedding model used for the index.
2. Verify the index manifest is compatible.
3. Embed the question.
4. Apply a scheme metadata filter when a scheme is known.
5. Retrieve the configured top-k chunks.
6. Prefer chunks matching the requested fact type.
7. Remove results below the configured score threshold.
8. Reject chunks with unknown or disabled source IDs.
9. If no chunk remains, return `UNSUPPORTED_BY_SOURCES`.

The score threshold must be calibrated with test questions. Do not present a retrieval score as a user-facing confidence percentage.

### 9.4 LLM generation

Implement `app/llm.py` so the model receives only:

- User's safe, non-sensitive question.
- Canonical scheme/fact information.
- A small set of retrieved chunks.
- Chunk IDs and source IDs.
- Instructions to use only the supplied evidence.

Expected model output:

```json
{
  "category": "FACTUAL_SUPPORTED",
  "answer_text": "The factual answer in no more than three sentences.",
  "selected_source_id": "SRC-02",
  "evidence_chunk_ids": ["chk_hash"]
}
```

The model must not return the final source URL. Application code resolves the selected source ID to the URL in `sources.yaml`.

### 9.5 Response validation

Before displaying an answer, verify:

- The answer is supported by at least one retrieved chunk.
- Selected source ID belongs to the retrieved evidence.
- Source ID is in the approved registry.
- Answer contains no more than three sentences.
- Answer text contains no arbitrary URL.
- Answer contains no advice, recommendation, return comparison, or sensitive value.
- Exactly one citation is attached by the application.
- The source date comes from ingestion metadata.

If validation fails, show a safe facts-only fallback.

### 9.6 Deterministic responses

Use fixed templates instead of the LLM for:

- Investment-advice refusal.
- Buy/sell/hold/switch refusal.
- Return calculation/comparison refusal.
- Sensitive-data warning.
- Unsupported question.
- Ambiguous scheme clarification.
- LLM or vector database failure.

### 9.7 Retrieval edge cases

| Edge case | Expected behavior |
|---|---|
| No relevant chunks | Say the fact could not be verified; do not guess. |
| Correct fact from wrong scheme | Reject through scheme filter/source validation. |
| Multiple schemes named | Ask a clarification question. |
| Model selects an unrelated source | Reject the response. |
| Model produces an external URL | Strip/reject it and use a trusted source. |
| More than three sentences | Retry once with stricter instructions or use fallback. |
| LLM times out | Show deterministic service-unavailable response. |
| Index model mismatch | Disable factual answering until the index is rebuilt. |

### 9.8 Phase output

- Supported factual questions return grounded answers.
- Unsupported questions do not produce invented values.
- Every response includes exactly one approved link.
- All answers and refusals stay within three sentences.

## 10. Phase 8: Build the Streamlit UI

### 10.1 UI content

Implement `app/ui.py` with:

- Product title.
- Welcome message.
- Visible note: **Facts-only. No investment advice.**
- Three example questions.
- Text input.
- Submit button.
- Loading indicator.
- Answer/refusal card.
- One descriptive source link.
- `Last updated from sources: <date>`.

### 10.2 Suggested example questions

1. What is the expense ratio of HDFC Large Cap Fund Direct Growth?
2. What is the lock-in period of HDFC ELSS Tax Saver Fund?
3. What are the exit load and minimum SIP for HDFC Mid Cap Fund?

### 10.3 UI response states

Support these states:

```text
IDLE
LOADING
ANSWER
CLARIFICATION
REFUSAL
UNSUPPORTED
SENSITIVE_WARNING
ERROR
```

The UI must use the category returned by the query service. It must not independently decide whether an answer is safe.

### 10.4 Safe debug panel

For a local demo, optionally show:

- Response category.
- Scheme and fact IDs.
- Retrieved chunk IDs.
- Source IDs.
- Raw retrieval scores with metric labels.
- Index and prompt version.

Do not show:

- API keys.
- Raw chain-of-thought.
- Full system prompts.
- Sensitive-data matches.
- Stored user history.

Disable the debug panel by default in a public deployment.

### 10.5 Run command

```text
streamlit run app/ui.py
```

### 10.6 UI edge cases

| Edge case | Expected behavior |
|---|---|
| Empty input | Ask the user to enter a question. |
| Very long input | Reject it with a clear message. |
| Double submit | Disable submit while the request is running. |
| Backend not ready | Disable factual queries and show a setup message. |
| Long scheme/source name | Wrap text without breaking layout. |
| Narrow screen | Keep input, answer, and citation readable. |
| Unsafe HTML in input/output | Render escaped text only. |

### 10.7 Phase output

- Working local FAQ UI.
- Three example questions.
- All response states visible and understandable.
- Exactly one clickable approved citation per response.
- No raw chain-of-thought or secrets displayed.

## 11. Guardrails and Edge Cases

### 11.1 Guardrail order

Apply guardrails in this order:

1. Input length and empty-input validation.
2. Sensitive-data detection.
3. Advice, portfolio, transaction, and performance detection.
4. Scope and scheme ambiguity check.
5. Retrieval evidence threshold.
6. LLM structured-output validation.
7. Final sentence, citation, URL, safety, and PII validation.

Sensitive-data detection must happen before logging, embedding, retrieval, or any LLM call.

### 11.2 Guardrail behavior

| Input/problem | Category | Required behavior |
|---|---|---|
| PAN, Aadhaar, account number, OTP, email, or phone | `SENSITIVE_DATA` | Do not process or repeat the value; warn the user and provide one official help link. |
| “Should I invest?” | `ADVICE_OR_OPINION` | Refuse investment advice and provide one educational link. |
| “Should I buy/sell/switch?” | `ADVICE_OR_OPINION` | Refuse and explain the facts-only scope. |
| “Which fund is best?” | `ADVICE_OR_OPINION` | Refuse ranking/recommendation. |
| “Compare returns” | `PERFORMANCE_REQUEST` | Do not calculate or compare; link to an official factsheet/source. |
| Scheme not clear | `CLARIFICATION_REQUIRED` | Ask which approved scheme the user means. |
| Fact not in corpus | `UNSUPPORTED_BY_SOURCES` | Say it could not be verified; do not invent a value. |
| Unrelated topic | `OUT_OF_SCOPE` | State the mutual-fund FAQ scope. |
| Prompt injection | Existing safe category | Ignore the instruction and continue enforcing system rules. |
| Unknown model-generated URL | Validation failure | Reject it and use only a registry URL. |

### 11.3 Sensitive-data logging rule

Do not store raw user questions by default. If operational logging is enabled, record only:

- Timestamp.
- Response category.
- Anonymous trace ID.
- Canonical scheme/fact IDs.
- Stage latency.
- Safe error code.

Never record the detected sensitive value, full prompt, API key, or raw LLM response.

## 12. Test Cases

### 12.1 Scraping tests

| Test | Expected result |
|---|---|
| Load all five approved URLs | Five raw and cleaned artifacts are produced. |
| Page contains internal links | No linked page is requested. |
| Redirect to another domain/path | Request is rejected unless the exact final URL is approved. |
| Page times out | Bounded retry occurs, then an error is recorded. |
| HTML structure changes | Empty/invalid extraction fails validation. |
| Same page is scraped again unchanged | Same content hash is produced. |

### 12.2 Document-loading tests

| Test | Expected result |
|---|---|
| Load five valid extracted files | Five typed documents are returned. |
| Extracted directory is missing | Loading stops with a clear error. |
| JSON is malformed | The document is rejected before chunking. |
| Required metadata is missing | Schema validation fails. |
| Source ID or URL is unregistered | The document is rejected as untrusted. |
| Empty sections | The document is rejected or invalid sections are removed according to policy. |
| Duplicate source documents | Loading fails instead of merging silently. |

### 12.3 Chunking tests

| Test | Expected result |
|---|---|
| Expense-ratio label and value | Stored in one chunk. |
| Exit load with conditions | All conditions remain together. |
| Large narrative section | Split near sentence boundaries with configured overlap. |
| Repeated atomic fact | Duplicate is removed or explicitly marked. |
| Identical input run twice | Same chunk IDs are generated. |
| Empty/navigation section | No chunk is created. |

### 12.4 Embedding and ChromaDB tests

| Test | Expected result |
|---|---|
| Embed known chunks | One same-dimension vector per chunk. |
| Run indexing twice | Record count does not increase. |
| Query expense ratio | Relevant expense-ratio chunk ranks near the top. |
| Apply scheme filter | Chunks from other schemes are excluded. |
| Change embedding model | Compatibility check fails until the index is rebuilt. |
| Fail staging build | Previous active index remains usable. |

### 12.5 Retrieval tests

| Query | Expected category/behavior |
|---|---|
| Expense ratio for an approved named scheme | `FACTUAL_SUPPORTED` with the correct scheme source. |
| ELSS lock-in period | `FACTUAL_SUPPORTED` using the ELSS page. |
| Minimum SIP for a named scheme | `FACTUAL_SUPPORTED` when supported by the source. |
| Valid fact not found in chunks | `UNSUPPORTED_BY_SOURCES`; no guessed value. |
| “What is its expense ratio?” without context | `CLARIFICATION_REQUIRED`. |
| Question about an unapproved AMC | `OUT_OF_SCOPE` or unsupported. |

### 12.6 Advice and performance tests

| Query | Expected behavior |
|---|---|
| Should I invest in this fund? | Refuse advice. |
| Which HDFC fund is best? | Refuse ranking/recommendation. |
| Should I sell my current fund? | Refuse portfolio action. |
| Compare the returns of large cap and mid cap. | Refuse calculation/comparison. |
| How much should I invest? | Refuse allocation advice. |

The LLM and vector database should not be called for clear deterministic refusals.

### 12.7 Sensitive-data tests

Use only obviously synthetic test values.

| Input category | Expected behavior |
|---|---|
| PAN-like value | Warning; no echo, log, embedding, retrieval, or LLM call. |
| Aadhaar-like value | Same privacy short-circuit. |
| Email address | Same privacy short-circuit. |
| Phone number | Same privacy short-circuit. |
| OTP/passcode language with digits | Same privacy short-circuit. |
| Account-number language with digits | Same privacy short-circuit. |

Tests must assert that the synthetic value is absent from logs, traces, prompts, exceptions, and stored artifacts.

### 12.8 Response validation tests

| Generated problem | Expected behavior |
|---|---|
| Four-sentence answer | Retry once or use safe fallback. |
| Two citation URLs | Reject; attach exactly one trusted citation. |
| Source ID not in retrieved chunks | Reject. |
| Arbitrary external URL | Reject. |
| Advice added to a factual answer | Reject. |
| Unsupported factual value | Reject through evidence validation. |
| Missing source date | Reject or return setup/service fallback. |

### 12.9 UI tests

- Disclaimer is visible.
- Three example questions work.
- Submit is disabled during processing.
- Every response shows exactly one source link.
- Source date is displayed.
- Sensitive input is not repeated.
- Debug panel is disabled by default.
- Input and source links are keyboard accessible.
- Narrow-screen layout remains readable.

## 13. End-to-End Acceptance Checklist

- [ ] Project installs and configuration loads.
- [ ] Only the five approved pages are scraped.
- [ ] Raw and cleaned documents are stored explicitly.
- [ ] Extracted documents are loaded and schema-validated before chunking.
- [ ] Structure-aware chunks are readable and source-linked.
- [ ] MiniLM embeddings are generated for every chunk.
- [ ] ChromaDB stores one record per unique chunk.
- [ ] Repeated ingestion creates no duplicates.
- [ ] Query and ingestion use the same embedding model.
- [ ] Supported questions retrieve the correct scheme evidence.
- [ ] Unsupported questions do not produce invented facts.
- [ ] Advice and performance questions are refused.
- [ ] Sensitive data is not logged, embedded, retrieved, or sent to the LLM.
- [ ] Every response contains exactly one approved source link.
- [ ] Every answer is no more than three sentences.
- [ ] Source update date is displayed.
- [ ] Streamlit UI shows the disclaimer and example questions.
- [ ] Automated tests pass.

## 14. Recommended Build Order

Implement and verify in this order:

1. Create directories, dependencies, configuration, and data models.
2. Build and test the exact-allowlist scraper.
3. Load and validate extracted documents into typed objects.
4. Build and manually review chunking.
5. Add MiniLM embeddings.
6. Add staging and active ChromaDB collections.
7. Calibrate retrieval with labelled questions.
8. Add sensitive-data and intent guardrails.
9. Add Groq generation and strict response validation.
10. Build the Streamlit UI.
11. Run all edge cases, acceptance tests, and the demo flow.

Do not begin LLM prompt tuning until the extracted documents, chunks, and retrieval results are correct.

