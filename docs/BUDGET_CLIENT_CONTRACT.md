# Target-free budget frontend client

Issue #151 provides client plumbing, not a budget form or result-page rollout.
`fetch_budget_results` uses the existing public `post_json` transport for
`/api/v1/allocation-plans/budget-results`, with a caller-overridable 60-second
timeout. It sends the supplied request unchanged. HTTP, connection and security
behavior remain those of the shared transport. It is exported by `api_client`.

The independent frontend validator returns the original response without mutation,
sorting, coercion, zero-filling or backend imports. It checks public stateless
markers, the budget methodology, primary and ordered unique alternate objectives,
same budget/months/snapshot/date/original holdings across plans, whole shares,
at most five unique additions, exact and rounded costs, and used/remaining amounts.
Month rows must exactly match selected months. Current and modeled cash can be
null; missing is not zero. It rejects target statuses and per-month target fields.

Optional descriptive metrics and backend explanations remain intact. Their
display validation belongs to the eventual budget renderer; this client does
not adopt a grade or normalize them. Nested internal scoring keys are rejected,
but explanatory text about scores or unavailable evidence is not a forbidden
field. The validator is a client consumption boundary, not a replacement for
the full backend model, solver feasibility checks or a security authority.

Financial amounts are checked with Decimal arithmetic in an isolated precision
context; invalid numeric representations become `APIResponseError`. It does not
recompute cash from rounded components or infer target attainment.

No UI, investment defaults, source data, ACTUAL/estimated/formal 76W semantics,
allocation algorithms, persistence or deployment is changed. Budget forms,
compact/expanded cards and real-page acceptance remain subsequent V5-5 work.
