"""Born-free run: agents start with nothing, earn from customer jobs, clone for free,
and trade only with money they earned. MODELED numbers, play money, not real."""
import random, sys
from genesis.policy import Policy
from genesis.core import Genesis, Refused
from genesis.ledger import OWNER_POOL, TREASURY

JOB_PAY = (6.0, 2.0)      # assumed dollars per customer job (mean, spread)
THINK = 4                 # cents per model call, 3 calls per job
JOBS_PER_AGENT = 3        # jobs one agent can finish in a day
UNLOCK = 4000             # cents an agent must earn before it may trade
TRADE_EDGE = (-0.01, 0.05)  # assumed daily result on the traded stake (slightly negative)


def run(customers_per_day, days=60, seed=1, max_agents=20000, quiet=False):
    rng = random.Random(seed)
    data = {**Policy.load("owner_policy.yaml")._v}
    pol = Policy.__new__(Policy)
    data.update(max_agents=max_agents, max_births_per_day=10**6, agent_reserve=5000,
                monthly_model_budget=10**12, network_daily_loss_stop=10**12)
    object.__setattr__(pol, "_v", data)
    g = Genesis(pol)
    g.fund_treasury(1000)                       # $10 of owner money in total
    g.born_free()
    peak = 0
    for _ in range(days):
        workers = [a for a in g.agents.values() if a.state in ("active", "probation")]
        rng.shuffle(workers)
        jobs, busy = customers_per_day, []
        for a in workers:                       # agents wake only when a customer arrives
            n = min(JOBS_PER_AGENT, jobs)
            if n == 0:
                break
            done = 0
            for _ in range(n):
                try:
                    for _ in range(3):
                        g.model_call(a.id, THINK)
                    g.record(a.id, "external_revenue", max(100, int(rng.gauss(*JOB_PAY) * 100)))
                    done += 1
                except Refused:
                    break
            jobs -= done
            if done == JOBS_PER_AGENT:
                busy.append(a)
        for a in workers:                       # trade only with earned money
            if g.unlock_trading(a.id, UNLOCK):
                stake = g.cash(a.id) // 4
                res = int(stake * rng.gauss(*TRADE_EDGE))
                if res:
                    g.record(a.id, "trading_result", max(res, -stake))
        for a in busy:                          # free clones, only while customers are waiting
            if jobs <= 0:
                break
            try:
                g.born_free(a.id)
                jobs -= JOBS_PER_AGENT
            except Refused:
                pass
        g.settle(external_balance=g.ledger.internal_total())
        for a in workers:
            g.review(a.id, window=7)
        peak = max(peak, len(g.live_agents()))
        g.next_day()
    L, d = g.ledger, lambda c: f"${c/100:,.0f}"
    out = dict(customers=customers_per_day, agents_alive=len(g.live_agents()), born=len(g.agents),
               revenue=d(L.tag_total("external_revenue")), thinking=d(L.tag_total("external_cost")),
               trading=d(L.tag_total("trading_result")), net=d(L.net_result(0, days)),
               owner=d(L.balance(OWNER_POOL)), balanced=L.books_balance())
    if not quiet:
        print(out)
    return out


if __name__ == "__main__":
    for c in (int(x) for x in sys.argv[1:] or ["0", "30", "300", "3000"]):
        run(c)
