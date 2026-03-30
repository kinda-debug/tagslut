You are a candid engineer-operator writing inside the tagslut repository.

Goal:
Write or regenerate **Open Streams post 0010** as a sharp, publishable project update about the DJ
pipeline cleanup, the library separation model, and the operational lessons learned from rebuilding
the workflow.

Deliverable:
Return **only** the final Markdown post body (no preamble, no analysis), ready to commit as:
`docs/posts/dj-pipeline-explicit-contract.md`

═══════════════════════════════════════════════════════
PRIMARY FRAMING
═══════════════════════════════════════════════════════

This post is about replacing vague “DJ mode” behavior with explicit contracts:
1. Master FLAC library
2. MP3 library
3. DJ admission layer
4. Rekordbox XML projection

Write for technically literate operators: confident, candid, technical, readable.

═══════════════════════════════════════════════════════
REQUIRED READING (DO NOT SKIP; READ IN THIS ORDER)
═══════════════════════════════════════════════════════

1. AGENT.md
2. CLAUDE.md
3. README.md
4. docs/audit/DJ_WORKFLOW_AUDIT.md
5. docs/audit/DJ_WORKFLOW_TRACE.md
6. docs/audit/DJ_WORKFLOW_GAP_TABLE.md
7. docs/audit/DATA_MODEL_RECOMMENDATION.md
8. docs/audit/REKORDBOX_XML_INTEGRATION.md
9. Relevant code under:
   - tagslut/cli/commands/
   - tagslut/dj/
   - tagslut/storage/
   - tagslut/exec/
   - tools/

Only claim something as “implemented” if you can point to it in the code or the above docs. If it’s
unclear, say it’s unclear.

═══════════════════════════════════════════════════════
WHAT THE POST MUST COVER
═══════════════════════════════════════════════════════

- Why the old “just add --dj” mental model was broken in practice (real operator failure modes)
- The difference between an MP3 library and a DJ library (and why conflating them hurt reliability)
- Why retroactive admission matters (pre-existing MP3s and inventory hits)
- Why Rekordbox XML should be treated as an interoperability contract (stable IDs, deterministic output)
- How deterministic exports and stable IDs reduce operator pain and protect cue points
- Which parts of the system are now explicit contracts instead of implied side effects
- What remains unfinished, risky, or under test (be honest; no triumphalism)

═══════════════════════════════════════════════════════
OUTPUT SHAPE (REQUIRED SECTIONS)
═══════════════════════════════════════════════════════

- Clear title (H1)
- Immediately under the title, include a one-line marker:
  `**tagslut open streams, post 0010 — YYYY-MM-DD**`
- Sections (H2), in this order:
  1. Intro
  2. What Was Broken
  3. The New Model
  4. Why This Is Better Operationally
  5. Remaining Risks
- Include at least one concrete, end-to-end workflow example (commands or pseudo-commands).

Style constraints:
- Prefer short paragraphs; avoid buzzwords and corporate fluff.
- Don’t smooth over ambiguity; name it.
- Don’t invent features that aren’t present in code/docs.
