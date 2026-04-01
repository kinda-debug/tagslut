Audit this repository as a hostile, evidence-driven reviewer. Do not be polite. Do not assume the current architecture is justified just because it exists.

Context:
The DJ workflow failed badly in real use. The most basic expectations were not met. In particular, commands like download with `--dj` did not reliably produce usable MP3 copies, the workflow was overly complicated, and the actual operator experience collapsed into manual 1999-style file handling.

A second requirement also became obvious in practice:
I do not just need “a DJ path.” I need two distinct but interoperable targets:
1. an MP3 library
2. a DJ library

These are related but not identical.

The system must also be flexible enough to retroactively admit MP3 tracks into the DJ library, reconcile them with the database, and relate them back to the master FLAC library where applicable. In other words, the workflow cannot assume that only FLAC-first intake is valid, or that DJ copies only arise at initial download time.

A further hard requirement:
I want seamless integration with Rekordbox through direct XML generation and editing as a first-class workflow, not as an afterthought. Audit whether the repo should explicitly support reliable Rekordbox XML authoring/editing for playlist creation, playlist updates, library admission, and DJ set preparation.

I want you to audit the repo from the perspective of real execution, not stated intent.

Your mission:
Produce a rigorous repo audit focused on why the DJ workflow is brittle, overcomplicated, operationally unreliable, and poorly aligned with actual DJ library operations, then propose concrete fixes.

Operating rules:
1. Inspect the actual code paths, CLI commands, configs, docs, tests, scripts, XML handling, and database models involved in the DJ workflow.
2. Trace the end-to-end path for:
   - intake / download
   - `--dj` behavior
   - transcode / MP3 copy generation
   - pool/export/build steps
   - MP3 library generation and maintenance
   - DJ library generation and maintenance
   - retroactive admission of existing MP3s into the DJ library
   - reconciliation with the main database
   - linkage back to the master FLAC library
   - Rekordbox XML generation/editing
   - any metadata, identity, enrichment, or path assumptions that affect DJ outputs
3. Verify behavior by running the relevant tests and, where safe, the actual commands in dry-run or controlled mode.
4. Compare docs/promises against implementation reality.
5. Identify where the architecture is doing too much, where responsibilities are split across too many layers, and where operator experience becomes unreasonable.
6. Prefer evidence over theory. Every claim must point to code, command output, tests, logs, schema, XML output, or missing tests.
7. Do not fix anything yet unless I explicitly ask. First produce the audit.

What I want audited specifically:
- Why `--dj` is not reliably resulting in MP3 copies being created
- Whether the DJ path is under-specified, over-engineered, or fragmented across too many scripts/modules
- Whether the repo has hidden coupling between download, transcode, tagging, identity, enrichment, export, pool-building, rebuild logic, and XML projection
- Whether there are places where “canonical architecture” is making simple workflows harder than they should be
- Whether the CLI surface is misleading, inconsistent, or operationally unsafe
- Whether failures are surfaced clearly or silently swallowed
- Whether docs and plans describe a workflow that the code does not actually implement
- Whether the test suite protects the real DJ workflow or mostly protects abstractions
- Whether the system cleanly distinguishes:
  - master FLAC library
  - MP3 library
  - DJ library
- Whether those three layers have clear contracts, or whether they are currently blurred in ways that create operational pain
- At what exact point files are enriched:
  - initial intake
  - post-download
  - post-transcode
  - library admission
  - DJ admission
  - export/pool phase
  - Rekordbox projection phase
- Whether enrichment is deterministic, repeatable, and retroactively applicable
- Whether a separate DJ metadata store or sub-database is warranted
- Whether custom tools are needed to generate, rebuild, reconcile, and audit DJ metadata independently of the master library flow
- Whether seamless Rekordbox integration via direct XML editing/generation should be a formal part of the architecture
- Whether the repo can produce Rekordbox XML deterministically and safely from its current DB/model state
- Whether XML is the right interoperability boundary for playlist curation, DJ admission, and Rekordbox preparation

You must evaluate:
- whether direct Rekordbox XML editing should be an official supported output contract
- whether the current data model can safely drive Rekordbox XML generation
- whether XML export/edit/rebuild should be treated as a stable interoperability layer between the repo and Rekordbox
- whether MP3 library tracks and DJ library tracks can be cleanly projected into Rekordbox XML without ambiguous identity or path handling
- whether retroactively admitted MP3 tracks can be inserted into Rekordbox-facing XML flows without corrupting collection consistency
- what safeguards are required so XML editing remains deterministic, reversible, and auditable

Key design questions you must answer:
1. Should the repo explicitly support both:
   - an MP3 library as a durable, managed derivative library
   - a DJ library as a stricter, performance-oriented subset or sibling layer?
2. If yes, what are the correct boundaries between them?
3. How should an existing MP3 track be admitted retroactively into the DJ library?
4. How should that MP3 be reconciled with:
   - the main DB
   - canonical recording identity
   - any FLAC master equivalent
   - asset/link/provenance records
5. What metadata should live in the main DB versus a DJ-specific metadata DB or sub-DB?
6. What custom tools should exist to:
   - generate DJ metadata
   - backfill DJ metadata
   - reconcile MP3 assets to FLAC-linked canonical identities
   - validate DJ readiness
   - rebuild the DJ library without corrupting the master library model
7. Should Rekordbox XML be treated as:
   - a thin export artifact
   - a bidirectional working format
   - a primary DJ interoperability layer?
8. What is the safest architecture for direct XML editing without creating identity drift, duplicate entries, or broken playlist state?
9. Should TrackID assignment and playlist membership for Rekordbox-facing outputs be generated from the main DB, a DJ sub-DB, or a dedicated export index?
10. At what exact stage should enrichment happen for:
   - FLAC masters
   - MP3 library assets
   - DJ-admitted assets
   - Rekordbox XML outputs
11. Which enrichment steps must be mandatory, optional, deferred, or backfillable?

Method:
1. Map the real DJ workflow entry points.
   - Find all commands, scripts, modules, schemas, and docs related to DJ download, transcode, MP3 generation, pool building, export, candidate selection, rebuilds, Rekordbox XML, and metadata enrichment.
   - Produce a dependency map showing the real execution chain.

2. Reconstruct expected behavior.
   - From docs, README, agent instructions, tests, CLI help, and code comments, infer what a user would reasonably expect `--dj` and related DJ workflows to do.
   - Infer separately what a user would expect for:
     - MP3 library behavior
     - DJ library behavior
     - retroactive MP3 admission into DJ workflows
     - Rekordbox XML integration
   - Then compare that to what the code actually does.

3. Reproduce failure points.
   - Run targeted commands/tests where feasible.
   - Capture the exact stage where MP3 generation is skipped, misrouted, optional when it should be required, or dependent on hidden preconditions.
   - Identify environment variables, config flags, DB state assumptions, path assumptions, enrichment assumptions, XML assumptions, or state dependencies that make the workflow fragile.

4. Audit complexity and bottlenecks.
   - Identify architectural bottlenecks, logic bottlenecks, UX bottlenecks, DB bottlenecks, XML bottlenecks, and debugging bottlenecks.
   - Call out duplicated logic, dead paths, wrapper-on-wrapper behavior, legacy compatibility layers that now obstruct execution, and places where simple actions require too much orchestration.

5. Audit data model clarity.
   - Identify the current source of truth for:
     - recordings
     - master FLAC assets
     - MP3 assets
     - DJ-admitted assets
     - DJ-specific metadata
     - Rekordbox-facing export state
   - Determine whether the data model cleanly supports multiple asset classes and library roles, or whether it is trying to force incompatible workflows into one model.
   - Evaluate whether a DJ metadata sub-DB or schema partition would reduce operational complexity.

6. Audit Rekordbox XML integration.
   - Identify all existing XML-related code, assumptions, generation paths, patching paths, and validation logic.
   - Determine whether XML output is deterministic and trustworthy.
   - Identify how TrackIDs are assigned, preserved, or regenerated.
   - Determine whether playlist membership, path projection, and collection consistency are robust under rebuilds and retroactive MP3 admission.
   - Flag anything likely to create broken paths, duplicate entries, malformed XML, unstable IDs, or inconsistent Rekordbox imports.

7. Evaluate test coverage against reality.
   - Which tests actually cover end-to-end DJ outcomes?
   - Which tests only prove internal pieces while the user-facing workflow can still fail?
   - Which tests would be needed to guarantee:
     - `download --dj` actually yields usable MP3 outputs
     - MP3 library generation works
     - DJ library generation works
     - retroactive MP3 admission works
     - reconciliation with DB and FLAC master works
     - enrichment timing is correct and stable
     - Rekordbox XML output is valid, deterministic, and import-safe

8. Propose concrete solutions.
   For each issue, provide:
   - severity: critical / high / medium / low
   - symptom
   - root cause
   - exact files/modules involved
   - recommended fix
   - whether the fix is:
     - small patch
     - refactor
     - architectural simplification
     - schema redesign
     - custom tool addition
     - export-layer redesign
     - deletion/removal of obsolete path
   - expected operator impact
   - suggested priority order

Deliverables:
A. `DJ_WORKFLOW_AUDIT.md`
This must include:
- Executive summary
- What a user expects
- What actually happens
- Failure map of the DJ workflow
- Bottlenecks ranked by severity
- Clear distinction between master FLAC library, MP3 library, and DJ library
- Analysis of when and how enrichment occurs
- Recommendation on whether to introduce a DJ metadata sub-DB
- Analysis of whether Rekordbox XML should be a first-class interoperability layer
- Concrete remediation plan
- “What to delete or collapse” section
- “Fast wins in 1 day / 3 days / 1 week” section

B. `DJ_WORKFLOW_TRACE.md`
Include:
- command entry points
- modules called
- downstream scripts/services
- config/env dependencies
- DB/schema dependencies
- enrichment points
- Rekordbox XML dependencies
- outputs expected vs outputs produced

C. `DJ_WORKFLOW_GAP_TABLE.md`
A table with columns:
- Workflow step
- Expected behavior
- Actual behavior
- Evidence
- Root cause
- Proposed fix
- Priority

D. `MISSING_TESTS.md`
List the highest-value tests that should exist to prevent this from happening again, especially true end-to-end tests for:
- DJ outcomes
- MP3 library outcomes
- retroactive MP3 admission
- DB reconciliation
- enrichment correctness
- Rekordbox XML correctness and determinism

E. `DATA_MODEL_RECOMMENDATION.md`
This must answer:
- Should there be separate concepts for master library, MP3 library, and DJ library?
- What should live in the main DB?
- What should live in a DJ metadata sub-DB, if any?
- What custom tools should exist for generation, admission, reconciliation, validation, and rebuild?
- At what stage should enrichment occur for each library role?

F. `REKORDBOX_XML_INTEGRATION.md`
This must answer:
- Should direct Rekordbox XML editing/generation be officially supported?
- What exact XML workflows should exist?
- What data should drive XML generation?
- What validations must run before XML is emitted or patched?
- How should retroactive MP3 admission appear in XML-facing workflows?
- What is the safest contract for deterministic playlist and track projection into Rekordbox XML?
- How should TrackIDs be handled across rebuilds, edits, and retroactive admissions?

Critical framing:
I do not want a defensive reading of the architecture. I want you to identify where the repo is being clever instead of being usable.
Assume the operator is trying to do straightforward DJ work under time pressure.
Flag anything that would force a user into manual file handling, manual transcoding, hidden preconditions, unclear enrichment stages, brittle XML flows, or multi-step recovery just to get MP3 DJ copies into a working Rekordbox-ready state.

Important constraints:
- Do not hand-wave.
- Do not say “could be improved” without saying exactly how.
- Do not produce vague recommendations like “improve documentation” unless you also specify what command contract, data contract, XML contract, or behavior must change.
- Be willing to conclude that some parts of the current workflow should be removed, collapsed, split, or rewritten.
- Distinguish sharply between:
  - bugs
  - design flaws
  - unnecessary complexity
  - misleading command surface
  - broken data contracts
  - broken XML contracts
  - missing safeguards
  - missing tests

Final required section:
End the audit with:
1. the top 5 reasons the DJ workflow failed in practice
2. the minimum viable redesign to make it trustworthy
3. the shortest path to a boring, reliable operator experience
4. the recommended model for:
   - master FLAC library
   - MP3 library
   - DJ library
   - DJ metadata storage
   - retroactive MP3 admission and reconciliation
5. the recommended architecture for seamless Rekordbox XML integration
