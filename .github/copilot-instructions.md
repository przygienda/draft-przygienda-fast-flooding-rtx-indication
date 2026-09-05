# Repository instructions: draft-przygienda-fast-flooding-rtx-indication

This repo holds an IETF Internet-Draft (v3 RFC XML) that extends RFC 9681
("IS-IS Fast Flooding") with a Retransmission (RTX) indication flag. Read
this before making further edits.

## Scope

- The draft extends **only** RFC 9681 §4.3 (LPP) and §4.6/§6.2.1 (RWIN)
  flow-control mechanisms.
- The optional, local congestion-window (`cwin`) algorithm in RFC 9681
  §6.2.2 is explicitly **out of scope** — considered impractical to
  implement at scale. Do not reach for cwin-style language when extending
  the draft; keep additions framed around RWIN/LPP and the RTX flag.

## Build

- `xml2rfc` is installed via `pip` into `~/.local/bin`, which is **not** on
  the default `$PATH` in a fresh shell. Always run:
  ```
  export PATH=$PATH:/homes/prz/.local/bin && ./build.sh
  ```
- `build.sh` runs `xml2rfc --text` (produces the rendered `.txt`) and
  `xml2rfc --allow-local-file-access --expand ... -o *.expanded.xml`
  (produces a reference-expanded XML, useful once figures exist / for
  datatracker upload).
- **Always rebuild immediately after any edit that touches a `<section>`
  boundary.** It is easy to accidentally drop or duplicate an opening/
  closing `<section>` tag when doing surgical string-replacement edits;
  this has happened twice in this repo's history and was only caught by
  `xml2rfc`'s "Opening and ending tag mismatch" error on rebuild. A
  successful edit-tool call does not mean the XML is still well-formed.

## Git conventions

- Only `build.sh` and the source `.xml` are git-tracked. Generated outputs
  (`*.txt`, `*.pdf`, `*.html`, `*.expanded.xml`, `*.nl.txt`) are gitignored.
  This matches the sibling repo `draft-hierarchical-snps.github`'s
  convention.
- **Commit and push only when explicitly asked.** The usual pattern is
  many rounds of iterative wording/design edits between commits; do not
  commit proactively after every edit.
- GitHub disabled password auth for git-over-HTTPS; the user authenticates
  with a Personal Access Token. Never handle or request the token
  yourself — if push fails on auth, explain the PAT flow and let the user
  run the credential steps.

## Writing style for this draft

The user (a co-author of RFC 9681) is precise about wording and pushes
back on vague or imprecise language. Established corrections so far:
- Avoid casual phrasing like "realistically deployed" — prefer precise,
  neutral language (e.g., "most important, useful, and likely to be
  implemented").
- Avoid "not standardized" — RFC 9681 *is* a standard, just
  Experimental-track. Say things like "described only as an optional,
  local choice, without a single mandatory algorithm."
- Avoid vague trigger conditions like "outstanding retransmissions" —
  prefer precise, measurable definitions (e.g., "a count of
  retransmissions generated within a trailing time window exceeding a
  configured threshold").
- Avoid over-prescriptive fixed behavior like "halve the window" — prefer
  configurable, bounded language (e.g., "reduce by not less than a
  configurable threshold (e.g., 25%)"; "reopen by not more than half of
  the step most recently used to close").
- Keep sender-side backoff **unconditional and local** (applies whether or
  not the RTX flag is sent/understood); the RTX flag's purpose is to let
  the **receiver** converge its advertised RWIN toward a stable
  equilibrium, not to gate the sender's own backoff.

## Document structure (as of the latest commit)

Top-level sections, in order: Introduction, Requirements Language,
Motivation, The RTX Flag, Counting LSPs Under Concurrent Versions,
Procedures (Sender Behavior / Receiver Behavior / Convergence and
Hysteresis / Fallback on Persistent Non-Acknowledgment / Applicability to
LAN Interfaces), Interaction with RFC 9681, IANA Considerations, Security
Considerations, Acknowledgements, References. Section numbers auto-shift
as sections are added (`numbered="true"`); check anchors, not hardcoded
numbers, when cross-referencing (`<xref target="anchor"/>`).
