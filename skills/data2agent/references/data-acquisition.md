# Source discovery and acquisition

Discover from primary papers, repository records and author-maintained sources. A GEO accession is a useful source identity, not proof that all its files are single-cell, relevant, accessible, comparable or independent.

## Build the source inventory

For each candidate record: accession/DOI, organism, material, assay, study/sample relationships, author processing, available matrices/annotations/native assets, approximate size, access conditions, and inclusion reason. Keep `catalog_only`, `downloaded`, `processed`, `validated` and `queryable` distinct. Never derive a global cell total from GEO sample/library counts or a paper abstract.

Check for SuperSeries/SubSeries, reused libraries, integrated atlases and overlapping cohorts. A source can be relevant yet excluded from expression totals. Start from author matrices/results when adequate; fetching FASTQ and alignment is a separate processing decision, not implied by the phrase "raw count matrix". For topic search record query/date and explain whether coverage is selected or systematic.

`fetch_geo.py` is a helper for a known GSE, not a thematic literature search engine. `probe.py` reads file heads and offers hypotheses: metadata tables can look numeric, extensions can hide nested compression, and a matrix alone may not carry annotations. Inspect headers, formats and a small sample before accepting a suggestion.

## Reviewed download plan

Use `scripts/fetch_sources.py` for sources already selected by the Agent:

```json
[
  {"id":"study-a-counts", "study_id":"study-a", "role":"counts", "url":"https://repository.example/data/counts.tsv.gz", "path":"raw/study-a/counts.tsv.gz"},
  {"id":"study-a-labels", "study_id":"study-a", "role":"author_annotations", "local_path":"inputs/labels.tsv", "path":"raw/study-a/labels.tsv"}
]
```

These are illustrative URLs, not scientific inputs. Use real verified sources in a live task. `local_path` is resolved relative to the project unless absolute. Stable source IDs and project-relative destinations prevent basename collisions between studies. `sha256` and `bytes` can pin expected content. Keep secrets out of plans/receipts; use the environment's authorized access mechanism for controlled sources rather than recording credentials or transient signed URLs as public provenance.

```sh
"$PY" "$SKILL_ROOT/scripts/fetch_sources.py" --project "$PROJECT_ROOT" --plan source-plan.json
```

Receipts: `work/sources.json`; events: `.pipeline/sources.jsonl`; result: `reports/acquisition.json`. The helper copies/downloads via temporary files, checks length and optional pins, validates gzip CRC, records SHA-256, and reuses only intact recorded inputs. An existing unrecorded destination is refused rather than falsely attributed to a URL. To register a preexisting local input, use it as `local_path` and copy to a new recorded destination.

`--max-bytes` is an optional per-file limit chosen for the task, not a universal scientific size cap. The helper supports public HTTP(S) and local files on a POSIX host. Other transports, resumable multipart downloads and private repository access can use appropriate tools while writing equivalent provenance.

For an intentional refresh, or to repair a recorded input whose bytes changed on disk, revise any expected pin and use a versioned source/destination or `--refresh`. A refresh never silently accepts a checksum mismatch against the plan. Replaced original bytes are retained in `raw/.history/`. Rebuilding from a prior receipt does not mean the remote source was checked for updates; snapshot reuse and source refresh are different operations.

## Metadata and identifiers

Preserve original identifiers before mapping aliases or ontology terms. Join annotations by a verified key with explicit duplicate/missing checks, not by row order. Name dictionaries are versioned data too: official symbols can change while aliases remain scientifically useful. Confirm publication authors and year from the publication, rather than assuming the GEO contact is the first author.

Store citations and source links with the artifacts that use them. Unknown licenses, assembly versions or label meanings stay explicit. The Agent can investigate available evidence before asking the user for information that remains indispensable.
