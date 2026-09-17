# Budget-mode form and result view

Issue #153 connects the accepted #151 client without changing backend contracts.
The public planner defaults to its existing cash-target mode. A separate budget
mode requires a user-entered decimal budget (no prefilled investment amount),
selected months and optional original holdings. Explicit zero is valid; blank,
negative, non-finite, over-contract or sub-cent input is rejected before transport.

The request contains only budget, months, original holdings, three-year history,
zero cash-deduction rate and TWD. Fixed assumptions are visible; this is not a
personal after-tax forecast. No target, personal-tax, projection or reinvestment
fields are sent. Inputs are session-local and never newly persisted by the UI.

Mode switching discards both result caches. Changed valid inputs or invalid
inputs discard stale budget results. Resubmission removes prior results before
the API call, so failure cannot leave old numbers displayed as a new calculation.

Returned plans remain in backend order, using descriptive objective headings.
No grade, winner, synthetic alternate, risk category or total score is added.
The view shows budget/used/remaining funds, per-month cash, added whole shares,
original and resulting holdings, reasons, risks, assumptions and bounded-search
warnings. Missing cash and missing resulting holdings remain unavailable; empty
positions are distinct. Total-first explicitly warns that individual months may
decrease. Dates are not added to result cards. Existing cash-target details remain
unchanged behind their original mode.

Native Streamlit widgets are used without HTML/CSS or deprecated width flags.
See the [official widget reference](https://docs.streamlit.io/develop/api-reference/widgets/st.text_input).
Automated AppTest acceptance covers form routing, blank/zero/invalid inputs,
rendering, edit/failure invalidation and mode isolation. Browser/mobile visual
acceptance and owner usefulness acceptance are separate from automated tests.
