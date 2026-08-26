# Private record — public commitments

`PLAN.md` is this project's canonical strategy document. It is **deliberately not published**: it
carries strategy detail that does not belong in a public repo, and it is gitignored here.

That creates a verifiability gap. Every pre-registration in `docs/probes/` is publicly committed, so
"registered before measured" is checkable by anyone. Decisions recorded only in `PLAN.md` had no such
property — a reader had to take our word that a decision preceded the result it justifies.

**This file closes that gap without publishing the document.** Each row commits to the exact bytes of
`PLAN.md` at a point in time. We cannot later alter what it said and claim otherwise: any change to
a single character changes the digest. If the plan is published after the event, or shown to a judge
privately, it can be checked against these.

```
shasum -a 256 PLAN.md
```

| date (ET) | PLAN.md SHA-256 | private-record commit *(separate repo)* | what had just been decided |
|---|---|---|---|
| 2026-08-26 15:57 | `220316a09015850ab6786b98b7ac27ca2a06cfd1d78bbdb76e20b6ce40038282` | `e7a68b3aff8a` | universe decided (11 names), gate verdicts recorded, cost model written, IC and job-2 results in |

**What this is not.** These digests are published by us, in our own repository, so on their own they
prove ordering only relative to our own commit history. Combined with the public commit timestamps
and the push history they are reasonable evidence, not a trusted third-party timestamp. Stated
plainly rather than implied.

**What it does not replace.** A digest cannot restore a lost document. `.claude/private/` is its own
nested git repository for that reason — content history for recovery, digests here for public
verifiability. They solve different problems and neither substitutes for the other.
