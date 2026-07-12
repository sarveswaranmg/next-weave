# NeuroWeave — Day 9: World Model Engine

## Overview

Days 1-8 made memory smarter — better retrieval, better compression,
self-maintenance, offline consolidation. All of it was still organized
around *memories*. Day 9 organizes around the user's *world*: a graph of
real entities (people, projects, companies, technologies, repositories,
tasks) connected by typed, weighted relationships, with projects as
first-class records carrying their own goals, architecture, roadmap, and
decision history.

```
Old: "The user mentioned PostgreSQL yesterday."
New: "The user is building a distributed cognitive runtime. Current
      stack: FastAPI, PostgreSQL, Redis. Next milestone: predictive
      retrieval evaluation."
```

This is understanding, not recollection — the world model continuously
answers: what exists, what's changing, what's connected, what's
important, what's currently active, and what should the AI anticipate.

## Pipeline

```
Conversation
     |
     v
Entity Extraction        EntityExtractor -> WorldEntity nodes
     |
     v
Relationship Detection   RelationshipBuilder -> WorldRelationship edges
     |
     v
Project Detection        ProjectMemoryEngine -> Project rows
     |
     v
Decision Recording       DecisionMemoryEngine -> ArchitecturalDecision rows
     |
     v
World Graph Update       WorldGraph (networkx rebuild + stats)
     |
     v
Context Prediction       ActiveContextEngine + PredictiveProjectIntelligence
```

Timeline is not a separate write step: `TimelineEngine` reads directly
from `WorldEntity`/`Project`/`ArchitecturalDecision` timestamps, so it can
never drift out of sync with the data it summarizes — the same "derive,
don't duplicate" choice Day 7 made for retrieval filtering.

## Components

| Component | File | Responsibility |
|---|---|---|
| `EntityExtractor` | `app/services/entity_extractor.py` | Curated keyword vocabularies (technology/service/device) + regex capture patterns (project/task/meeting/person/repository/goal/document/company) |
| `RelationshipBuilder` | `app/services/relationship_builder.py` | Infers typed edges (uses/stores/depends_on/migrates_to/deployed_to/works_on/blocks/part_of) from verb patterns between co-occurring entities |
| `WorldGraph` | `app/services/world_graph.py` | networkx graph construction + stats, mirrors Day 3/4's `ConceptGraph`/`IdentityGraphService` |
| `WorldTraversalService` | `app/services/world_traversal.py` | find_related_projects, find_affected_systems, find_dependencies (dependency-edges-only subgraph), explain_path (shortest path with hop-by-hop relationship labels) |
| `ProjectMemoryEngine` | `app/services/project_engine.py` | Detects/updates first-class `Project` records: phase, next step, status, tech stack |
| `DecisionMemoryEngine` | `app/services/decision_engine.py` | Detects and records architectural decisions with *why*, never overwritten |
| `ActiveContextEngine` | `app/services/active_context_engine.py` | Current project/milestone/priorities/blockers/experiments/stack, computed live |
| `TimelineEngine` | `app/services/timeline_engine.py` | Past/present/future, derived from existing timestamps |
| `EnvironmentalContextEngine` | `app/services/environmental_context_engine.py` | OS/IDE/cloud providers/databases/repos/integrations, categorized from DEVICE/SERVICE/TECHNOLOGY entities |
| `PredictiveProjectIntelligence` | `app/services/predictive_project_intelligence.py` | Likely next task, blockers, dependencies, missing knowledge/docs |
| `WorldModelPipeline` | `app/services/world_model_pipeline.py` | Orchestrates all of the above; `update()` |

## Database Changes

`world_entities` (migration `009_world_model_engine.py`): `entity_type`
(native Postgres enum covering all 15 kinds from the spec — person,
project, company, goal, technology, file, repository, task, meeting,
idea, document, api, location, device, service), `entity_name`,
`confidence`, `mention_count`, `attributes` (JSON), `first_seen_at`/`last_seen_at`.

`world_relationships`: `source_entity_id`/`target_entity_id` (FKs),
`relationship_type`, `strength` (weighted edge confidence),
`evidence_count` (grows with repeated evidence).

`projects`: `project_name`, `status` (active/paused/completed/archived),
`current_phase`, `progress`, `next_step`, plus `goals`, `tech_stack`,
`dependencies`, `roadmap`, `open_questions` (all JSON) — matches the
spec's example shape (`project`, `current_phase`, `status`) with the
richer fields the spec's "Project Memory Engine" section calls for.

`architectural_decisions`: `decision`, `reason`, `impact`, `status`
(decided/postponed/reversed/superseded), linked to `project_id` —
append-only, so a later retrieval can explain *why*, not just *what*.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/world/update` | Run the full pipeline over a piece of text |
| GET | `/world/model` | Full world model snapshot (entity/relationship/project counts, graph stats, active context, environment) |
| GET | `/projects` | List all tracked projects |
| GET | `/projects/{id}` | Single project's full record |
| POST | `/decision` | Manually record an architectural decision |
| GET | `/timeline` | Past/present/future for a user or project |
| GET | `/dependencies` | Transitive dependencies of an entity |
| POST | `/world/predict` | Likely next task/blockers/dependencies/missing knowledge |

## Test Case (validated in `tests/test_world_model.py`, 23/23 passing, and live end-to-end)

The spec's own conversation, run through `WorldModelPipeline.update()`:

> "I started building NeuroWeave. I'm using FastAPI. I'll migrate
> retrieval to Rust later. I'm currently implementing Day 9."

produced, in 18ms:

```
Project:        NeuroWeave (status=active)
Current Phase:  Day 9
Tech Stack:     [FastAPI, Rust]
Decision:       "retrieval to Rust later" (status=decided)
Active Context: current_project=NeuroWeave, milestone=Day 9,
                technology_stack=[FastAPI, Rust]
Prediction:     likely_missing_knowledge=[testing, ci/cd,
                api documentation, monitoring] (confidence=0.65)
```

— matching the spec's expected world model (project, current phase,
tech stack, future migration decision, active status) end to end, not
just per-component.

The second spec example ("Deploy Redis. Connect PostgreSQL. Benchmark
retrieval.") correctly extracts both `Redis` and `PostgreSQL` as
TECHNOLOGY entities.

## Bugs Found and Fixed During This Build

Two real defects, both caught by running the spec's own example text end
to end — the same pattern as every prior day:

1. **The spec's own relationship example didn't work**: `EntityExtractor`
   only recognized PROJECT entities introduced with "building/creating/
   started" — so "NeuroWeave uses PostgreSQL" (the spec's literal
   `RelationshipBuilder` example) extracted *zero* entities for
   "NeuroWeave", since it's the sentence subject with no introduction
   verb. Fixed by adding a second, lower-confidence pattern that
   recognizes a capitalized subject immediately preceding a relationship
   verb (uses/stores/depends on/...), guarded against relabeling anything
   already matched via the curated technology/service/device vocabularies.
2. **`re.IGNORECASE` silently defeats `[A-Z]` proper-noun detection**: to
   fix "Building NeuroWeave..." (capital B at sentence start) not matching
   a lowercase-only `building` trigger, a blanket `re.IGNORECASE` was
   applied — which also makes `[A-Z]` character classes match lowercase
   letters, since IGNORECASE affects the whole pattern, not just literal
   text. The result: "I started building NeuroWeave last month" captured
   `"NeuroWeave last month"` as the project name, greedily treating "last"
   and "month" as additional capitalized words. Fixed by scoping
   case-insensitivity to just the trigger-word alternations via inline
   `(?i:...)` groups, leaving `[A-Z]` capture groups genuinely
   case-sensitive.

A third, minor cosmetic issue was also fixed: `likely_documentation_needed`
produced doubled text ("api documentation documentation") when a missing-
knowledge topic already contained the word "documentation".

## Known Limitations

- **Heuristic NER, not a trained model**: entity extraction is curated
  keyword vocabularies + regex capture patterns (consistent with this
  project's dependency-free approach through Days 5-8). It will miss
  proper nouns with no supporting pattern (a project name that's never
  the subject of a recognized verb and never introduced with "building")
  and can occasionally over-match (e.g. a capitalized word that happens
  to precede "uses" without actually being a project). Precision favors
  the patterns the spec itself illustrates; recall on arbitrary free text
  will be lower than an LLM- or trained-NER-based extractor.
- **Relationship direction is mention-order, not grammatical**: `RelationshipBuilder`
  builds `source -> target` based on which entity's name appears first in
  the text, not true dependency parsing — correct for the natural
  "X verb Y" phrasing the patterns target, but not robust to reordered
  clauses ("Powered by PostgreSQL is NeuroWeave").

## Scalability Notes

- **Bounded per-update work**: `WorldModelPipeline.update()` processes one
  piece of text at a time (extraction is O(text length × pattern count),
  not O(store size)) — the cost of an update doesn't grow as the world
  model accumulates entities, which is the property that matters for
  scaling toward 1B+ entities.
- **Graph rebuild is per-user, not global**: `WorldGraph.build_graph_for_user`
  loads only one user's entities/relationships — horizontal scaling is
  partitioning by user, not sharding a single global graph.
- **Traversal is depth-bounded**: every `WorldTraversalService` method
  takes a `max_depth`/`cutoff`, so a query never walks an unbounded graph
  even if a user's world model grows very large.
- **Indexed hot paths**: `entity_type`, `entity_name`, `confidence`,
  `last_seen_at` on `world_entities`, and `relationship_type`/`strength`
  on `world_relationships`, are all indexed — the same convention as
  every prior day's tables.
- **Future Rust graph engine**: `WorldGraph`/`WorldTraversalService` are
  thin networkx wrappers over plain dicts/edges with no Python-specific
  state — the same portability property carried through Days 5-8's pure
  functions applies to a future native graph engine swap.
- **Streaming ingestion**: `WorldModelPipeline.update()` already takes
  arbitrary text with an optional `source_memory_id` — wiring it to a
  streaming conversation feed (rather than one full memory at a time) is
  a caller-side change, not a pipeline redesign.

## Future Extensibility

- **Code repository understanding**: `WorldEntityTypeEnum.REPOSITORY` and
  `WorldEntityTypeEnum.FILE` nodes already exist; a repo-aware extractor
  (parsing commit messages, README content, dependency manifests) is a new
  `EntityExtractor` input source, not a new entity type.
- **Calendar/email integration**: `WorldEntityTypeEnum.MEETING` nodes and
  the `works_on`/`blocks` relationship types are already modeled — a
  calendar sync populates the same tables through a different ingestion
  path.
- **Filesystem/browser/IoT awareness**: `WorldEntityTypeEnum.DEVICE` and
  `WorldEntityTypeEnum.LOCATION` already cover the entity shape; new
  sources are new `EntityExtractor` vocabularies, not schema changes.
- **Enterprise knowledge graphs**: every service takes `(session, user_id)`
  as plain arguments — a multi-user/organization graph is a different
  candidate query in each engine, not a different architecture.
- **Multimodal world understanding**: `WorldEntity.attributes` (JSON) and
  `supporting_memory_ids` are already generic enough to carry references
  to non-text evidence (image/audio memory ids) once those memory types
  exist upstream.
