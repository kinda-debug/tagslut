You are working inside the tagslut repository.

Your task:
Write or regenerate the post named `open-streams-post-0010` as a sharp, publishable project update about the DJ pipeline cleanup, library separation model, and operational lessons learned from rebuilding the workflow.

Goals:
- Explain what changed in clear operator language.
- Make the architecture understandable to someone who did not follow the repo history.
- Emphasize why the old workflow failed in practice.
- Show how the new workflow separates concerns cleanly.
- Keep the tone confident, candid, technical, and readable.

Primary framing:
This post is about replacing vague “DJ mode” behavior with explicit contracts:
1. Master FLAC library
2. MP3 library
3. DJ admission layer
4. Rekordbox XML projection

Required source-reading order before writing:
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

What the post must cover:
- Why the old “just add --dj” mental model was broken
- The difference between an MP3 library and a DJ library
- Why retroactive admission matters
- Why Rekordbox XML should be treated as an interoperability contract, not an afterthought
- How deterministic exports and stable IDs reduce operator pain
- Which parts of the system are now explicit instead of implied
- What remains unfinished, risky, or under test

Output requirements:
- Produce one complete markdown post
- Title it clearly
- Include:
  - a short intro
  - a “what was broken” section
  - a “new model” section
  - a “why this is better operationally” section
  - a “remaining risks” section
- Use plain language, not corporate fluff
- Include at least one concrete workflow example
- Do not invent features that are not present in code or docs
- If something is ambiguous, state the ambiguity instead of smoothing it over

Style constraints:
- Prefer short paragraphs
- Avoid buzzwords
- No fake triumphalism
- Be honest about failure modes and migration pain
- Sound like an engineer writing for technically literate operators

Deliverable:
Return only the final markdown for the post, ready to commit.
