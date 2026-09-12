"""V5-4 deterministic complete-portfolio search and Pareto filtering.

The module is deliberately independent from database and public API models.  It
receives only already-gated candidates, never uses an ETF quality score to
select a feasible portfolio, and returns bounded-search evidence explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from typing import Mapping, Sequence


_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class CompletePortfolioCandidate:
    etf_code: str
    reference_price: Decimal
    monthly_cash_per_share: tuple[Decimal, ...]


@dataclass(frozen=True, slots=True)
class CompletePortfolioPlan:
    shares: tuple[tuple[str, int], ...]
    additional_capital: Decimal
    monthly_added_cash: tuple[tuple[int, Decimal], ...]
    monthly_resulting_cash: tuple[tuple[int, Decimal], ...]
    monthly_shortfall: tuple[tuple[int, Decimal], ...]
    monthly_overshoot: tuple[tuple[int, Decimal], ...]
    max_position_pct: Decimal

    @property
    def added_etf_count(self) -> int:
        return len(self.shares)

    @property
    def total_shortfall(self) -> Decimal:
        return sum((value for _, value in self.monthly_shortfall), _ZERO)

    @property
    def total_overshoot(self) -> Decimal:
        return sum((value for _, value in self.monthly_overshoot), _ZERO)

    @property
    def complete(self) -> bool:
        return self.total_shortfall == 0

    @property
    def month_imbalance(self) -> Decimal:
        values = [value for _, value in self.monthly_resulting_cash]
        return max(values, default=_ZERO) - min(values, default=_ZERO)


@dataclass(frozen=True, slots=True)
class CompletePortfolioSearch:
    frontier: tuple[CompletePortfolioPlan, ...]
    explored_states: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class BudgetPortfolioPlan:
    shares: tuple[tuple[str, int], ...]
    used_budget: Decimal
    monthly_added_cash: tuple[tuple[int, Decimal], ...]
    monthly_resulting_cash: tuple[tuple[int, Decimal], ...]

    @property
    def added_etf_count(self) -> int:
        return len(self.shares)

    @property
    def minimum_month_cash(self) -> Decimal:
        return min((value for _, value in self.monthly_resulting_cash), default=_ZERO)

    @property
    def total_month_cash(self) -> Decimal:
        return sum((value for _, value in self.monthly_resulting_cash), _ZERO)

    @property
    def month_imbalance(self) -> Decimal:
        values = [value for _, value in self.monthly_resulting_cash]
        return max(values, default=_ZERO) - min(values, default=_ZERO)


@dataclass(frozen=True, slots=True)
class BudgetPortfolioSearch:
    frontier: tuple[BudgetPortfolioPlan, ...]
    explored_states: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class _State:
    shares: tuple[tuple[str, int], ...]
    capital: Decimal
    monthly_added: tuple[Decimal, ...]


def _ceil_quantity(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def _validated_candidates(
    candidates: Sequence[CompletePortfolioCandidate],
) -> tuple[CompletePortfolioCandidate, ...]:
    ordered = sorted(candidates, key=lambda item: item.etf_code)
    codes = [item.etf_code for item in ordered]
    if len(codes) != len(set(codes)):
        raise ValueError("candidate ETF codes must be unique")
    for item in ordered:
        if not item.etf_code or item.reference_price <= 0:
            raise ValueError("candidate code and positive price are required")
        if len(item.monthly_cash_per_share) != 12:
            raise ValueError("candidate monthly cash must contain twelve months")
        if any(value < 0 for value in item.monthly_cash_per_share):
            raise ValueError("candidate monthly cash cannot be negative")
    return tuple(ordered)


def _validated_months(selected_months: Sequence[int]) -> tuple[int, ...]:
    months = tuple(sorted(selected_months))
    if not months or len(months) != len(set(months)):
        raise ValueError("selected months must be non-empty and unique")
    if any(month < 1 or month > 12 for month in months):
        raise ValueError("selected months must be between 1 and 12")
    return months


def _plan(
    state: _State,
    months: tuple[int, ...],
    current_cash: Mapping[int, Decimal],
    target_cash: Mapping[int, Decimal],
    current_value: Mapping[str, Decimal],
    reference_prices: Mapping[str, Decimal],
) -> CompletePortfolioPlan:
    added = tuple(zip(months, state.monthly_added, strict=True))
    shortfall = []
    overshoot = []
    for position, month in enumerate(months):
        modeled = current_cash.get(month, _ZERO) + state.monthly_added[position]
        target = target_cash[month]
        shortfall.append((month, max(target - modeled, _ZERO)))
        overshoot.append((month, max(modeled - target, _ZERO)))
    resulting_values = dict(current_value)
    for code, quantity in state.shares:
        resulting_values[code] = (
            resulting_values.get(code, _ZERO)
            + reference_prices[code] * quantity
        )
    total_value = sum(resulting_values.values(), _ZERO)
    max_position_pct = (
        max(resulting_values.values(), default=_ZERO) / total_value * Decimal("100")
        if total_value > 0
        else _ZERO
    )
    return CompletePortfolioPlan(
        shares=state.shares,
        additional_capital=state.capital,
        monthly_added_cash=added,
        monthly_resulting_cash=tuple(
            (month, current_cash.get(month, _ZERO) + amount)
            for month, amount in added
        ),
        monthly_shortfall=tuple(shortfall),
        monthly_overshoot=tuple(overshoot),
        max_position_pct=max_position_pct,
    )


def _plan_order(plan: CompletePortfolioPlan) -> tuple[object, ...]:
    return (
        plan.total_shortfall,
        plan.additional_capital,
        plan.total_overshoot,
        plan.added_etf_count,
        plan.max_position_pct,
        plan.shares,
    )


def _dominance_values(plan: CompletePortfolioPlan) -> tuple[Decimal, ...]:
    return (
        plan.total_shortfall, plan.additional_capital, plan.total_overshoot,
        plan.month_imbalance, plan.max_position_pct, Decimal(plan.added_etf_count),
    )


def _values_dominate(
    left_values: tuple[Decimal, ...], right_values: tuple[Decimal, ...],
) -> bool:
    return all(a <= b for a, b in zip(left_values, right_values, strict=True)) and any(
        a < b for a, b in zip(left_values, right_values, strict=True)
    )


def _dominates(left: CompletePortfolioPlan, right: CompletePortfolioPlan) -> bool:
    return _values_dominate(_dominance_values(left), _dominance_values(right))


def cash_target_plan_order(
    plan: CompletePortfolioPlan, objective: str,
) -> tuple[object, ...]:
    """Use the same feasibility-first order for search and final selection."""
    if objective == "CAPITAL_EFFICIENT":
        return _plan_order(plan)
    if objective == "MONTHLY_BALANCED":
        return (
            plan.total_shortfall, plan.month_imbalance, plan.total_overshoot,
            plan.additional_capital, plan.added_etf_count, plan.shares,
        )
    if objective == "DIVERSIFIED_PROTECTION":
        return (
            plan.total_shortfall, plan.max_position_pct, plan.additional_capital,
            plan.total_overshoot, plan.added_etf_count, plan.shares,
        )
    raise ValueError("unknown V5-4 plan objective")


def _refinement_quantities(
    candidate: CompletePortfolioCandidate,
    plan: CompletePortfolioPlan,
    current_value: Mapping[str, Decimal],
    prices: Mapping[str, Decimal],
    objective: str,
) -> set[int]:
    """Integer neighbours of cash-line or position-value intersections."""
    crossings: list[Decimal] = []
    if objective == "MONTHLY_BALANCED":
        cash = plan.monthly_resulting_cash
        for i, (month, amount) in enumerate(cash):
            for other_month, other_amount in cash[i + 1:]:
                slope = (candidate.monthly_cash_per_share[month - 1]
                         - candidate.monthly_cash_per_share[other_month - 1])
                if slope:
                    crossings.append((other_amount - amount) / slope)
    elif objective == "DIVERSIFIED_PROTECTION":
        values = dict(current_value)
        for code, quantity in plan.shares:
            values[code] = values.get(code, _ZERO) + prices[code] * quantity
        own = values.get(candidate.etf_code, _ZERO)
        other = max(
            (value for code, value in values.items() if code != candidate.etf_code),
            default=_ZERO,
        )
        crossings.append((other - own) / candidate.reference_price)
    quantities: set[int] = set()
    for crossing in crossings:
        if crossing > 0:
            ceiling = _ceil_quantity(crossing)
            quantities.update((max(1, ceiling - 1), ceiling))
    return quantities


def _non_dominated(
    plans: Sequence[CompletePortfolioPlan],
) -> tuple[CompletePortfolioPlan, ...]:
    unique = {plan.shares: plan for plan in plans}
    ordered = sorted(unique.values(), key=_plan_order)
    # Cache each vector once and compare only surviving skyline members.
    # Strict Pareto dominance is transitive, so discarded members cannot
    # change the final set. Later ties may dominate an earlier member.
    skyline: list[tuple[CompletePortfolioPlan, tuple[Decimal, ...]]] = []
    for plan in ordered:
        values = _dominance_values(plan)
        if any(_values_dominate(other_values, values) for _, other_values in skyline):
            continue
        skyline = [
            (other, other_values) for other, other_values in skyline
            if not _values_dominate(values, other_values)
        ]
        skyline.append((plan, values))
    return tuple(plan for plan, _ in skyline)


def solve_cash_target_frontier(
    candidates: Sequence[CompletePortfolioCandidate],
    *,
    selected_months: Sequence[int],
    target_cash_by_month: Mapping[int, Decimal],
    current_cash_by_month: Mapping[int, Decimal] | None = None,
    current_value_by_code: Mapping[str, Decimal] | None = None,
    max_added_etfs: int = 5,
    beam_width: int = 64,
    max_expansions: int = 20_000,
    objective: str = "CAPITAL_EFFICIENT",
    max_additional_capital: Decimal | None = None,
) -> CompletePortfolioSearch:
    """Search whole-share combinations and return a deterministic Pareto set.

    Each expansion adds an exact integer batch sized around a remaining monthly
    constraint.  The beam bound is explicit: a truncated result is never proof
    of a global minimum.
    """

    ordered = _validated_candidates(candidates)
    if max_additional_capital is not None and (
        not max_additional_capital.is_finite() or max_additional_capital < 0
    ):
        raise ValueError("additional capital ceiling must be finite and non-negative")
    months = _validated_months(selected_months)
    current = dict(current_cash_by_month or {})
    current_value = dict(current_value_by_code or {})
    prices = {item.etf_code: item.reference_price for item in ordered}
    if max_added_etfs < 1 or max_added_etfs > 5:
        raise ValueError("max_added_etfs must be between one and five")
    if beam_width < 1 or max_expansions < 1:
        raise ValueError("search bounds must be positive")
    if any(month not in target_cash_by_month for month in months):
        raise ValueError("every selected month requires a target")
    if any(target_cash_by_month[month] < 0 for month in months):
        raise ValueError("cash targets cannot be negative")
    if any(current.get(month, _ZERO) < 0 for month in months):
        raise ValueError("current cash cannot be negative")
    if any(not code or value <= 0 for code, value in current_value.items()):
        raise ValueError("current holding values require codes and positive values")

    initial = _State(
        shares=(),
        capital=_ZERO,
        monthly_added=tuple(_ZERO for _ in months),
    )
    initial_plan = _plan(
        initial, months, current, target_cash_by_month, current_value, prices
    )
    def order(plan: CompletePortfolioPlan) -> tuple[object, ...]:
        return cash_target_plan_order(plan, objective)

    order(initial_plan)  # Validate even when no additions are needed.
    if initial_plan.complete:
        return CompletePortfolioSearch((initial_plan,), 1, False)

    active = [initial]
    best_partial = [initial_plan]
    feasible: list[CompletePortfolioPlan] = []
    seen = {initial.shares}
    explored = 1
    truncated = False
    round_limit = len(months) * max_added_etfs + 2

    for _ in range(round_limit):
        stop_search = False
        next_states: list[_State] = []
        for state in active:
            state_map = dict(state.shares)
            state_plan = _plan(
                state, months, current, target_cash_by_month, current_value, prices
            )
            remaining = dict(state_plan.monthly_shortfall)
            for candidate in ordered:
                is_new = candidate.etf_code not in state_map
                if is_new and len(state_map) >= max_added_etfs:
                    continue
                quantities = {1}
                if objective != "CAPITAL_EFFICIENT":
                    quantities.update(_refinement_quantities(
                        candidate, state_plan, current_value, prices, objective
                    ))
                for month in months:
                    per_share = candidate.monthly_cash_per_share[month - 1]
                    if remaining[month] <= 0 or per_share <= 0:
                        continue
                    covering = _ceil_quantity(remaining[month] / per_share)
                    quantities.add(covering)
                    quantities.add(max(1, covering - 1))
                    quantities.add(max(1, covering // 2))
                if max_additional_capital is not None:
                    affordable = int(
                        (max_additional_capital - state.capital) // candidate.reference_price
                    )
                    if affordable < 1:
                        continue
                    # Explore the boundary, rather than merely rejecting an
                    # over-budget covering/refinement batch after the search.
                    quantities.update((affordable, max(1, affordable - 1)))
                    quantities = {q for q in quantities if q <= affordable}
                for quantity in sorted(quantities):
                    if explored >= max_expansions:
                        truncated = True
                        stop_search = True
                        break
                    new_map = dict(state_map)
                    new_map[candidate.etf_code] = (
                        new_map.get(candidate.etf_code, 0) + quantity
                    )
                    signature = tuple(sorted(new_map.items()))
                    if signature in seen:
                        continue
                    if max_additional_capital is not None:
                        exact_cost = state.capital + candidate.reference_price * quantity
                        displayed_cost = sum((
                            (prices[code] * count).quantize(
                                Decimal("0.01"), rounding=ROUND_HALF_UP
                            ) for code, count in signature
                        ), _ZERO)
                        if (exact_cost > max_additional_capital
                                or displayed_cost > max_additional_capital):
                            continue
                    seen.add(signature)
                    monthly_added = tuple(
                        state.monthly_added[position]
                        + candidate.monthly_cash_per_share[month - 1] * quantity
                        for position, month in enumerate(months)
                    )
                    new_state = _State(
                        shares=signature,
                        capital=(
                            state.capital + candidate.reference_price * quantity
                        ),
                        monthly_added=monthly_added,
                    )
                    explored += 1
                    candidate_plan = _plan(
                        new_state,
                        months,
                        current,
                        target_cash_by_month,
                        current_value,
                        prices,
                    )
                    if candidate_plan.complete:
                        feasible.append(candidate_plan)
                        if objective != "CAPITAL_EFFICIENT" and (
                            not state_plan.complete or order(candidate_plan) < order(state_plan)
                        ):
                            next_states.append(new_state)
                    else:
                        next_states.append(new_state)
                        best_partial.append(candidate_plan)
                if stop_search:
                    break
            if stop_search:
                break
        if len(feasible) > beam_width * 4:
            feasible = sorted(_non_dominated(feasible), key=order)[:beam_width]
            truncated = True
        if len(best_partial) > beam_width * 4:
            best_partial.sort(key=order)
            best_partial = best_partial[: beam_width * 2]
            truncated = True
        if stop_search or not next_states:
            active = next_states
            break
        next_states.sort(
            key=lambda state: order(
                _plan(
                    state,
                    months,
                    current,
                    target_cash_by_month,
                    current_value,
                    prices,
                )
            )
        )
        if len(next_states) > beam_width:
            truncated = True
        active = next_states[:beam_width]

    if active:
        truncated = True
    frontier = _non_dominated(feasible if feasible else best_partial)
    return CompletePortfolioSearch(frontier, explored, truncated)


def _budget_order(plan: BudgetPortfolioPlan) -> tuple[object, ...]:
    return (
        -plan.minimum_month_cash,
        -plan.total_month_cash,
        plan.month_imbalance,
        -plan.used_budget,
        plan.added_etf_count,
        plan.shares,
    )


def _budget_dominates(left: BudgetPortfolioPlan, right: BudgetPortfolioPlan) -> bool:
    left_cash = dict(left.monthly_resulting_cash)
    right_cash = dict(right.monthly_resulting_cash)
    no_worse = (
        left.used_budget <= right.used_budget
        and left.added_etf_count <= right.added_etf_count
        and all(left_cash[month] >= value for month, value in right_cash.items())
    )
    strictly_better = (
        left.used_budget < right.used_budget
        or left.added_etf_count < right.added_etf_count
        or any(left_cash[month] > value for month, value in right_cash.items())
    )
    return no_worse and strictly_better


def _budget_strategy_order(plan, objective, minimum_cash_floor):
    if objective == "MONTHLY_BALANCED":
        return (max(minimum_cash_floor - plan.minimum_month_cash, _ZERO),
                plan.month_imbalance, *_budget_order(plan))
    if objective == "TOTAL_MONTH_CASH":
        return (-plan.total_month_cash, *_budget_order(plan))
    return _budget_order(plan)


def _non_dominated_budget(
    plans: Sequence[BudgetPortfolioPlan],
    objective: str = "MINIMUM_THEN_TOTAL_MONTH_CASH",
    minimum_cash_floor: Decimal = _ZERO,
) -> tuple[BudgetPortfolioPlan, ...]:
    ordered = sorted({plan.shares: plan for plan in plans}.values(),
                     key=lambda p: _budget_strategy_order(p, objective, minimum_cash_floor))
    skyline: list[tuple[BudgetPortfolioPlan, tuple[Decimal, ...]]] = []
    for plan in ordered:
        values = (plan.used_budget, Decimal(plan.added_etf_count), *(
            -cash for _, cash in plan.monthly_resulting_cash
        ))
        if objective == "MONTHLY_BALANCED":
            values += (plan.month_imbalance,)
        if any(_values_dominate(other, values) for _, other in skyline):
            continue
        skyline = [(p, v) for p, v in skyline if not _values_dominate(values, v)]
        skyline.append((plan, values))
    return tuple(plan for plan, _ in skyline)


def solve_budget_frontier(
    candidates: Sequence[CompletePortfolioCandidate],
    *,
    selected_months: Sequence[int],
    investable_budget: Decimal,
    current_cash_by_month: Mapping[int, Decimal] | None = None,
    max_added_etfs: int = 5,
    beam_width: int = 64,
    max_expansions: int = 20_000,
    objective: str = "MINIMUM_THEN_TOTAL_MONTH_CASH",
    seed_plan: BudgetPortfolioPlan | None = None,
) -> BudgetPortfolioSearch:
    """Build a bounded whole-share budget frontier without exceeding budget."""

    if any(
        not item.reference_price.is_finite()
        or any(not cash.is_finite() for cash in item.monthly_cash_per_share)
        for item in candidates
    ):
        raise ValueError("budget candidate facts must be finite")
    ordered = _validated_candidates(candidates)
    months = _validated_months(selected_months)
    current = dict(current_cash_by_month or {})
    if not investable_budget.is_finite() or investable_budget < 0:
        raise ValueError("investable budget must be finite and non-negative")
    if any(not current.get(month, _ZERO).is_finite()
           or current.get(month, _ZERO) < 0 for month in months):
        raise ValueError("current cash must be finite and non-negative")
    if (max_added_etfs < 1 or max_added_etfs > 5
            or beam_width < 1 or max_expansions < 1):
        raise ValueError("invalid budget search bounds")
    if objective not in {"MINIMUM_THEN_TOTAL_MONTH_CASH", "MONTHLY_BALANCED", "TOTAL_MONTH_CASH"}:
        raise ValueError("unknown budget objective")
    if objective != "MINIMUM_THEN_TOTAL_MONTH_CASH" and seed_plan is None:
        raise ValueError("alternate searches require the primary plan")
    if objective == "MINIMUM_THEN_TOTAL_MONTH_CASH" and seed_plan is not None:
        raise ValueError("the primary search cannot be seeded")
    if seed_plan is not None:
        by_code = {c.etf_code: c for c in ordered}
        if (len(seed_plan.shares) > max_added_etfs
                or len(dict(seed_plan.shares)) != len(seed_plan.shares)
                or any(c not in by_code or not isinstance(q, int) or q <= 0
                       for c, q in seed_plan.shares)):
            raise ValueError("invalid primary shares")
        exact = sum((by_code[c].reference_price * q for c, q in seed_plan.shares), _ZERO)
        displayed = sum(((by_code[c].reference_price * q).quantize(
            Decimal('.01'), rounding=ROUND_HALF_UP) for c, q in seed_plan.shares), _ZERO)
        added = tuple((m, sum((by_code[c].monthly_cash_per_share[m - 1] * q
                              for c, q in seed_plan.shares), _ZERO)) for m in months)
        reconstructed = BudgetPortfolioPlan(
            tuple(sorted(seed_plan.shares)), exact, added,
            tuple((m, current.get(m, _ZERO) + cash) for m, cash in added),
        )
        if seed_plan != reconstructed or exact > investable_budget or displayed > investable_budget:
            raise ValueError("primary plan does not match this request")
    floor = seed_plan.minimum_month_cash if seed_plan is not None else _ZERO
    order = lambda p: _budget_strategy_order(p, objective, floor)
    retain = lambda plans: _non_dominated_budget(plans, objective, floor)

    initial = _State((), _ZERO, tuple(_ZERO for _ in months))
    active = [initial]
    plan_pool = [BudgetPortfolioPlan(
        (), _ZERO, tuple((month, _ZERO) for month in months),
        tuple((month, current.get(month, _ZERO)) for month in months),
    )]
    if seed_plan is not None:
        plan_pool.append(seed_plan)
    prices = {item.etf_code: item.reference_price for item in ordered}
    seen = {initial.shares}
    explored = 1
    truncated = False
    for _ in range(max_added_etfs):
        stop_search = False
        next_states = []
        for state in active:
            present = dict(state.shares)
            for candidate in ordered:
                if candidate.etf_code in present:
                    continue
                if not any(candidate.monthly_cash_per_share[m - 1] > 0 for m in months):
                    continue
                affordable = int(
                    (investable_budget - state.capital) // candidate.reference_price
                )
                if affordable <= 0:
                    continue
                quantities = {1, affordable, max(1, affordable // 2)}
                for quantity in sorted(quantities):
                    if explored >= max_expansions:
                        truncated = True
                        stop_search = True
                        break
                    new_map = dict(present)
                    new_map[candidate.etf_code] = quantity
                    signature = tuple(sorted(new_map.items()))
                    if signature in seen:
                        continue
                    capital = state.capital + candidate.reference_price * quantity
                    displayed_capital = sum((
                        (prices[code] * count).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        ) for code, count in signature
                    ), _ZERO)
                    if capital > investable_budget or displayed_capital > investable_budget:
                        continue
                    seen.add(signature)
                    new_state = _State(
                        signature,
                        capital,
                        tuple(
                            state.monthly_added[position]
                            + candidate.monthly_cash_per_share[month - 1] * quantity
                            for position, month in enumerate(months)
                        ),
                    )
                    explored += 1
                    next_states.append(new_state)
                    plan_pool.append(
                        BudgetPortfolioPlan(
                            new_state.shares,
                            new_state.capital,
                            tuple(zip(months, new_state.monthly_added, strict=True)),
                            tuple(
                                (
                                    month,
                                    current.get(month, _ZERO)
                                    + new_state.monthly_added[position],
                                )
                                for position, month in enumerate(months)
                            ),
                        )
                    )
                if stop_search:
                    break
            if stop_search:
                break
        if stop_search:
            break
        if not next_states:
            break
        if len(plan_pool) > beam_width * 4:
            plan_pool = list(retain(plan_pool))[:beam_width]
            truncated = True
        next_states.sort(
            key=lambda state: order(
                BudgetPortfolioPlan(
                    state.shares,
                    state.capital,
                    tuple(zip(months, state.monthly_added, strict=True)),
                    tuple(
                        (
                            month,
                            current.get(month, _ZERO)
                            + state.monthly_added[position],
                        )
                        for position, month in enumerate(months)
                    ),
                )
            )
        )
        if len(next_states) > beam_width:
            truncated = True
        active = next_states[:beam_width]

    frontier = retain(plan_pool + ([seed_plan] if seed_plan is not None else []))
    if objective == "MONTHLY_BALANCED":
        frontier = tuple(p for p in frontier if p.minimum_month_cash >= floor)
    if objective != "MINIMUM_THEN_TOTAL_MONTH_CASH":
        return _refine_budget_frontier(
            frontier, ordered, months, current, investable_budget,
            max_added_etfs, explored, max_expansions, truncated, objective, floor,
        )
    return _refine_budget_frontier(
        frontier, ordered, months, current, investable_budget,
        max_added_etfs, explored, max_expansions, truncated,
    )


def _budget_exchange_quantities(
    plan: BudgetPortfolioPlan,
    source: CompletePortfolioCandidate,
    destination: CompletePortfolioCandidate,
    source_quantity: int,
    remaining_budget: Decimal,
    minimum_cash_floor: Decimal | None = None,
) -> tuple[int, ...]:
    """Integer neighbours of continuous month-line crossings for one exchange.

    This removes only proposed additions, never original holdings. The actual
    destination quantity is floored and independently budget-checked later.
    """
    quantities = {0, source_quantity}
    cash = plan.monthly_resulting_cash
    price_ratio = source.reference_price / destination.reference_price
    free_shares = remaining_budget / destination.reference_price
    intercepts = [amount + free_shares * destination.monthly_cash_per_share[m - 1]
                  for m, amount in cash]
    slopes = [price_ratio * destination.monthly_cash_per_share[m - 1]
              - source.monthly_cash_per_share[m - 1] for m, _ in cash]
    if minimum_cash_floor is not None:
        for intercept, slope in zip(intercepts, slopes, strict=True):
            if slope:
                crossing = (minimum_cash_floor - intercept) / slope
                if 0 < crossing < source_quantity:
                    ceiling = _ceil_quantity(crossing)
                    quantities.update(q for q in (ceiling - 1, ceiling, ceiling + 1)
                                      if 0 <= q <= source_quantity)
    for i in range(len(cash)):
        for j in range(i + 1, len(cash)):
            difference = slopes[i] - slopes[j]
            if not difference:
                continue
            crossing = (intercepts[j] - intercepts[i]) / difference
            if 0 < crossing < source_quantity:
                ceiling = _ceil_quantity(crossing)
                quantities.update(q for q in (ceiling - 1, ceiling, ceiling + 1)
                                  if 0 <= q <= source_quantity)
    return tuple(sorted(quantities))


def _refine_budget_frontier(
    frontier: tuple[BudgetPortfolioPlan, ...],
    candidates: tuple[CompletePortfolioCandidate, ...],
    months: tuple[int, ...],
    current: Mapping[int, Decimal],
    budget: Decimal,
    max_added_etfs: int,
    explored: int,
    max_expansions: int,
    truncated: bool,
    objective: str = "MINIMUM_THEN_TOTAL_MONTH_CASH",
    minimum_cash_floor: Decimal = _ZERO,
) -> BudgetPortfolioSearch:
    """Improve the incumbent using only unused state capacity from batch search."""
    by_code = {c.etf_code: c for c in candidates}
    order = lambda p: _budget_strategy_order(p, objective, minimum_cash_floor)
    retain = lambda plans: _non_dominated_budget(plans, objective, minimum_cash_floor)
    seen = {p.shares for p in frontier}
    incumbent = frontier[0]
    # No available refinement work when the original search exhausted its cap
    # or returned no additions. Preserve that result exactly.
    if not incumbent.shares or explored >= max_expansions:
        return BudgetPortfolioSearch(frontier, explored, truncated)
    while incumbent.shares and explored < max_expansions:
        start = incumbent
        remaining = budget - start.used_budget
        improved = []
        for source_code, source_quantity in start.shares:
            source = by_code[source_code]
            for destination in candidates:
                if destination.etf_code == source_code:
                    continue
                if not any(destination.monthly_cash_per_share[m - 1] > 0 for m in months):
                    continue
                removals = _budget_exchange_quantities(
                    start, source, destination, source_quantity, remaining,
                    minimum_cash_floor if objective == "MONTHLY_BALANCED" else None,
                )
                for removed in removals:
                    available = remaining + source.reference_price * removed
                    affordable = int(available // destination.reference_price)
                    quantities = {affordable, max(0, affordable - 1)}
                    if objective == "MONTHLY_BALANCED":
                        quantities.add(0)
                    for added in sorted(quantities):
                        if explored >= max_expansions:
                            return BudgetPortfolioSearch(
                                retain((*frontier, *improved)), explored, True,
                            )
                        # Count every attempted exchange (including duplicate or
                        # rejected vectors); the public cap covers both phases.
                        explored += 1
                        shares = dict(start.shares)
                        shares[source_code] -= removed
                        shares[destination.etf_code] = shares.get(destination.etf_code, 0) + added
                        signature = tuple(sorted((code, q) for code, q in shares.items() if q > 0))
                        if signature in seen or len(signature) > max_added_etfs:
                            continue
                        seen.add(signature)
                        exact = sum((by_code[c].reference_price * q for c, q in signature), _ZERO)
                        displayed = sum((
                            (by_code[c].reference_price * q).quantize(
                                Decimal('.01'), rounding=ROUND_HALF_UP,
                            ) for c, q in signature
                        ), _ZERO)
                        if exact > budget or displayed > budget:
                            continue
                        added_cash = tuple((m, sum((
                            by_code[c].monthly_cash_per_share[m - 1] * q for c, q in signature
                        ), _ZERO)) for m in months)
                        plan = BudgetPortfolioPlan(
                            signature, exact, added_cash,
                            tuple((m, current.get(m, _ZERO) + cash) for m, cash in added_cash),
                        )
                        if objective == "MONTHLY_BALANCED" and plan.minimum_month_cash < minimum_cash_floor:
                            continue
                        if order(plan) < order(incumbent) and not any(
                            _budget_dominates(old, plan) and (
                                objective != "MONTHLY_BALANCED" or old.month_imbalance <= plan.month_imbalance
                            ) for old in frontier
                        ):
                            improved.append(plan)
                            incumbent = plan
        if not improved:
            break
        frontier = retain((*frontier, *improved))
        incumbent = frontier[0]
        if order(incumbent) >= order(start):
            break
    return BudgetPortfolioSearch(frontier, explored, truncated or explored >= max_expansions)
