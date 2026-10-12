# Reproducible domain processing

The Agent chooses and configures appropriate domain tools and may write adapters, workflows and application code. Preserve original numeric inputs; record transformations and do not relabel a recomputed result as an author result.

## Decide before computing

Inspect file signatures, dimensions, IDs, assay, organism, reference version and numeric meaning. Distinguish raw reads, raw counts, normalized values, residuals, embeddings and author result tables. Select reuse versus recomputation for the scientific question; an available pipeline's defaults are not automatically appropriate for every organism or assay.

A processing plan should state input assets and units, selected tools/versions, parameters, seeds, expected outputs, resources, and scientific acceptance checks. Install dependencies in project-owned environments and lock them. Large alignment/integration work needs a resource plan; it is not a hidden consequence of viewing a matrix.

Keep independent studies separate unless an explicit scientific integration method is justified. Preserve study/sample/cohort identities and feature presence. Never silently drop duplicate IDs, join metadata by position, fill missing measurements with zero or mix normalized values with counts.

## Local task runner

Write the domain scripts first, review them, then express their execution in `pipeline.json`. This example refers to project scripts the Agent must implement; they are not bundled genome adapters:

```json
{
  "version": 1,
  "steps": [
    {
      "id": "index-genome",
      "command": ["{python}", "pipeline/index_genome.py", "raw/reference.fa", "raw/genes.gff3", "work/genome-index"],
      "inputs": ["raw/reference.fa", "raw/genes.gff3", "pipeline/index_genome.py", "requirements.lock"],
      "outputs": ["work/genome-index"],
      "checks": [["{python}", "pipeline/check_genome.py", "work/genome-index"]],
      "timeout_seconds": 600
    },
    {
      "id": "build-database",
      "needs": ["index-genome"],
      "command": ["{python}", "pipeline/build_database.py"],
      "inputs": ["work/genome-index", "pipeline/build_database.py", "project.json"],
      "outputs": ["pkg/database.sqlite", "pkg/manifest.json"],
      "checks": [["{python}", "pipeline/validate.py"]]
    }
  ]
}
```

```sh
"$PY" "$SKILL_ROOT/scripts/run_pipeline.py" --project "$PROJECT_ROOT" --dry-run
"$PY" "$SKILL_ROOT/scripts/run_pipeline.py" --project "$PROJECT_ROOT"
"$PY" "$SKILL_ROOT/scripts/run_pipeline.py" --project "$PROJECT_ROOT" --step build-database
```

`--step` includes dependencies; the default visits the whole DAG. `--force` recomputes the selected graph. The runner uses POSIX locking and argument-array subprocesses, not an implicit shell. Paths for outputs are project-relative; outputs must not overlap each other, inputs, `raw/`, environments or task state. Inputs can name explicitly selected external files. Declare imported helper modules, parameter files and non-Python environment/image versions as inputs as well as the direct script. Keep secrets in authorized runtime facilities, not the serializable `env` or `parameters` fields.

`parameters` records decisions for fingerprinting; it does not invent command-line flags. Pass actual arguments/config files to the domain tool. Declare reports produced by validation commands as outputs when they form part of the task. Scientific inputs should reference source content and stable configuration, not volatile event logs or verification timestamps.

The runner fingerprints inputs, definition, dependencies and the Python version; installed package versions are recorded in the receipt but not fingerprinted, so declare the lock file as an input to invalidate on dependency changes. It does not infer scientific validity or inspect every external tool environment. Provide domain validators in `checks`. They must exit nonzero on failure. Every declared output must exist before success is recorded. Old outputs are moved aside before execution, preventing exit-0 commands from passing on stale artifacts. They are restored after failure; earlier generated versions remain under `.pipeline/attempts/` after success for deliberate cleanup.

Successful receipts are reusable only while fingerprints and output hashes match. A corrupted/missing output triggers a rerun. Input changes invalidate downstream work even when dimensions remain the same. A task interrupted before success is not reusable. If its receipt still says `running`, inspect the recorded PID, then rerun with `--force`. Submitting an asynchronous cluster job is insufficient: the wrapper must wait for and verify its result.

## Validation specific to the domain

- Matrices: axis identities, shape, sparse-coordinate uniqueness, finite/range constraints, missingness, source units, and summary denominators including true zeros.
- Metadata: unique join keys, unexpected/missing rows, namespaces, aliases, source/ontology evidence and annotation confidence.
- Genomic assets: assembly/contig agreement, bounds, strand, coordinate conversion and index compatibility.
- Analyses: distinguish author versus recomputed output, record parameter/model/reference versions, validate representative values independently, and avoid conclusions beyond the tested method.

See [single-cell](domains/single-cell.md) and [genome/track](domains/genome.md) rules only when applicable.
