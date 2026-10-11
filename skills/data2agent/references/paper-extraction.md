# Paper extraction

If a paper is available (DOI, PDF, PMC full text, or the GEO series summary/overall design), pull exactly these fields into `work/curation.json → dataset`:

| Field | From | Rules |
| --- | --- | --- |
| `title` | paper title or GEO series title | as published |
| `short_title` | accession or a 2–4 word name | used in the nav bar |
| `description` | abstract + GEO summary | 2–4 sentences, your words, present tense, no results claims beyond what the data shows; name organism, tissue, technology, sample/cell counts, groups |
| `source.paper` | DOI, authors, journal, year | `citation` in a standard one-line form: "Authors (Year). Title. Journal. doi" |
| `methods` | methods section + GEO "overall design" + what the adapter did | markdown; separate "Original processing (authors)" from "Portal processing (Data2Agent)" |
| `license` | GEO (public domain for metadata; check supplementary file licence), paper data-availability statement | if unknown write "see source" rather than inventing a licence |
| `contact` | corresponding author or GEO contact | published contact only |
| `results[*].description` | figure legends / supplementary table captions for DE tables | state the comparison and the method the authors used |

Tone: a database "About" page, not a press release. No "novel", "groundbreaking", "we show". No first person. No AI self-reference anywhere in the package.

Record in `notes` what you could not find (e.g. "no licence stated for GSE…_counts.txt.gz").
