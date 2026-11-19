"""90-day play-money run of the Genesis core. Results here are MODELED, not real:
agent earnings come from a random model, not from real markets or customers."""
import random, sys
from genesis.policy import Policy
from genesis.core import Genesis, Refused
from genesis.ledger import OWNER_POOL, TREASURY

# (mean daily result, spread) in dollars per agent - assumptions for the model only.
# Trading is set slightly negative because it lost money in every earlier simulation.
MODEL = {"trend": (-0.6, 9), "dip": (-0.8, 8), "breakout": (-0.9, 11),
         "client_work": (3.0, 6), "product": (0.4, 4)}
KIND = {"trend": "trading", "dip": "trading", "breakout": "trading",
        "client_work": "business", "product": "product"}


def run(days=90, seed=1, start_capital=2000):
    rng = random.Random(seed)
    g = Genesis(Policy.load("owner_policy.yaml"))
    g.fund_treasury(start_capital * 100)
    for s in MODEL:
        g.seed(KIND[s], s)
    refused = {}
    for _ in range(days):
        for a in list(g.agents.values()):
            if a.state not in ("paper", "active", "probation"):
                continue
            mean, spread = MODEL[a.strategy]
            amt = int(rng.gauss(mean, spread) * 100)
            amt = max(amt, -g.cash(a.id))
            try:
                if a.state != "probation" or rng.random() < 0.5:
                    g.model_call(a.id, 4)
                if amt:
                    tag = "trading_result" if a.kind == "trading" else \
                        ("external_revenue" if amt > 0 else "external_cost")
                    g.record(a.id, tag, amt)
            except Refused as e:
                refused[e.reasons[0]] = refused.get(e.reasons[0], 0) + 1
            if g.killed:
                break
        if g.killed:
            g.resume()          # in this model the owner resumes the next morning
            for a in g.agents.values():
                if a.state == "suspended":
                    g._set_state(a, "active")
        g.settle(external_balance=g.ledger.internal_total())
        for a in list(g.agents.values()):
            if a.state in ("paper", "active", "probation"):
                state = g.review(a.id)
                if state == "active":
                    try:
                        g.replicate(a.id)
                    except Refused as e:
                        for r in e.reasons:
                            refused[r] = refused.get(r, 0) + 1
                    g.contribute_up(a.id)
        g.next_day()
    assert g.ledger.books_balance()
    L = g.ledger
    d = lambda c: f"${c/100:,.2f}"
    states = {}
    for a in g.agents.values():
        states[a.state] = states.get(a.state, 0) + 1
    by_kind = {}
    for a in g.agents.values():
        by_kind[a.kind] = by_kind.get(a.kind, 0) + L.net_result(0, days, a.id)
    print(f"Days run: {days}   Books balance: {L.books_balance()}")
    print(f"Agents ever created: {len(g.agents)}   By state: {states}")
    print(f"Revenue: {d(L.tag_total('external_revenue'))}  Costs: {d(L.tag_total('external_cost'))}"
          f"  Trading: {d(L.tag_total('trading_result'))}")
    print("Net by agent type:", {k: d(v) for k, v in by_kind.items()})
    print(f"Network net: {d(L.net_result(0, days))}")
    print(f"Owner pool (85%): {d(L.balance(OWNER_POOL))}   Treasury: {d(L.balance(TREASURY))}"
          f"   Not yet distributed/carry: {d(g.carry)}")
    print(f"Money in Genesis: {d(L.internal_total())} (started with {d(start_capital*100)})")
    print("Top refusals:", sorted(refused.items(), key=lambda x: -x[1])[:4])
    return g


if __name__ == "__main__":
    run(seed=int(sys.argv[1]) if len(sys.argv) > 1 else 1)
