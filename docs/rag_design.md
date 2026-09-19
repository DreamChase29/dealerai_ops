# RAG Design

## Scope

Phase 5 implements retrieval only. It does not generate answers with an LLM. The subsystem loads a
fictional synthetic dealership knowledge corpus, chunks it, embeds it with a deterministic local
implementation, retrieves relevant chunks, and returns citation-ready metadata.

## Corpus

The `/knowledge` directory contains synthetic demonstration markdown documents covering:

- dealership policies
- maintenance policies
- service scheduling
- warranty FAQs
- vehicle maintenance FAQs
- inventory terminology
- customer privacy
- sales-process FAQs
- human escalation policies

Each document states that it is fictional/synthetic demonstration material.

## Loading And Normalization

The loader reads markdown files, extracts the first H1 as title, uses the filename stem as
`document_id`, normalizes whitespace, and verifies the synthetic disclaimer marker. Evaluation JSON is
kept in the same directory but is not loaded as a knowledge document.

## Chunking

Documents are split by H2 section before chunking. Section-aware chunking keeps citations meaningful:
each chunk carries document title, section title, source path, synthetic flag, and chunk ID.

Default chunking uses:

- `max_words=90`
- `overlap_words=18`

This is intentionally small for the compact demo corpus. The overlap preserves context for sections
that mention a policy condition in one sentence and the action in the next.

## Embeddings

The default local embedding model uses sklearn `HashingVectorizer` with word and bigram features. It
is deterministic, requires no paid API, does not need a fitted vocabulary, and is suitable for tests.
It is not intended to match production semantic embedding quality.

## Vector Store

The default vector store is in-memory cosine similarity over L2-normalized vectors. It supports local
tests and offline demos. The interfaces support future adapters for:

- Amazon Bedrock embeddings
- Aurora PostgreSQL pgvector
- Amazon OpenSearch Serverless

The future adapter classes are explicit placeholders and raise `NotImplementedError`.

## Retrieval Output

Retrieved chunks include:

- `document_id`
- `title`
- `section`
- `chunk_id`
- `score`
- `text`
- source metadata

Citations can be derived directly from retrieved chunks.

## Evaluation

`knowledge/eval_queries.json` contains at least 40 evaluation queries with known relevant documents.
The evaluator calculates:

- Recall@K
- MRR
- Hit Rate@K

These metrics are retrieval-only. They do not measure grounded answer generation because answer
generation is not implemented yet.

## Failure Modes

- Lexical mismatch: local hashing retrieval may miss semantically related wording that shares few
  terms with the corpus.
- Chunk boundary miss: a relevant answer can be split across adjacent chunks despite overlap.
- Ambiguous query: broad queries may retrieve a neighboring policy document first.
- Stale corpus: policy changes require re-indexing.
- Source collision: future external stores must enforce stable document IDs and chunk IDs.
- Over-retrieval: high `top_k` can include weakly related chunks that a future generator must ignore.

## Production Notes

Before production use, replace local hashing embeddings with a managed or model-backed embedding
adapter, persist vectors in pgvector or OpenSearch, version indexes, evaluate citation correctness, and
monitor retrieval quality over real user queries.
