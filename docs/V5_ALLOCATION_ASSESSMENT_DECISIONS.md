# V5 allocation and assessment decisions

Status: owner-approved direction for V5-3 through V5-6

Tracking Issue: [#85](https://github.com/twstockanalysis/goodcat-website/issues/85)

Decision baseline: `main@12b08e75e3e1359ae33e6dbea6b62e580b0f243d`

## 1. Purpose

This document preserves the product decisions made after the first V5 data and
automatic-planning review. It prevents later data, algorithm and page work from
drifting back toward score-led ETF selection, unexplained capital requirements,
or page-first implementation.

This is a direction and acceptance document, not an implemented formula. The
current production contracts remain in force until a later Issue changes them
with deterministic tests.

Every subsequent V5 task must begin by fetching GitHub and confirming:

- the exact `origin/main` commit;
- merged and open PRs and their file scopes;
- the task Issue, active branch and worktree status;
- whether another contributor owns a shared file or module.

Repository Git and GitHub are the current-state authority. A handoff file or
earlier chat is context only and must not be treated as proof that a PR was
merged or that a branch is current.

## 2. Approved product boundaries

GoodCat keeps historical ETF quality, ETF risk, allocation feasibility and
owner-goal plan fit distinct.

### 2.1 MeowMeow historical quality grade

The historical quality grade evaluates one ETF from its historical investment
characteristics. The same ETF, evidence period and algorithm version must
produce the same score for every user.

Conceptually it asks whether the ETF has demonstrated repeatable historical
quality rather than merely a recent high distribution or price increase. Its
factors may include:

- sustained historical return rather than one recent period;
- downside severity and recovery behavior;
- distribution continuity and amount stability;
- long-run fee drag, size and liquidity characteristics.

It does not use:

- owner cash-flow targets, selected months, budget or holdings;
- constituent overlap with another ETF or portfolio;
- data completeness, source reliability or pipeline coverage as score factors.

Data sufficiency remains an internal calculation gate. Missing required inputs
must never lower an ETF score, become zero, or produce a fabricated neutral
grade. The internal pipeline either provides enough inputs for the algorithm or
does not publish a grade.

### 2.2 ETF risk grade

The risk grade evaluates one ETF's historical risk characteristics separately
from historical quality. A high-quality ETF is not automatically low risk, and
a higher-risk ETF is not automatically low quality.

Conceptually it considers:

- historical volatility;
- maximum decline and recovery duration;
- distribution-amount variability;
- the ETF's own industry, theme or constituent concentration;
- size and liquidity-related trading risk.

Pairwise or portfolio constituent overlap is not part of the single-ETF risk
grade. After an allocation exists, overlap may be shown as a plan-level risk
trade-off when formal constituent evidence is available.

### 2.3 MeowMeow planning grade

The planning grade evaluates a completed allocation plan against the conditions
submitted in that request. It is not the historical grade of any individual ETF
and does not claim that the plan is suitable for every aspect of the person's
financial circumstances.

It answers whether the plan fits this request's:

- target payment months;
- cash-flow target or investable budget;
- zero-to-N existing holdings;
- whole-share and maximum-five-added-ETF constraints;
- tax and cash-flow assumptions.

The allocation must be solved before the planning grade is calculated. A score
must never select ETFs first and then attempt to make the selected set feasible.

The planning-grade concept may compare:

- whether every requested month meets the target;
- additional-capital or budget efficiency;
- unnecessary cash-flow overshoot;
- number of added ETFs and operational complexity;
- concentration and formally supported overlap trade-offs;
- the historical quality and risk characteristics of the included ETFs.

The eventual formula, weights, thresholds and public grade names are deferred
to the V5-4 algorithm Issue. They require replay, sensitivity and deterministic
boundary tests before adoption.

## 3. Internal data gates are not ratings

Data acquisition, source reliability, freshness, missing-value handling and
coverage reconciliation remain mandatory internal responsibilities, but they do
not contribute positive or negative points to the three ratings.

The system must still preserve these data meanings:

- official `ACTUAL` dividend composition;
- eFortune estimated fallback;
- official `76W`;
- estimated realized capital gain that is not official `76W`;
- formal zero;
- missing or unavailable data;
- announced-but-not-yet-paid distributions versus paid history.

An internal gate may prevent a calculation when a required fact is unavailable.
It must not silently replace the missing value, assign a lower grade because of
the missing value, or describe estimated evidence as official evidence.

## 4. Allocation algorithm direction

The present engine is not simply a highest-score selector: it first compares
cash-flow-gap reduction per dollar and uses an internal quality score as a later
ordering key. However, feasibility, candidate ranking and quality are still too
coupled, the solver is bounded best effort rather than a proved global minimum,
and the universal 20 percent concentration repair can add large amounts of
capital.

V5-4 must replace that coupling with the following conceptual stages.

### 4.1 Build the calculable universe

Apply product and required-input gates without using quality or risk grades to
choose the result. Existing holdings remain visible even when they are not
eligible for an additional purchase.

### 4.2 Build explicit cash-flow scenarios

Keep at least these concepts distinct:

- historical month-specific base evidence;
- a conservative scenario;
- a latest-announced sensitivity scenario.

The latest distribution may illustrate a scenario but must not be treated as a
guarantee that the same amount will continue.

### 4.3 Solve the complete portfolio

Search ETF combinations and exact whole-share quantities together. Do not rank
individual ETFs first and then combine only the highest-ranked names, because
two individually weaker candidates may provide the best month-to-month
complement.

For cash-target mode:

1. include the cash flow and value of zero-to-N existing holdings;
2. require every selected month to meet the requested amount for a normal plan;
3. minimize required additional capital;
4. reduce avoidable overshoot and unnecessary ETF count;
5. limit added ETFs to at most five;
6. compare quality, risk, concentration and overlap only after feasibility.

For investable-budget mode:

1. do not exceed the submitted budget;
2. maximize useful selected-month cash flow and month-to-month balance;
3. use exact whole shares and at most five added ETFs;
4. compare quality, risk and concentration after respecting the budget.

If no complete cash-target plan exists, the response must use an explicit
no-complete-plan state. It must not display an ordinary result card that silently
misses a requested month.

### 4.4 Keep only non-dominated plans

A plan should be removed when another plan uses no more capital, has no larger
cash-flow shortfall, is no more complex and offers equal or better relevant
quality or risk evidence. The remaining plans form the meaningful trade-off set
from which two or three materially distinct cards may be selected.

More capital is not itself a benefit. A higher-capital card is justified only
when it produces a measurable improvement such as better monthly stability,
lower concentration, stronger historical characteristics or a clearer risk
trade-off.

## 5. Existing-holding treatment

Every submitted holding participates in the monthly cash-flow and portfolio
calculation. GoodCat does not silently sell or replace it.

For each existing ETF, the expanded result may explain its contribution to this
request through:

- supported target months and modeled cash contribution;
- reduction in the remaining target shortfall;
- reduction in required new capital because the ETF is already held;
- duplication or concentration added to the completed plan;
- the counterfactual change when the holding is excluded from the calculation.

User-facing language should describe contribution to this request as higher,
medium, limited, concentration-increasing or unavailable. It must not turn that
comparison into a buy or sell instruction or an absolute judgment that the ETF
is good or bad.

## 6. 00929 reference scenarios

00929 is the initial reference case for explaining why a monthly-cash result
depends on its evidence convention.

Reference facts used in the V5 discussion:

- reference close: TWD 29.13 on 2026-08-28;
- recent official payments: TWD 0.26 on 2026-07-13 and TWD 0.38 on
  2026-08-14;
- announced payment: TWD 0.38 for 2026-09-14;
- target: TWD 3,000 gross monthly cash, before transaction costs and personal
  tax effects.

The discussion produced three intentionally different illustrations:

- latest-announced continuation: 7,895 shares, or eight board lots costing
  approximately TWD 233,040;
- trailing 12 paid months totaling TWD 1.63 per share: approximately 22,086
  shares and TWD 643,365 for an average TWD 3,000 per month;
- current three-year same-calendar-month model: January is the binding month,
  requiring approximately 36,001 shares and TWD 1,048,709 after the model's
  per-share quantization.

These numbers are not interchangeable product promises. They demonstrate why
V5-4 must name the evidence convention, distinguish an annual monthly average
from an every-selected-month requirement, and keep gross and after-tax targets
separate.

The V5-1 candidate also exposed an internal status problem: 00929 was marked
inactive and an announced future payment caused future-data exclusions. V5-3
must reconcile active-product status and announced-versus-paid semantics before
using this ETF as an allocation acceptance case.

## 7. Result-card decisions

The accepted structural direction is two result cards in the normal case and no
more than three, with at most five added ETFs in each plan. The system must not
fabricate a duplicate plan merely to reach a fixed card count.

### 7.1 Collapsed card

The collapsed card may show:

- provisional strategy title;
- MeowMeow planning grade;
- ETF codes and count;
- required capital or used budget;
- modeled cash-flow summary;
- plan risk level;
- one short trade-off explanation.

It does not show achieved-month count. Meeting every requested month is a
precondition for a normal cash-target result card.

### 7.2 Expanded card

The expanded card may show:

- exact whole shares and capital by ETF;
- month-by-month cash flow, overshoot and assumptions;
- existing-holding contribution;
- tax and estimation treatment;
- concentration and formally supported overlap;
- exclusions, risks and limitations.

The expanded result card does not show source or data dates. This decision does
not remove dates from ETF detail, evidence or owner-administration pages.

### 7.3 Provisional strategy themes

For cash-target mode, the accepted concept is lower-, middle- and higher-capital
trade-offs. Provisional names are:

- capital-efficient;
- stable and balanced;
- diversified protection.

For investable-budget mode, the accepted concept is:

- cash-flow efficiency;
- monthly balance;
- more aggressive trade-off.

Final Chinese titles, capital bands, risk wording and whether all three cards
are useful remain deferred until V5-4 produces representative results.

## 8. V5 sequence

- V5-3: acquire and reconcile the data required by the accepted result and
  algorithm contract, including 00929 status and dividend-event semantics.
- V5-4: implement and test the allocation algorithm, cash-target and budget
  modes, plan-fit grading boundary and deterministic result selection. Do not
  redesign the result page in this milestone.
- V5-5: integrate the accepted algorithm output into compact and expandable
  result cards, then perform real-page review.
- V5-6: replay the accepted cases, record remaining limits, complete regression
  and obtain owner usefulness acceptance.

V4-8, release-candidate selection, formal deployment and SEC-4 remain paused
until V5-6 owner acceptance.

## 9. Deferred decisions

### Owner clarification for #139

Allow an optional user-entered additional-capital ceiling in cash-target mode.
All three strategies search within it; omitted/null remains unlimited and zero
allows no new investment. Existing holdings do not consume this allowance.
Report an explicit incomplete state when no complete plan is found within it;
do not merely hide over-budget plans after searching. This authorizes neither
automatic caps nor the previously rejected minimum-improvement filter.

### Owner clarification for #137

Keep distinct strategy portfolios without the proposed 1% improvement filter.
Improve the direct capital-efficient, monthly-balanced and diversified search
instead. Exact duplicate share combinations remain omitted; small improvements
must not be described as material benefits. This decision does not approve
planning-grade formulas, new risk labels, capital caps or scenario changes.

The following must not be guessed during implementation:

- exact formulas, weights and grade thresholds;
- the public letter or word labels for planning and risk grades;
- the capital ranges or frontier tolerance for selecting alternate plans;
- final result-card titles and copy;
- whether one valid plan or a non-card explanation is used when two materially
  distinct plans do not exist;
- exact conservative cash-flow methodology and tax-default presentation.

Each deferred item must be decided from representative V5-4 output and tested
before it becomes a public contract.
