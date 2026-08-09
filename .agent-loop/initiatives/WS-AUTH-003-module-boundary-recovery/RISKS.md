# Risks

| Risk | Consequence | Control |
|---|---|---|
| Frozen ledger becomes permanent | porous boundary survives | count cannot grow; touched entries must be removed; final closure requires zero |
| API becomes a re-export dump | internals remain coupled under a new path | leak tests reject ORM/session/repository/concrete service exposure |
| Feature work bypasses repair | new debt accumulates | CI separately rejects new inbound and outbound imports |
| Capability extraction changes behavior | authorization regression | small touched scope, exact behavior ledger, focused concurrency proof |
| Mechanical splitting hides cohesion | more files but same spaghetti | split only complete capabilities and transaction ownership |
| POL-03A resumes on stale design | first proof fails | amend its contract after foundation and before implementation |
| REV starts with temporary exceptions | new subsystem begins coupled | zero-exception precondition for REV's AUTH/ART dependencies |
| Other worktrees conflict | overwritten work | dedicated branches; reconcile current main before each PR |
