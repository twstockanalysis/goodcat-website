# Descriptive planning metrics presentation

Issue #149 follows #147/#148. The existing cash-target result page shows the same
metric rows and units for each returned plan, in original response order. It
does not introduce scores, normalizers, grades, risk labels or new calculations.
The budget input/result frontend remains outside this presentation-only change.

The frontend matches optional `plan_metrics` by unique `plan_key`, checking mode,
methodology, precision basis, status, attainment and selected months against the
plan. Absent, duplicate or incompatible metadata yields an unavailable column,
not a reassigned metric or a failed original result page. Missing, non-finite,
negative and out-of-range percentages display as unavailable, never zero.
Known zero displays as `0.00`. Unavailable source plans show no calculated numeric
metrics; a known submitted capital limit remains visible, matching the contract.
Backend issue messages remain visible. No frontend/backend model coupling is added.

Cash summaries and capital are displayed in NTD to two decimals. Percentages
are already percentages, not fractions. Values use the backend displayed-response
basis and are not recomputed from rounded frontend cash. Attainment follows status,
not a rounded cash threshold. The table has no winner highlight or selection logic;
existing cards, details, scheme selection and portfolio projection remain unchanged.

The explanatory text distinguishes month spread from risk, position concentration
from underlying asset overlap, and capital usage from desirability. It includes
original holdings and does not imply ETF quality or personal suitability.
ACTUAL, estimated, formal 76W, missing and zero semantics remain unchanged.

Implementation uses native Streamlit 1.60.0 dataframe sizing (`width="stretch"`,
`height="content"`) per the [versioned official reference](https://docs.streamlit.io/1.60.0/develop/api-reference/data/st.dataframe).
No deprecated width flag, custom HTML or CSS is introduced.
