from __future__ import annotations


PROFIT_SALE_RATE = 0.95
HOLD_BONUS_RATE = 0.30


def calculate_job_hold(
    *,
    profit_loss: float,
    balance_amount: float | None,
    payment_received_amount: float | None = None,
) -> tuple[float, float]:
    """Return the JOB hold percent and amount from receivable evidence.

    A missing Balance keeps the default 30% policy. Negative Balance rows are
    ignored. Balance = 0 removes the hold only when the amount actually paid
    covers Profit/Loss; this prevents an inconsistent AGEING Balance from
    marking a partially-paid JOB as fully settled.
    """
    if balance_amount is not None and float(balance_amount) < 0:
        return 0.0, 0.0
    if balance_amount is not None:
        paid_amount = max(0.0, float(payment_received_amount or 0.0))
        effective_outstanding = max(
            float(balance_amount),
            max(0.0, float(profit_loss or 0.0) - paid_amount),
        )
        if effective_outstanding <= 0:
            return 0.0, 0.0
    amount = round(max(0.0, float(profit_loss or 0.0)) * HOLD_BONUS_RATE, 2)
    return (30.0 if amount > 0 else 0.0), amount


def calculate_company_bonus_wallet(
    *,
    total_profit_loss: float,
    total_bonus_quarter: float,
    monthly_bonus: float,
    policy_hold_amount: float,
) -> dict[str, float | bool]:
    """Apply the company rule that separates Profit hold from bonus money.

    ``policy_hold_amount`` is the sum of 30% positive Profit/Loss on JOBs.  If
    that amount consumes the monthly commission, the company keeps the whole
    95%-Profit Sale amount and the complete quarterly bonus moves into the
    temporary bonus wallet.  Otherwise only the withheld part of each monthly
    commission moves into that wallet.
    """
    profit_sale = round(max(0.0, float(total_profit_loss or 0.0)) * PROFIT_SALE_RATE, 2)
    quarter_bonus = round(max(0.0, float(total_bonus_quarter or 0.0)), 2)
    monthly_base = round(max(0.0, float(monthly_bonus or 0.0)), 2)
    policy_hold = round(max(0.0, float(policy_hold_amount or 0.0)), 2)

    holds_entire_profit = monthly_base > 0 and policy_hold >= monthly_base - 0.005
    company_held_profit = profit_sale if holds_entire_profit else min(policy_hold, profit_sale)
    monthly_payout = max(0.0, round(monthly_base - company_held_profit, 2))

    if holds_entire_profit:
        temporary_bonus_available = quarter_bonus
    else:
        paid_for_three_months = min(quarter_bonus, round(monthly_payout * 3, 2))
        temporary_bonus_available = max(0.0, round(quarter_bonus - paid_for_three_months, 2))

    return {
        "profit_sale": profit_sale,
        "policy_hold_amount": policy_hold,
        "holds_entire_profit": holds_entire_profit,
        "company_held_profit": round(company_held_profit, 2),
        "monthly_payout": monthly_payout,
        "temporary_bonus_available": temporary_bonus_available,
    }
