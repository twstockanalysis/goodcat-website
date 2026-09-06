# Existing ETF additions and overlap

An existing ETF may participate in the V5 complete-portfolio search when its
price, product, cash-flow, risk and component gates pass. Comparing the ETF
against a portfolio containing itself must not independently prohibit adding
shares to that same position.

For existing ETF codes only, `EXCESSIVE_HOLDING_OVERLAP` and
`HOLDING_OVERLAP_UNAVAILABLE` are trade-off warnings. The measured overlap and
snapshot dates remain unchanged. Unavailable overlap stays null, never zero.
All other exclusions remain mandatory, and distinct new ETF codes keep the
existing overlap gate. No holdings are removed or sold by this change.

This fixes the V5-3D replay's self-overlap eligibility defect. Bounded-search
ordering can still affect the resulting capital; the change does not promise
global optimality or that every holding request costs less than zero holdings.
