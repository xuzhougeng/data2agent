# Genome, sequence and genomic-track databases

Use assemblies, annotations and evidence as first-class entities. A genome article can justify a database without any expression matrix or observation table.

## Model the reference

Record organism, assembly identifier/version, contig names and lengths, sequence/annotation sources, and gene/transcript/exon relationships. Preserve source identifiers and namespaced aliases. Keep different assemblies separate unless a documented mapping is provided. Gene-name lookup requires an annotation source, not just FASTA headers.

Validate FASTA identifiers/lengths, annotation contig membership, interval bounds, strand and parent relationships. Document coordinate conventions at each interface: GFF/GTF coordinates are commonly 1-based inclusive; BED/bigWig APIs commonly use 0-based half-open intervals. Verify conversions on boundary examples, both strands, and known sequences rather than applying an unexamined offset throughout.

Use native indexed sequence/annotation formats when they support efficient queries. Build indexes with appropriate libraries/tools and record their compatibility with the exact source assembly. Do not manufacture an `obs × features` table to satisfy the legacy portal contract.

## bigWig, peaks and related evidence

Preserve bigWig as indexed signal data. Record assembly, sample/assay, target/antibody, condition/replicate, signal meaning, units and normalization from the source. A track's filename or chromosome names do not reliably establish all these facts. Missing signal is distinct from an explicit zero. Signal tracks alone do not establish author peak calls, differential significance or target genes.

Keep peak/region annotations queryable as appropriate tables or indexed assets. Link tracks to assemblies, studies and samples. A browser such as IGV.js or JBrowse can be chosen after checking current official documentation and the desired interactions; the skill does not require one widget or visual style. Verify byte-range retrieval and CORS when applicable, including custom assemblies rather than only a built-in reference.

For programmatic access, expose domain queries such as gene lookup, region annotations, sequence extraction and region signal summaries. Define exact-versus-zoom-summary behavior, bounds, strand and missingness. Precomputed summaries and online interval reads are different capabilities; label what is implemented.

## Application and acceptance

Useful interactions can include assembly overview, gene/transcript pages, region navigation, sequence downloads, cross-referenced evidence and a track browser. Add sequence similarity search only when requested/useful and actually implement its indexing, job execution and results; do not show a nonfunctional tool button.

Derive acceptance values from original FASTA/GFF/track inputs: contig lengths, feature counts/relationships, boundary overlaps, strand-correct subsequences, and representative signal values with units. Verify unknown contigs/IDs, out-of-range queries, downloadable indexes/assets and any implemented HTTP/MCP transport. Preserve native assets and provenance in delivery.
