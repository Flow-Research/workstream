# Plan: Writer-Directed Workstream Start

1. Add a closed signed selection envelope containing mode, phase, exact contract
   path, canonical heading title, and trusted-main blob SHA. Preserve declared
   successor compatibility and permit a writer-directed selection when all
   signed initiatives are idle.
2. Resolve only a regular, non-symlink contract in the requested initiative's
   canonical chunk directory; reject missing, duplicate, foreign-initiative,
   malformed, title-mismatched, or blob-mismatched evidence.
3. Replace the static actor list with a closed trusted-main permission policy;
   query and sign the dispatcher's current GitHub repository permission and
   require `write`/`push`, `maintain`, or `admin`. Preserve the separate environment
   approval and active-chunk match required for cancel.
4. Allow a fresh signed writer dispatch after cancellation when global state is
   idle, without modifying the prior cancel event or its approval evidence.
5. Extend the closed recovery certificate with an exact one-merge bootstrap mode
   for `WS-ENG-004-01`; require plan `[target]`, first parent equal to signed
   current main, and target identity from trusted GitHub merge evidence; consume
   it before ledger publication and prohibit persistence or replay.
6. Add fail-closed tests, workflow invariants, operational documentation,
   internal review evidence, and one merge intent with no automatic successor.
7. After merge and signed reconciliation, dispatch `WS-CI-001-02` as planning
   work on exact main. Its output must replace placeholder scope with a separately
   reviewed executable amendment before CI implementation begins.
