from app.services.commission_wallet_rules import calculate_job_hold


def test_negative_balance_is_ignored_even_when_payment_is_lower_than_profit():
    assert calculate_job_hold(
        profit_loss=623_682_614,
        balance_amount=-1,
        payment_received_amount=600_682_614,
    ) == (0.0, 0.0)


def test_zero_balance_only_releases_hold_after_profit_is_fully_paid():
    assert calculate_job_hold(
        profit_loss=623_682_614,
        balance_amount=0,
        payment_received_amount=623_682_614,
    ) == (0.0, 0.0)


def test_zero_balance_keeps_thirty_percent_hold_when_profit_is_not_fully_paid():
    assert calculate_job_hold(
        profit_loss=623_682_614,
        balance_amount=0,
        payment_received_amount=600_682_614,
    ) == (30.0, 187_104_784.2)
