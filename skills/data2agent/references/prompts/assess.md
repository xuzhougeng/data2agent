# Assess, design and preview

Goal: a concrete scientific and application plan grounded in real inputs. Use [assessment](../assessment.md) and [project design](../project-design.md).

1. Determine what questions can be answered from available evidence. Identify entities/relationships, units, processing requirements, compatible versus independent datasets, storage/query needs and missing annotations.
2. Select a useful first release and implementation. Reuse the user's scope/target/destination; otherwise choose reversible local defaults with reasons. Ask only for unresolved information that materially changes scope, resources or external deployment. Do not ask again for an already authorized hosted or static target.
3. Build a preview with a verified slice when it will resolve scientific, interaction or design choices. Clearly label sampling and which interactions are not yet implemented. For a compatible dataset, existing adapters plus `build_portal.py --preview-note` can help. For a thematic/genome project, preview its own entities and primary user tasks.
4. Open the preview against a real local server when possible. Record representative screenshots and errors. A picture or file:// page does not establish that queries work.
5. Record the plan and decisions in project files. Mark Agent choices as Agent choices, not invented user confirmations. A missing optional preference is not a universal stop condition; dependent work waits only for information genuinely required.

The preview/assessment is evidence for design. It is not the completed database. Stop only preview processes owned by this task when no longer needed; do not kill arbitrary processes by port.
