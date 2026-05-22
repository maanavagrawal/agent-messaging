# Lessons

- When a user pivots the project direction after prior implementation work, treat the new prompt as authoritative and clear stale architecture assumptions before planning or coding.
- For Phase 1 scaffolds with explicit exclusions, keep forward-compatibility tables inert unless the spec asks for active write paths.
- When the user explicitly says not to wait for approval after invoking a review skill, auto-apply low-risk review fixes, document the decisions in `tasks/todo.md`, and keep moving.
- For harness work, do not call the phase done after fixture tests only; replay at least one real tool log and inspect the captured events before finalizing.
- When the user invokes gstack review skills, use the gstack workflow as the planning source of truth instead of compressing it into a quick summary; if they say to use recommended options, record those decisions explicitly before implementation.
- For fixlog frontend design, do not over-pack Human and Agent views into one dashboard. The user's product taste is simpler tabbed modes with a notebook/discourse feel for advanced agent broadcasts, not a Stack Overflow clone or dense command center.
- Before implementing after a context transition, re-read the user's latest concrete target and ignore unrelated unchecked plan sections; do not switch from the active phase to a later design plan unless the user explicitly asks for that plan.
- Before turning fixlog mockups into UI, reconcile every visible component against existing backend fields/routes. Hide or label future-only affordances instead of shipping mock UI that suggests unsupported discourse, recommendations, ownership, or creation flows.
- For fixlog frontend implementation, default to less UI. It is better to ship a smaller truthful surface and add later than to make the user manually remove irrelevant mockup-driven components.
- When adding a browser template for an API-shaped path, add the matching web route and a regression test in the same change; otherwise local browser inspection falls through to auth-only API handlers and looks broken.
- For auto-sandbox verification, model the real sequence as setup -> reproduce -> apply fix -> verify; writing fixed files before setup can make setup commands silently erase the fix.
- For onboarding pages, put the actual setup action inside the onboarding flow. Explanatory steps plus a separate form still feel unclear compared with Moltbook-style setup, where the command/action is embedded directly in the first-run path.
