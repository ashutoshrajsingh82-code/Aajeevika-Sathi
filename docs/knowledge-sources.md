# Knowledge sources and review

## Configured starting sources

`backend/app/knowledge/sources.json` contains a deliberately small URL allowlist and import catalogue. Initial records are official publication pages for:

- Department of Social Justice and Empowerment PM-AJAY page: <https://socialjustice.gov.in/schemes/104>
- PM-AJAY Guidelines, May 2023 PDF: <https://socialjustice.gov.in/writereaddata/UploadFile/31121740857806.pdf>
- PM-AJAY guidelines index: <https://pmagy.gov.in/Guidelines-All-Languages>
- National Qualifications Register overview: <https://www.nqr.gov.in/aboutus>

These are **source candidates**, not indexed or approved answers. New imports remain `OFFICIAL_UNVERIFIED`. A reviewer must inspect extracted text, confirm the live source bytes still match the imported original, and submit a review note before a document becomes retrievable as `OFFICIAL_VERIFIED`. Government-looking terms or a `.gov.in` string alone do not grant authority. URLs outside the exact import catalogue cannot be downloaded by the application.

The allowlist is not an automatic trust decision. Before adding a source, verify the specific publishing agency and document against its official government site. Do not add third-party mirrors as official sources.

## Ingestion and extraction

Admins can import an allowlisted URL or upload PDF, DOCX, TXT, Markdown, HTML, or common image formats. The original bytes are retained in the document row and content-addressed with SHA-256. PDF extraction stores page-aware chunks and first tries layout-preserving native text. Pages with sparse native text are rendered for OCR. The OCR copy is normalized for resolution, converted to grayscale, contrast-enhanced, denoised, and thresholded where appropriate; the retained original never changes. Tesseract, PyMuPDF, Pillow, pytesseract, and the configured Tesseract language data are required for OCR. Configure `OCR_LANGUAGES` (default `eng+hin`), `OCR_DPI`, and `OCR_MIN_CONFIDENCE`; install matching `.traineddata` files for every configured language. Engine absence, missing language data, failed pages, and low confidence receive distinct ingestion states. An image-only upload with no OCR result is retained for review but creates no searchable text chunks. Mixed documents preserve native page text while staying unverified if scanned pages still need OCR.

OCR engine, configured language, aggregate confidence and page-level confidence are stored with document/chunk provenance. OCR and partial-text results remain unverified and excluded from knowledge retrieval until an administrator approves the source. The verification endpoint rejects incomplete or failed OCR. For any OCR-produced text, the admin must explicitly confirm that the extracted pages were compared against the original. Low-confidence output is highlighted for this review. Re-indexing clears previous approval because extracted text may change. DOCX extraction preserves headings and table rows, but DOCX files do not have stable page numbers. PDF table extraction is best-effort and requires human review.

Chunks preserve document id, page number where the format supplies one, section heading, source URL, and scheme metadata. Re-indexing works from the retained original. HTML scripts and styles are excluded. Ingestion is limited to 20 MB.

## Retrieval and answering

`VECTOR_STORE=json` and `RETRIEVAL_MODE=hybrid` preserve portable SQLite operation. `VECTOR_STORE=pgvector` uses the PostgreSQL vector column and HNSW cosine index created by migration `0007`; the JSON vector remains available as a fallback. `RETRIEVAL_MODE=hash` and `vector` select the individual retrievers. `EMBEDDING_PROVIDER=hash` keeps an offline feature-hash embedding; an OpenAI-compatible embeddings endpoint can be selected with `EMBEDDING_PROVIDER=openai_compatible`, `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL`, and `EMBEDDING_DIMENSIONS=256`.

Hybrid retrieval combines a lexical candidate score with vector similarity; a small rule-based intent classifier only selects retrieval metadata filters. It does not generate facts. Only `OFFICIAL_VERIFIED`, `SECONDARY_SOURCE`, `STALE`, and explicitly synthetic `DEMO` chunks can be returned. Unknown and unverified material is excluded. Official verified evidence takes precedence over secondary and demo evidence. Secondary material is labelled as secondary, and demo material is labelled `DEMO DATA`.

For LLM answers, the model returns atomic claims and chunk citations. The backend checks every claim against its cited passage, requires numeric values to occur in the evidence, rejects mismatched citations, and renders only claims that pass. If validation rejects all claims, the backend uses exact source sentences or abstains. The check is conservative lexical entailment, not a general semantic proof; it can reject valid paraphrases and does not establish legal correctness. Human review remains necessary.

If authoritative evidence is missing, the API abstains with `I could not find sufficient verified official-source information to answer this question. Official source information is currently unavailable for this query.` No model-only factual answer is used.

## Evaluation

`backend/app/knowledge/evaluation_cases.json` is a synthetic retrieval benchmark. It tests direct, paraphrased, short, long, spelling/mixed-language, and unanswerable questions without embedding claims about an actual scheme. `evaluation.py` reports Recall@k, Precision@k, MRR, nDCG@k, abstention accuracy, citation coverage, support rate, and unsupported-claim rate. These synthetic results are not evidence of government-domain retrieval quality. Review and expand the benchmark with labeled official passages before making quality claims.
