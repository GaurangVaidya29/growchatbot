# Product Requirements Document: Groww Mutual Fund FAQ Assistant

## 1. Document Control

| Field | Value |
|---|---|
| Product | Groww Mutual Fund FAQ Assistant |
| Status | Draft for implementation |
| Version | 1.0 |
| Date | 24 November 2026 |
| Source | `Problem Statement.txt` |
| Primary use case | Facts-only FAQ assistant backed by a small, explicit RAG corpus |

## 2. Product Summary

Build a small retrieval-augmented generation (RAG) assistant that answers factual questions about a defined set of HDFC mutual fund schemes. The assistant must use only approved public sources, answer in no more than three sentences, and include exactly one clear source link in every response.

The assistant must not provide investment advice, portfolio recommendations, buy/sell opinions, return calculations, or performance comparisons. Questions outside the factual scope must receive a polite refusal plus a relevant official educational link.

The prototype must expose and persist the output of every RAG stage—loading, chunking, embedding, indexing, retrieval, and generation—so the implementation can be demonstrated and evaluated stage by stage.

## 3. Problem Statement

Retail investors and support/content teams repeatedly need simple facts such as a scheme's expense ratio, exit load, minimum SIP amount, lock-in period, riskometer, benchmark, and statement-download instructions. Finding and validating these details across public pages takes time, while general-purpose assistants may provide uncited, stale, or advisory responses.

The product should make approved facts easy to retrieve while maintaining source transparency and a strict boundary between factual information and investment advice.

## 4. Goals

1. Answer supported mutual fund questions accurately from the approved corpus.
2. Provide exactly one clickable source URL with every answer.
3. Keep each user-facing answer concise: a maximum of three sentences, excluding UI labels.
4. Identify advice-seeking, portfolio, performance-comparison, and sensitive-data requests and respond safely.
5. Make each RAG stage explicit, persisted, inspectable, and reproducible for demonstration.
6. Allow the embedding model, vector database, LLM provider, and LLM model to be changed through configuration without changing application logic.
7. Deliver a small, usable prototype with setup documentation and evaluation examples.

## 5. Non-Goals

- Investment advice or scheme recommendations.
- Buy, sell, hold, switch, allocation, or portfolio suitability decisions.
- Return calculations, projections, rankings, or performance comparisons.
- Transactions, account access, order placement, or portfolio tracking.
- Collection, validation, or storage of personal or financial identifiers.
- Crawling the internal links found on the five defined ingestion pages.
- Coverage of AMCs or schemes outside the approved initial scope.
- Real-time NAV, market-price, or portfolio data unless added in a future, separately approved scope.

## 6. Target Users

### 6.1 Retail mutual fund users

Users comparing basic scheme facts or looking for general process information such as how to download a statement.

### 6.2 Support and content teams

Teams answering repetitive factual mutual fund questions that need short, consistent, source-backed responses.

### 6.3 Demo evaluators and developers

Reviewers who need to inspect every stage of the RAG pipeline and verify the relationship between source content, chunks, retrieval results, and the final response.

## 7. Initial Content Scope

Only the following five pages may be scraped during the initial ingestion. The crawler must not follow or scrape links found inside these pages.

| ID | Content type | Scheme/page | Approved ingestion URL |
|---|---|---|---|
| SRC-01 | AMC overview | HDFC Mutual Fund | https://groww.in/mutual-funds/amc/hdfc-mutual-funds |
| SRC-02 | Large Cap | HDFC Large Cap Fund Direct Growth | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth |
| SRC-03 | Flexi Cap | HDFC Flexi Cap Direct Plan Growth | https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth |
| SRC-04 | ELSS | HDFC ELSS Tax Saver Fund Direct Plan Growth | https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth |
| SRC-05 | Mid Cap | HDFC Mid Cap Fund Direct Growth | https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth |

Additional official public URLs may be referenced for educational refusals, factsheets, statement-download instructions, or regulatory explanations when required. These must be limited to official Groww, AMC, AMFI, or SEBI pages, documented in the source list, and must not silently expand the five-page scheme-ingestion scope.

## 8. Supported Question Types

The initial release should answer factual questions when the answer exists in the approved corpus, including:

- Expense ratio.
- Exit load.
- Minimum SIP amount.
- ELSS lock-in period.
- Riskometer or risk level.
- Scheme benchmark.
- Basic AMC or scheme facts present on an approved page.
- How to download a capital-gains statement or another supported statement, using an approved official process page.

Example questions shown in the UI:

1. “What is the expense ratio of HDFC Large Cap Fund Direct Growth?”
2. “What is the lock-in period for the HDFC ELSS fund?”
3. “What are the exit load and minimum SIP for HDFC Mid Cap Fund?”

## 9. Conversation and Safety Policy

### 9.1 Answer policy

The assistant must:

- Identify the exact fact and scheme requested.
- Retrieve evidence before composing an answer.
- Answer only when the retrieved evidence directly supports the requested fact.
- Use the value and qualifiers shown in the source; it must not infer missing values.
- Name the scheme when needed to remove ambiguity.
- Use no more than three sentences.
- Include exactly one clear, clickable source link.
- Display `Last updated from sources: <date>` with the answer. This label is UI metadata and is not counted toward the three-sentence answer limit.

If multiple retrieved chunks support the answer, the assistant should cite the most direct primary page rather than emit multiple URLs.

### 9.2 Advice and opinion refusal

The assistant must refuse questions such as:

- “Should I invest in this fund?”
- “Which fund is best?”
- “Should I buy, sell, hold, or switch?”
- “Is this fund right for my portfolio?”
- “How much should I invest?”

Refusal pattern:

> I can help with factual scheme information, but I can’t provide investment advice or portfolio recommendations. You can review this official educational resource: <one relevant official link>.

### 9.3 Performance requests

The assistant must not calculate, project, rank, or compare returns. When asked about performance, it should state the limitation and link to the relevant official factsheet or approved scheme page without making a performance claim.

### 9.4 Unsupported or ambiguous questions

- If a requested fact is not present in the approved sources, say that it could not be verified from the available sources and provide the most relevant approved source link.
- If the scheme or fact is ambiguous, ask one concise clarifying question instead of guessing. The clarifying response should still include a relevant source link to meet the global citation requirement.
- If a question is outside the AMC/scheme scope, state the current scope and provide one relevant scope or educational link.

### 9.5 Sensitive data policy

The assistant must not request, accept for processing, log, embed, or store PAN, Aadhaar, account numbers, OTPs, email addresses, or phone numbers. If such data is detected, the system must:

1. Stop normal retrieval and generation.
2. Warn the user not to share personal or financial information.
3. Avoid echoing the detected value in logs or the response.
4. Store only a redacted safety-event category if operational logging is enabled.
5. Include one official safety/help link in the response.

## 10. User Experience Requirements

### 10.1 Initial screen

The compact UI must show:

- A welcome line explaining what the assistant can answer.
- Three clickable example questions.
- The visible disclaimer: **“Facts-only. No investment advice.”**
- A text input and submit control.

### 10.2 Answer presentation

Each answer must display:

- The concise answer text.
- One source link with a descriptive label such as `Source: HDFC Large Cap Fund Direct Growth`.
- `Last updated from sources: <date>` based on the ingestion metadata, not the current chat date.

The answer must not show raw model chain-of-thought. An optional demo/debug panel may show source document IDs, chunk text, similarity scores, and pipeline artifacts.

### 10.3 States

The UI must provide clear states for loading, successful answer, clarification required, refusal, unsupported question, sensitive-data warning, and system error.

## 11. Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-01 | Ingest only the five approved scheme/AMC URLs and do not follow internal links. | Must |
| FR-02 | Store the raw response and extraction metadata for every source. | Must |
| FR-03 | Extract readable page content while preserving headings, labels, values, tables/lists where possible, and canonical source URLs. | Must |
| FR-04 | Split extracted content using a structure-aware strategy appropriate to the page data. | Must |
| FR-05 | Persist chunks and their metadata before embedding. | Must |
| FR-06 | Generate embeddings with the configured model; default: `sentence-transformers/all-MiniLM-L6-v2`. | Must |
| FR-07 | Store embeddings in the configured vector database; default: ChromaDB. | Must |
| FR-08 | Use the same configured embedding model and vector collection for ingestion and retrieval. | Must |
| FR-09 | Retrieve and rank relevant chunks for each eligible factual query. | Must |
| FR-10 | Generate an answer only from retrieved evidence and include exactly one citation URL. | Must |
| FR-11 | Route advice, performance, out-of-scope, ambiguous, and sensitive-data inputs to the appropriate safe response. | Must |
| FR-12 | Enforce a maximum of three sentences for answer/refusal copy. | Must |
| FR-13 | Show the source-refresh date with every response. | Must |
| FR-14 | Keep provider/model settings in configuration and secrets in `.env`. | Must |
| FR-15 | Support Groq as the initial LLM provider and allow future adapters for Gemini, OpenAI, Anthropic, and Mistral. | Must/Should |
| FR-16 | Persist inspectable artifacts from every RAG stage. | Must |
| FR-17 | Provide a debug/demo view or files that connect a query to retrieved chunks, scores, source, and final response. | Should |
| FR-18 | Record non-sensitive operational errors and pipeline timing without storing raw PII. | Should |

## 12. RAG Pipeline Requirements

### 12.1 Stage 1: Data loading

For each approved URL, store:

- `source_id`
- Requested URL and canonical URL
- Page title and scheme name
- HTTP status
- Retrieval timestamp
- Raw HTML or an equivalent immutable raw snapshot
- Content checksum
- Parser version
- Load status/error

The loader must use a fixed allowlist and must not behave as a recursive crawler.

### 12.2 Stage 2: Extraction and chunking

Use structure-aware, field-oriented chunking because the source pages contain compact labelled facts and sections. Preferred behavior:

1. Preserve atomic label-value pairs such as expense ratio, minimum SIP, exit load, lock-in, risk level, and benchmark in one chunk.
2. Use page headings and section boundaries before token-length boundaries.
3. Keep table rows or list items intact.
4. Add a small configurable overlap only for narrative sections; do not duplicate independent fact rows unnecessarily.
5. Attach the source URL, source ID, scheme name, section heading, fact type, extraction date, and chunk index to every chunk.

Initial configuration defaults may use a target of 300–500 tokens and 50-token overlap for narrative text, but the implementation must validate these values against the extracted page structure and expose them in configuration.

### 12.3 Stage 3: Embedding

- Default model: `sentence-transformers/all-MiniLM-L6-v2`.
- Embed normalized chunk text, not raw HTML.
- Store embedding model name and model/version metadata with the index manifest.
- Rebuild the collection when the embedding model or incompatible chunking configuration changes.
- Batch size and device must be configurable.

### 12.4 Stage 4: Vector storage

- Default vector database: ChromaDB.
- Use a configurable collection name and persistence directory.
- Store chunk text, vector, source URL, scheme, section, fact type, extraction date, and configuration fingerprint.
- Make indexing idempotent using deterministic chunk IDs or upserts.
- Prevent mixing embeddings from different models in one collection.

### 12.5 Stage 5: Retrieval

- Use the same embedding model as ingestion.
- Retrieve a configurable top `k` set of chunks.
- Apply metadata filters when a scheme is recognized.
- Return similarity scores and source metadata for inspection.
- Apply a configurable relevance threshold.
- If no result crosses the threshold, use the unsupported-answer path rather than guessing.

### 12.6 Stage 6: Classification and generation

Before generation, classify the request into one of:

- `FACTUAL_SUPPORTED`
- `CLARIFICATION_REQUIRED`
- `ADVICE_OR_OPINION`
- `PERFORMANCE_REQUEST`
- `OUT_OF_SCOPE`
- `SENSITIVE_DATA`
- `UNSUPPORTED_BY_SOURCES`

For supported questions, the LLM prompt must instruct the model to use only the supplied context, avoid calculations or recommendations, obey the sentence limit, and return a structured result containing answer text, selected source ID, and response category. The application—not the model alone—must validate the selected source ID and construct the final clickable URL from trusted metadata.

### 12.7 Stage 7: Validation

Before displaying a response, validate that:

- The category is allowed.
- The answer contains no more than three sentences.
- Exactly one trusted source link is attached.
- The link belongs to the approved source registry.
- A supported answer has retrieved evidence.
- Restricted advice or performance language is absent.
- No sensitive value is present in logs or generated output.

On validation failure, return a safe fallback with one approved help/source link and log the non-sensitive reason.

## 13. Explicit Artifact Storage

The prototype should persist artifacts in a human-inspectable layout such as:

```text
data/
  raw/                 # one immutable source snapshot per URL
  extracted/           # cleaned page-level content
  chunks/              # JSONL/JSON chunks with metadata
  embeddings/          # manifest and optional exported vectors
  chroma/              # persistent ChromaDB collection
  retrieval_runs/      # redacted demo traces: query, chunk IDs, scores
  evaluations/         # sample Q&A results and pass/fail output
```

Secrets, raw user conversations, and sensitive user input must never be written into these artifacts.

## 14. Configuration and Secrets

Non-secret settings must live in a configuration file (for example, `config.yaml`). Environment-specific secrets and model selection must be read from `.env`.

Illustrative configuration:

```yaml
ingestion:
  allowed_urls_file: sources.yaml
  follow_links: false
  refresh_policy: manual

chunking:
  strategy: structure_aware
  target_tokens: 400
  overlap_tokens: 50

embeddings:
  provider: sentence_transformers
  model: sentence-transformers/all-MiniLM-L6-v2
  batch_size: 32

vector_db:
  provider: chroma
  collection: groww_hdfc_mf_faq
  persist_directory: data/chroma

retrieval:
  top_k: 5
  score_threshold: 0.50

llm:
  provider: ${LLM_PROVIDER}
  model: ${LLM_MODEL}
  temperature: 0

response:
  max_sentences: 3
  citation_count: 1
```

Required `.env` variables for the initial provider:

```dotenv
LLM_PROVIDER=groq
LLM_MODEL=qwen/qwen3.8-27b
GROQ_API_KEY=
```

The supplied Groq model identifier must be treated as configurable and verified against the provider's available model catalogue during implementation. Future provider adapters may use keys such as `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and `MISTRAL_API_KEY`; these providers are not required to be fully implemented in the first prototype unless separately prioritized.

`.env` must be excluded from version control. A `.env.example` with empty values must be supplied.

## 15. High-Level Architecture

```text
Approved URL allowlist
        |
        v
Loader -> Raw snapshots -> Extractor -> Structured chunks
                                           |
                                           v
                              MiniLM embeddings -> ChromaDB
                                                       |
User query -> PII/scope classifier -> Query embedding -> Retrieval
     |                                                   |
     +------ safe refusal/clarification                  v
                                               Grounded LLM response
                                                       |
                                               Policy/link validator
                                                       |
                                                       v
                                             Concise cited answer
```

## 16. Non-Functional Requirements

### 16.1 Grounding and correctness

- Factual values must be traceable to retrieved text from an approved source.
- The system must not generate a factual value when evidence is missing.
- Source freshness must be visible to the user.

### 16.2 Privacy and security

- Do not retain raw user input by default.
- Redact sensitive patterns before any optional logging or tracing.
- Keep API keys server-side and out of prompts, browser code, source files, and logs.
- Use an explicit URL allowlist for ingestion and displayed citations.
- Treat scraped page content as data, never as executable instructions.

### 16.3 Reliability

- Ingestion should be idempotent and resumable.
- A failure on one source must not corrupt previously indexed sources.
- Every stored artifact must include enough version metadata to reproduce the run.
- The application must provide a clear fallback when the LLM or vector database is unavailable.

### 16.4 Performance

Suggested prototype targets:

- Median end-to-end answer latency: under 5 seconds, excluding cold start.
- Retrieval latency: under 1 second on the local five-page corpus.
- Ingestion must complete without duplicate chunks on repeated runs with unchanged inputs.

### 16.5 Accessibility and clarity

- Source links and example questions must be keyboard accessible.
- Status and error text must not rely on color alone.
- Use plain language and preserve scheme names exactly.

## 17. Success Metrics

The prototype is considered successful when the evaluation set demonstrates:

- **Citation coverage:** 100% of displayed responses contain exactly one approved source link.
- **Evidence grounding:** at least 90% of in-scope factual test questions are answered correctly and supported by the cited page.
- **Advice safety:** 100% of advice/portfolio prompts in the safety test set are refused.
- **Performance safety:** 100% of calculation, projection, ranking, and return-comparison prompts avoid performance claims.
- **PII safety:** 100% of defined sensitive-data tests trigger the warning path and do not persist the supplied value.
- **Conciseness:** 100% of responses comply with the three-sentence limit.
- **Pipeline transparency:** every demo query can be traced to stored ingestion, chunk, retrieval, and response artifacts.

These are initial acceptance targets and may be adjusted after the first labelled evaluation run.

## 18. Phased Implementation Plan

### Phase 1: Source registry and loading

- Create the five-URL allowlist.
- Fetch and persist raw source snapshots and metadata.
- Confirm that internal links are not followed.
- Produce a source-load report.

**Exit criterion:** all five allowed pages have a stored snapshot or an explicit, inspectable error record; no unapproved URL has been fetched.

### Phase 2: Extraction and chunking

- Extract clean content and labelled fund facts.
- Implement structure-aware chunking.
- Persist chunks as inspectable JSON/JSONL.
- Review chunks for broken label-value pairs and missing source metadata.

**Exit criterion:** each indexed chunk is readable, independently attributable, and contains its source and scheme metadata.

### Phase 3: Embedding and ChromaDB indexing

- Embed chunks using `sentence-transformers/all-MiniLM-L6-v2`.
- Persist the model/configuration manifest.
- Upsert chunks into ChromaDB.
- Add index inspection and repeat-run checks.

**Exit criterion:** a repeated unchanged ingestion creates no duplicates, and test queries retrieve relevant chunks.

### Phase 4: Retrieval and factual answering

- Implement query embedding, scheme recognition, metadata filtering, top-k retrieval, and thresholding.
- Integrate Groq using provider/model values from `.env`.
- Generate structured, evidence-only answers.
- Enforce trusted citation construction and sentence limits.

**Exit criterion:** supported test questions return grounded answers with exactly one valid source link.

### Phase 5: Safety routing and privacy

- Implement advice, performance, out-of-scope, ambiguity, and unsupported-source routing.
- Add sensitive-data detection/redaction before logging, retrieval, or generation.
- Add deterministic safe fallbacks.

**Exit criterion:** all defined negative and privacy tests follow the correct route without exposing or storing sensitive values.

### Phase 6: UI, evaluation, and packaging

- Build the tiny UI and optional debug/demo panel.
- Add example questions, disclaimer, citation, and source date.
- Run and document the sample Q&A evaluation.
- Complete README, source list, and demo/hosting deliverables.

**Exit criterion:** the prototype is reproducible from the README and all submission artifacts are present.

## 19. Acceptance Criteria

### AC-01: Supported factual answer

Given an in-scope question whose answer exists in the approved sources, when the user submits it, then the assistant returns a fact supported by retrieved text, uses no more than three sentences, includes exactly one approved source link, and shows the source update date.

### AC-02: No fabricated answer

Given an in-scope question whose answer cannot be verified in the corpus, when the user submits it, then the assistant states that the fact could not be verified and does not invent a value.

### AC-03: Advice refusal

Given a buy/sell, recommendation, suitability, allocation, or portfolio question, when the user submits it, then the assistant politely refuses, states the facts-only boundary, and provides one approved educational link.

### AC-04: Performance boundary

Given a request to calculate, compare, project, or rank returns, when the user submits it, then the assistant makes no performance claim and links to one relevant official factsheet or approved source.

### AC-05: Sensitive data

Given input containing a defined sensitive identifier, when it reaches the system, then no normal retrieval or generation occurs, the value is not echoed or persisted, and the user receives a warning with one official help/safety link.

### AC-06: Ingestion boundary

Given an allowed source page containing many internal links, when ingestion runs, then only the five explicitly allowlisted pages are fetched.

### AC-07: Reproducible stages

Given a completed ingestion and a demo query, when an evaluator inspects the project artifacts, then they can identify the raw source, extracted text, chunks, embedding/index manifest, retrieved chunk IDs and scores, and final response category.

### AC-08: Configuration consistency

Given a configured embedding model and Chroma collection, when ingestion and retrieval run, then both use the same compatible model and collection metadata; a mismatch fails clearly rather than returning unreliable results.

## 20. Evaluation Set

The submitted sample Q&A file should contain 5–10 representative queries, including at minimum:

1. Expense ratio for a named scheme.
2. Exit load for a named scheme.
3. Minimum SIP for a named scheme.
4. ELSS lock-in period.
5. Riskometer or benchmark.
6. Statement-download process.
7. Advice-seeking question that must be refused.
8. Performance-comparison question that must be refused or redirected.
9. Unsupported or out-of-scope factual question.
10. Sensitive-data test using an obviously synthetic placeholder, never real PII.

Each row should capture the query, expected category, expected fact or behavior, actual answer, citation URL, retrieved source/chunk IDs, and pass/fail result.

## 21. Deliverables

1. Working prototype link (app or notebook), or a demo video of no more than three minutes if hosting is unavailable.
2. Source list in CSV or Markdown containing all 15–25 URLs used across ingestion, official education/help, factsheets, and citations. Each entry should include URL, owner/domain, purpose, whether it is ingested or reference-only, and last-checked date.
3. README with setup steps, architecture, AMC/scheme scope, configuration, ingestion/retrieval commands, demo instructions, and known limitations.
4. Sample Q&A/evaluation file containing 5–10 queries, answers, links, expected categories, and results.
5. UI disclaimer: **“Facts-only. No investment advice.”**
6. `.env.example` with empty secret values.
7. Explicit persisted artifacts for all RAG stages.

## 22. Dependencies

- Network access to the approved public pages during ingestion.
- Stable extraction of the five page layouts.
- `sentence-transformers/all-MiniLM-L6-v2` availability.
- ChromaDB local persistence.
- A valid Groq API key and a Groq-supported model identifier.
- At least one approved official educational/safety link for refusal and privacy responses.

## 23. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Source page layout changes | Extraction may miss or mislabel facts | Use structure-aware parsing, extraction tests, checksums, and visible refresh status. |
| Values change after ingestion | Answers become stale | Store retrieval date, expose last-updated date, and provide a repeatable refresh command. |
| Weak retrieval selects a related but wrong scheme | Incorrect answer or citation | Detect scheme names, filter metadata, use thresholds, and evaluate near-duplicate facts. |
| LLM adds unsupported detail | Hallucinated claims | Constrain prompts, require structured output, validate source IDs, and use deterministic fallbacks. |
| Prompt injection in scraped content | Model behavior could be manipulated | Treat page content only as quoted evidence and enforce application-level policies. |
| PII enters logs or external prompts | Privacy breach | Detect and redact before logging, retrieval, tracing, or LLM calls; disable raw conversation storage. |
| Model identifier is unavailable | Generation fails | Keep the identifier configurable and validate it at startup with a clear error. |
| Five-page ingestion conflicts with a 15–25 URL source-list deliverable | Scope may be misunderstood | Mark every source as `ingested` or `reference-only`; preserve the five-page ingestion allowlist. |

## 24. Assumptions and Open Decisions

1. **Source authority:** The five Groww pages are the approved initial ingestion corpus. Official AMC, AMFI, SEBI, or Groww help pages may be added as reference-only sources for factsheets, education, and statement instructions.
2. **LLM identifier:** `qwen/qwen3.8-27b` is retained from the problem statement but must be validated before implementation because provider model catalogues can change.
3. **Provider scope:** Groq is required for the initial prototype. Gemini, OpenAI, Anthropic, and Mistral are treated as future provider adapters unless implementation scope is expanded.
4. **Source refresh:** The initial refresh can be manual; a required automatic schedule has not been specified.
5. **Statement instructions:** The exact official page for capital-gains statement download must be selected and added to the source registry before that question type is released.
6. **Citation count:** “Every answer must include one source link” is interpreted as exactly one trusted link per displayed response.
7. **Logging:** Operational telemetry is optional, but any implementation must redact inputs before storage and must never retain the defined sensitive values.

