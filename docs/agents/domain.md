# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

Layout: **single-context.** One glossary and one ADR directory at the repo root.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root: this repo's glossary. The skills' default name is `GLOSSARY.md`; here the file is `CONTEXT.md` (it predates the setup). Read and extend `CONTEXT.md`; do not create a second `GLOSSARY.md`.
- **`docs/adr/`**: read ADRs that touch the area you're about to work in (today `0001-never-force-delete.md`).

If either doesn't cover the area, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates and extends them lazily when terms or decisions actually get resolved.

## File structure

```
/
├── CONTEXT.md          ← glossary (the skills' "GLOSSARY.md")
├── docs/adr/
│   └── 0001-never-force-delete.md
└── src/
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md` (for example *own upload*, *duplicate*, *watched root*, *live delete*). Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0001 (never force-delete), but worth reopening because…_

Weakening ADR 0001 needs the owner's explicit approval and a new ADR (CLAUDE.md, P9).
