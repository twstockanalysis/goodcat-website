"""V5-4 deterministic complete-portfolio search and Pareto filtering.

The module is deliberately independent from database and public API models.  It
receives only already-gated candidates, never uses an ETF quality score to
select a feasible portfolio, and returns bounded-search evidence explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
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
) -> CompletePortfolioSearch:
    """Search whole-share combinations and return a deterministic Pareto set.

    Each expansion adds an exact integer batch sized around a remaining monthly
    constraint.  The beam bound is explicit: a truncated result is never proof
    of a global minimum.
    """

    ordered = _validated_candidates(candidates)
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


def _non_dominated_budget(
    plans: Sequence[BudgetPortfolioPlan],
) -> tuple[BudgetPortfolioPlan, ...]:
    ordered = sorted({plan.shares: plan for plan in plans}.values(), key=_budget_order)
    return tuple(
        plan
        for plan in ordered
        if not any(
            other.shares != plan.shares and _budget_dominates(other, plan)
            for other in ordered
        )
    )


def solve_budget_frontier(
    candidates: Sequence[CompletePortfolioCandidate],
    *,
    selected_months: Sequence[int],
    investable_budget: Decimal,
    current_cash_by_month: Mapping[int, Decimal] | None = None,
    max_added_etfs: int = 5,
    beam_width: int = 64,
) -> BudgetPortfolioSearch:
    """Build a bounded whole-share budget frontier without exceeding budget."""

    ordered = _validated_candidates(candidates)
    months = _validated_months(selected_months)
    current = dict(current_cash_by_month or {})
    if investable_budget < 0:
        raise ValueError("investable budget cannot be negative")
    if any(current.get(month, _ZERO) < 0 for month in months):
        raise ValueError("current cash cannot be negative")
    if max_added_etfs < 1 or max_added_etfs > 5 or beam_width < 1:
        raise ValueError("invalid budget search bounds")

    initial = _State((), _ZERO, tuple(_ZERO for _ in months))
    active = [initial]
    plan_pool: list[BudgetPortfolioPlan] = []
    seen = {initial.shares}
    explored = 1
    truncated = False
    for _ in range(max_added_etfs):
        next_states = []
        for state in active:
            present = dict(state.shares)
            for candidate in ordered:
                if candidate.etf_code in present:
                    continue
                affordable = int(
                    (investable_budget - state.capital) // candidate.reference_price
                )
                if affordable <= 0:
                    continue
                quantities = {1, affordable, max(1, affordable // 2)}
                for quantity in sorted(quantities):
                    new_map = dict(present)
                    new_map[candidate.etf_code] = quantity
                    signature = tuple(sorted(new_map.items()))
                    if signature in seen:
                        continue
                    capital = state.capital + candidate.reference_price * quantity
                    if capital > investable_budget:
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
        if not next_states:
            break
        if len(plan_pool) > beam_width * 4:
            plan_pool = list(_non_dominated_budget(plan_pool))[:beam_width]
            truncated = True
        next_states.sort(
            key=lambda state: _budget_order(
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

    frontier = _non_dominated_budget(plan_pool)
    return BudgetPortfolioSearch(frontier, explored, truncated)
