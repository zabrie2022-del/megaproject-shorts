"""Gate 1: the books balance and the owner's 85% is settled once, on the net."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from genesis.policy import Policy
from genesis.core import Genesis, Refused
from genesis.ledger import Ledger, LedgerError, OWNER_POOL, TREASURY, WORLD, agent_account

BASE = dict(mode="paper", owner_share_percent=85, max_agents=100, max_births_per_day=5,
            monthly_model_budget=300, monthly_server_budget=100, capital_per_agent=200,
            agent_reserve=20, max_leverage=1, network_daily_loss_stop=500,
            daily_payout_limit=1000, max_days_to_profit=30, child_monthly_cost_estimate=3,
            strategy_capacity=dict(trend=5000, dip=3000, client_work=8000, product=4000))


def make(**over):
    g = Genesis(Policy({**BASE, **over}))
    g.fund_treasury(10_000_00)
    return g


def test_policy_is_read_only_and_paper_only():
    p = Policy(BASE)
    with pytest.raises(PermissionError):
        p.max_agents = 10**6
    with pytest.raises(ValueError):
        Policy({**BASE, "mode": "live"})


def test_every_transaction_balances_and_ledger_is_append_only():
    led = Ledger()
    with pytest.raises(LedgerError):
        led.post(0, "capital", [(WORLD, -100), (TREASURY, 90)])
    led.transfer(0, "capital", WORLD, TREASURY, 100)
    assert led.books_balance()
    with pytest.raises(Exception):
        led.db.execute("UPDATE line SET amount=999")
    with pytest.raises(Exception):
        led.db.execute("DELETE FROM tx")


def test_worked_example_100k_network_pays_85k_once():
    g = make(capital_per_agent=20_000, network_daily_loss_stop=10**6, agent_reserve=0,
             strategy_capacity=dict(trend=10**7, client_work=10**7, product=10**7))
    g.ledger.transfer(0, "capital", WORLD, TREASURY, 100_000_00)
    biz = g.seed("business", "client_work"); trd = g.seed("trading", "trend")
    gen = g.seed("business", "client_work"); prod = g.seed("product", "product")
    before = g.ledger.internal_total()
    g.record(biz.id, "external_revenue", 50_000_00)
    g.record(trd.id, "trading_result", 45_000_00)
    g.record(gen.id, "external_revenue", 20_000_00)
    g.record(prod.id, "trading_result", -5_000_00)
    g.record(gen.id, "external_cost", -10_000_00)
    r = g.settle(external_balance=g.ledger.internal_total())
    assert r["net"] == 100_000_00
    assert r["owner"] == 85_000_00 and r["treasury"] == 15_000_00   # not 97,750
    assert g.ledger.balance(OWNER_POOL) == 85_000_00
    assert g.ledger.internal_total() == before + 100_000_00
    assert g.ledger.books_balance()
    with pytest.raises(Refused):
        g.settle()                       # the same day can never be settled twice


def test_winner_and_loser_net_to_zero_pays_nothing():
    g = make()
    a, b = g.seed("trading", "trend"), g.seed("trading", "dip")
    g.record(a.id, "trading_result", 100_00)
    g.record(b.id, "trading_result", -100_00)
    assert g.settle()["owner"] == 0
    assert g.ledger.balance(OWNER_POOL) == 0


def test_losses_are_carried_forward_before_any_payout():
    g = make()
    a = g.seed("trading", "trend")
    g.record(a.id, "trading_result", -60_00)
    assert g.settle() == {"net": -60_00, "owner": 0, "treasury": 0, "carry": -60_00}
    g.next_day()
    g.record(a.id, "trading_result", 100_00)
    r = g.settle()
    assert r["owner"] == 34_00 and r["treasury"] == 6_00 and r["carry"] == 0


def test_internal_transfers_and_capital_are_never_profit():
    g = make()
    a = g.seed("business", "client_work")
    g.ledger.transfer(0, "internal_transfer", TREASURY, agent_account(a.id), 500_00)
    g.contribute_up(a.id)
    assert g.settle()["net"] == 0 and g.ledger.balance(OWNER_POOL) == 0


def test_reserves_are_kept_at_settlement():
    g = make(capital_per_agent=10, agent_reserve=20)
    a = g.seed("business", "client_work")
    g.record(a.id, "external_revenue", 15_00)       # cash 25, only 5 above reserve
    r = g.settle()
    assert r["owner"] + r["treasury"] == 5_00 and r["carry"] == 10_00
    assert g.cash(a.id) == 20_00


def test_reconciliation_mismatch_blocks_settlement():
    g = make()
    g.seed("trading", "trend")
    with pytest.raises(Refused):
        g.settle(external_balance=g.ledger.internal_total() - 1)
    assert any(e["event"] == "reconciliation_mismatch" for e in g.audit)


def test_owner_pool_only_leaves_by_confirmed_payout_within_limit():
    g = make()
    a = g.seed("business", "client_work")
    g.record(a.id, "external_revenue", 3000_00)
    g.settle()
    with pytest.raises(LedgerError):
        g.ledger.transfer(0, "internal_transfer", OWNER_POOL, agent_account(a.id), 1)
    with pytest.raises(Refused):
        g.payout(100_00)
    g.payout(1000_00, owner_confirmed=True)
    with pytest.raises(Refused):
        g.payout(1, owner_confirmed=True)            # daily limit
    assert g.ledger.balance(OWNER_POOL) == 2550_00 - 1000_00


def test_agents_cannot_spend_past_budget_or_borrow():
    g = make()
    a = g.seed("trading", "trend")
    with pytest.raises(Refused):
        g.record(a.id, "trading_result", -201_00)
    assert g.cash(a.id) == 200_00


def test_replication_needs_every_rule():
    g = make()
    a = g.seed("business", "client_work")
    with pytest.raises(Refused) as e:
        g.replicate(a.id)
    assert any("rule 1" in r for r in e.value.reasons)
    g.record(a.id, "external_revenue", 30_00)        # profit, but cash 230 < 200 + 2*20
    with pytest.raises(Refused) as e:
        g.replicate(a.id)
    assert [r[:6] for r in e.value.reasons] == ["rule 2"]
    g.record(a.id, "external_revenue", 100_00)
    child = g.replicate(a.id)
    assert child.state == "paper" and child.parent == a.id and child.generation == 1
    assert g.cash(child.id) == 200_00 and g.ledger.books_balance()
    assert g.settle()["net"] == 130_00               # the child's budget is not profit or loss


def test_caps_capacity_and_parameter_bounds():
    g = make(max_agents=2, strategy_capacity=dict(trend=300, client_work=8000))
    g.seed("trading", "trend")
    with pytest.raises(Refused) as e:
        g.seed("trading", "trend")
    assert any("rule 4" in r for r in e.value.reasons)
    g.seed("business", "client_work")
    with pytest.raises(Refused) as e:
        g.seed("business", "client_work")
    assert any("agent cap" in r for r in e.value.reasons)
    assert Genesis._vary({"stop": 10.0}, {"stop": 50.0}) == {"stop": 12.0}
    with pytest.raises(Refused):
        Genesis._vary({"stop": 10.0}, {"leverage": 100})


def test_birth_cap_per_day():
    g = make(max_births_per_day=2)
    g.seed("trading", "trend"); g.seed("trading", "dip")
    with pytest.raises(Refused):
        g.seed("business", "client_work")
    g.next_day()
    g.seed("business", "client_work")


def test_kill_switch_stops_agents_and_freezes_replication():
    g = make()
    a = g.seed("business", "client_work")
    g.kill()
    assert a.state == "suspended"
    with pytest.raises(Refused):
        g.record(a.id, "external_revenue", 10_00)
    with pytest.raises(Refused):
        g.seed("trading", "trend")


def test_daily_loss_stop_trips_the_kill_switch():
    g = make(network_daily_loss_stop=150)
    a, b = g.seed("trading", "trend"), g.seed("trading", "dip")
    g.record(a.id, "trading_result", -100_00)
    with pytest.raises(Refused):
        g.record(b.id, "trading_result", -100_00)
    assert g.killed


def test_model_budget_is_enforced():
    g = make(monthly_model_budget=1, child_monthly_cost_estimate=0.3)
    a = g.seed("business", "client_work")
    g.model_call(a.id, 60)
    with pytest.raises(Refused):
        g.model_call(a.id, 60)


def test_lifecycle_probation_and_shutdown_return_money():
    g = make()
    a = g.seed("trading", "trend")
    g.record(a.id, "trading_result", -150_00)
    assert g.review(a.id) == "probation"
    g.record(a.id, "trading_result", -45_00)
    t = g.ledger.balance(TREASURY)
    assert g.review(a.id) == "shut_down"
    assert g.cash(a.id) == 0 and g.ledger.balance(TREASURY) == t + 5_00
    assert g.ledger.books_balance()


def test_born_free_agents_earn_first_then_trade_and_starve_without_work():
    g = make()
    a = g.born_free()                                  # first one: $1 from the treasury
    assert g.cash(a.id) == 1_00
    with pytest.raises(Refused):
        g.record(a.id, "trading_result", 50)           # no trading before earning
    with pytest.raises(Refused):
        g.born_free(a.id)                              # no profit yet: cannot clone
    g.record(a.id, "external_revenue", 60_00)
    assert not g.unlock_trading(a.id, 100_00) and g.unlock_trading(a.id, 40_00)
    g.record(a.id, "trading_result", -5_00)
    child = g.born_free(a.id)                          # paid by the parent, not the treasury
    assert g.cash(child.id) == 1_00 and g.cash(a.id) == 55_00
    g.model_call(child.id, 60); g.model_call(child.id, 40)
    with pytest.raises(Refused):
        g.model_call(child.id, 1)                      # out of money: cannot even think
    assert g.review(child.id) == "probation" and g.review(child.id) == "shut_down"
    assert g.ledger.books_balance()
