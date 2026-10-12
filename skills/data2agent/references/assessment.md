# Assessment and recorded decisions

Keep the user-facing assessment concrete and short. Scale detail to the task; avoid a fixed report or mandatory static/hosted question when the request already settles the choice.

Include:

- Scientific objective/audience and useful first-release scope.
- Sources found, source relationships, availability, input formats/units and verified dimensions. Separate catalog coverage from intended/actual queryable data.
- Required reuse/preprocessing/indexing and significant scientific ambiguities or resource needs.
- Domain entities, main queries/interactions and a preview when useful.
- Recommended storage/application/deployment architecture, with reasons based on capability needs and environment as well as size.
- Existing user decisions, Agent defaults, unresolved questions and concrete blockers.

An optional `work/decision.json` can look like:

```json
{
  "target": "hosted",
  "destination": "current machine, loopback",
  "backend": "project-specific implementation",
  "decisions": [
    {"field":"target", "value":"hosted", "decided_by":"user", "evidence":"The user requested a Web service"},
    {"field":"backend", "value":"project-specific implementation", "decided_by":"agent", "reason":"Supports the required domain queries in the available environment"}
  ]
}
```

Use actual choices and evidence, not these example strings. An Agent default is not a user confirmation. Ask only about missing information that would materially change the task or exceed authorized scope/resources. Record new answers and preserve prior decisions on resume.

The historical S/M/L/XL hints may describe an implementation, but they do not select one automatically. Static indexed-asset access, backend queries, online analysis, submissions/accounts, repeated updates and access requirements can lead to different choices even at similar data sizes.
