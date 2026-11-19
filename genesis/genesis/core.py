from dataclasses import dataclass, field
from .ledger import Ledger, LedgerError, WORLD, OWNER_POOL, TREASURY, agent_account

STATES = ("proposed", "paper", "active", "probation", "suspended", "shut_down")


@dataclass
class Agent:
    id: int
    parent: int | None
    generation: int
    kind: str          # trading, business or product
    strategy: str
    params: dict
    state: str
    born_day: int
    first_profit_day: int | None = None
    history: list = field(default_factory=list)


class Refused(Exception):
    def __init__(self, reasons):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


class Genesis:
    """Runs the agent network inside the owner's policy. Paper mode only."""

    def __init__(self, policy, ledger=None):
        self.policy = policy
        self.ledger = ledger or Ledger()
        self.agents = {}
        self.audit = []            # append-only audit log
        self.killed = False
        self.day = 0
        self.births = {}           # day -> count
        self.carry = 0             # <0 losses carried forward, >0 profit not yet distributed
        self.settled_days = set()
        self.proven = set()        # strategies that were profitable while active
        self.model_spend = {}      # month -> cents
        self._next_id = 1

    # ---- audit and kill switch -------------------------------------------------
    def log(self, event, **data):
        self.audit.append({"day": self.day, "event": event, **data})

    def kill(self, reason="owner"):
        self.killed = True
        for a in self.agents.values():
            if a.state in ("paper", "active", "probation"):
                self._set_state(a, "suspended")
        self.log("kill_switch", reason=reason)

    def resume(self):
        self.killed = False
        self.log("resume")

    def _live(self):
        if self.killed:
            raise Refused(["kill switch is on"])

    def _set_state(self, agent, state):
        assert state in STATES
        agent.history.append((self.day, agent.state, state))
        agent.state = state
        self.log("state", agent=agent.id, state=state)

    # ---- money -----------------------------------------------------------------
    def cash(self, agent_id):
        return self.ledger.balance(agent_account(agent_id))

    def free_cash(self, agent_id):
        return max(0, self.cash(agent_id) - self.policy.agent_reserve)

    def fund_treasury(self, amount):
        """Owner puts starting capital into Genesis. Not profit."""
        self.ledger.transfer(self.day, "capital", WORLD, TREASURY, amount, memo="owner capital")
        self.log("capital", amount=amount)

    def record(self, agent_id, tag, amount, memo=""):
        """Book a realized result for an agent: revenue (+), cost (-), trading (+/-)."""
        self._live()
        a = self.agents[agent_id]
        if a.state not in ("active", "probation", "paper"):
            raise Refused([f"agent {agent_id} is {a.state}"])
        if tag not in ("external_revenue", "external_cost", "trading_result"):
            raise LedgerError("agents can only book revenue, cost or trading results")
        if tag == "external_revenue" and amount <= 0 or tag == "external_cost" and amount >= 0:
            raise LedgerError("wrong sign for tag")
        if tag == "trading_result" and a.params.get("born_free") and not a.params.get("can_trade"):
            raise Refused([f"agent {agent_id} must earn its trading money first"])
        if amount < 0 and -amount > self.cash(agent_id):
            raise Refused([f"agent {agent_id} cannot spend past its budget"])
        if tag == "trading_result" and amount < 0 and \
                self._today_loss() - amount > self.policy.network_daily_loss_stop:
            self.kill("network daily loss stop")
            raise Refused(["network daily loss stop reached"])
        acct = agent_account(agent_id)
        self.ledger.post(self.day, tag, [(WORLD, -amount), (acct, amount)], agent_id, memo)
        self.log(tag, agent=agent_id, amount=amount)

    def _today_loss(self):
        return -min(0, self.ledger.tag_total("trading_result", self.day, self.day))

    def model_call(self, agent_id, cost):
        """Model gateway: enforces the monthly budget, then charges the agent."""
        month = self.day // 30
        if self.model_spend.get(month, 0) + cost > self.policy.monthly_model_budget:
            raise Refused(["monthly model budget reached"])
        self.record(agent_id, "external_cost", -cost, "model call")
        self.model_spend[month] = self.model_spend.get(month, 0) + cost

    def contribute_up(self, agent_id):
        """Cash above reserve and budget moves up to the parent (or treasury).
        An internal transfer: it never counts as profit."""
        a = self.agents[agent_id]
        surplus = self.cash(agent_id) - self.policy.agent_reserve - self.policy.capital_per_agent
        if surplus <= 0:
            return 0
        dst = agent_account(a.parent) if a.parent in self.agents and \
            self.agents[a.parent].state != "shut_down" else TREASURY
        self.ledger.transfer(self.day, "internal_transfer", agent_account(agent_id), dst,
                             surplus, agent_id, "contribution")
        self.log("contribution", agent=agent_id, amount=surplus)
        return surplus

    # ---- agents and replication ------------------------------------------------
    def live_agents(self):
        return [a for a in self.agents.values() if a.state not in ("shut_down", "proposed")]

    def _new_agent(self, parent, kind, strategy, params, state):
        a = Agent(self._next_id, parent, 0 if parent is None else self.agents[parent].generation + 1,
                  kind, strategy, dict(params), "proposed", self.day)
        self._next_id += 1
        self.agents[a.id] = a
        self._set_state(a, state)
        self.births[self.day] = self.births.get(self.day, 0) + 1
        return a

    def _capacity_used(self, strategy):
        return sum(self.cash(a.id) for a in self.live_agents()
                   if a.strategy == strategy and a.state != "paper")

    def _network_checks(self, strategy, budget):
        p, reasons = self.policy, []
        if self.killed:
            reasons.append("kill switch is on: replication frozen")
        if len(self.live_agents()) >= p.max_agents:
            reasons.append("rule 3: agent cap reached")
        if self.births.get(self.day, 0) >= p.max_births_per_day:
            reasons.append("rule 3: today's birth cap reached")
        cap = p.strategy_capacity.get(strategy)
        if cap is None:
            reasons.append("rule 4: strategy is not in the tested library")
        elif self._capacity_used(strategy) + budget > cap:
            reasons.append("rule 4: strategy has no spare capacity")
        month = self.day // 30
        if self.model_spend.get(month, 0) + p.child_monthly_cost_estimate > p.monthly_model_budget:
            reasons.append("rule 5: child's costs do not fit this month's budget")
        return reasons

    def seed(self, kind, strategy, params=None):
        """Genesis creates a first-generation agent from the treasury."""
        budget = self.policy.capital_per_agent
        reasons = self._network_checks(strategy, budget)
        if self.ledger.balance(TREASURY) < budget:
            reasons.append("treasury cannot fund the agent")
        if reasons:
            self.log("seed_refused", reasons=reasons)
            raise Refused(reasons)
        a = self._new_agent(None, kind, strategy, params or {}, "active")
        self.ledger.transfer(self.day, "internal_transfer", TREASURY, agent_account(a.id),
                             budget, a.id, "starting budget")
        return a

    def replicate(self, parent_id, params=None):
        """A parent asks for a child. All six rules must pass."""
        p, parent = self.policy, self.agents[parent_id]
        budget = p.capital_per_agent
        reasons = []
        if parent.state != "active":
            reasons.append("parent is not active")
        if self.ledger.net_result(self.day - 29, self.day, parent_id) <= 0:
            reasons.append("rule 1: parent has no net profit over 30 days")
        if self.cash(parent_id) < budget + 2 * p.agent_reserve:
            reasons.append("rule 2: parent cannot fund the child and both reserves")
        reasons += self._network_checks(parent.strategy, budget)
        sib = [s for s in self.agents.values() if s.parent == parent_id]
        times = sorted(s.first_profit_day - s.born_day for s in sib if s.first_profit_day is not None)
        failed = [s for s in sib if s.state == "shut_down" and s.first_profit_day is None]
        if sib and (len(failed) > len(times) or (times and times[len(times) // 2] > p.max_days_to_profit)):
            reasons.append("rule 6: siblings' history does not show profit in time")
        if reasons:
            self.log("replication_refused", parent=parent_id, reasons=reasons)
            raise Refused(reasons)
        state = "active" if parent.strategy in self.proven else "paper"
        child_params = self._vary(parent.params, params)
        child = self._new_agent(parent_id, parent.kind, parent.strategy, child_params, state)
        self.ledger.transfer(self.day, "internal_transfer", agent_account(parent_id),
                             agent_account(child.id), budget, child.id, "child budget")
        return child

    # ---- born-free agents: start with nothing, earn first, trade later ----------
    def born_free(self, parent_id=None, strategy="client_work", allowance=100):
        """A clone that gets no budget. It receives only a tiny allowance to pay for
        its first thoughts (from its parent, or the treasury for the first one),
        must earn from service work, and may trade only after unlock_trading()."""
        reasons = []
        if self.killed:
            reasons.append("kill switch is on: replication frozen")
        if len(self.live_agents()) >= self.policy.max_agents:
            reasons.append("rule 3: agent cap reached")
        if self.births.get(self.day, 0) >= self.policy.max_births_per_day:
            reasons.append("rule 3: today's birth cap reached")
        if strategy not in self.policy.strategy_capacity:
            reasons.append("rule 4: strategy is not in the tested library")
        if parent_id is None:
            src = TREASURY
        else:
            src = agent_account(parent_id)
            if self.agents[parent_id].state != "active":
                reasons.append("parent is not active")
            if self.ledger.net_result(self.day - 29, self.day, parent_id) <= 0:
                reasons.append("rule 1: parent has no net profit over 30 days")
        if self.ledger.balance(src) < 2 * allowance:
            reasons.append("rule 2: nobody can pay for the clone's first thoughts")
        if reasons:
            self.log("replication_refused", parent=parent_id, reasons=reasons)
            raise Refused(reasons)
        a = self._new_agent(parent_id, "business", strategy, {"born_free": 1}, "active")
        self.ledger.transfer(self.day, "internal_transfer", src, agent_account(a.id),
                             allowance, a.id, "first thoughts")
        return a

    def unlock_trading(self, agent_id, threshold):
        """An agent may start trading once it has EARNED at least `threshold`."""
        a = self.agents[agent_id]
        if self.ledger.net_result(0, self.day, agent_id) >= threshold and self.cash(agent_id) >= threshold:
            a.params["can_trade"] = 1
            self.log("trading_unlocked", agent=agent_id)
        return bool(a.params.get("can_trade"))

    @staticmethod
    def _vary(parent_params, requested, bound=0.2):
        """Children vary only numeric parameters, within +/-20% of the parent's."""
        out = dict(parent_params)
        for k, v in (requested or {}).items():
            if k not in parent_params:
                raise Refused([f"children cannot add parameter {k}"])
            base = parent_params[k]
            lo, hi = sorted((base * (1 - bound), base * (1 + bound)))
            out[k] = min(max(v, lo), hi)
        return out

    def review(self, agent_id, window=30):
        """Move an agent through its lifecycle from its results."""
        a = self.agents[agent_id]
        net = self.ledger.net_result(self.day - window + 1, self.day, agent_id)
        if net > 0 and a.first_profit_day is None:
            a.first_profit_day = self.day
        if a.state == "paper":
            if self.day - a.born_day >= window:
                self._set_state(a, "active") if net > 0 else self.shut_down(agent_id)
        elif a.state == "active":
            if net > 0:
                self.proven.add(a.strategy)
            elif net < 0:
                self._set_state(a, "probation")
        elif a.state == "probation":
            if self.cash(agent_id) <= self.policy.agent_reserve // 2:
                self.shut_down(agent_id)
            elif net > 0:
                self._set_state(a, "active")
        return a.state

    def shut_down(self, agent_id):
        a = self.agents[agent_id]
        left = self.cash(agent_id)
        if left > 0:
            dst = agent_account(a.parent) if a.parent in self.agents and \
                self.agents[a.parent].state != "shut_down" else TREASURY
            self.ledger.transfer(self.day, "internal_transfer", agent_account(agent_id), dst,
                                 left, agent_id, "returned on shutdown")
        self._set_state(a, "shut_down")

    # ---- settlement ------------------------------------------------------------
    def settle(self, external_balance=None):
        """Daily settlement. The owner's share is computed ONCE, on the whole
        network's realized net, after losses carried forward and reserves."""
        day = self.day
        if day in self.settled_days:
            raise Refused(["this day is already settled"])
        if not self.ledger.books_balance():
            raise Refused(["ledger does not balance"])
        if external_balance is not None and external_balance != self.ledger.internal_total():
            self.log("reconciliation_mismatch", ledger=self.ledger.internal_total(),
                     external=external_balance)
            raise Refused(["reconciliation mismatch: settlement blocked, owner alerted"])
        net = self.ledger.net_result(day, day)
        self.carry += net
        self.settled_days.add(day)
        paid_owner = paid_treasury = 0
        if self.carry > 0:
            free = {a.id: self.free_cash(a.id) for a in self.live_agents() if a.state != "paper"}
            total_free = sum(free.values())
            pay = min(self.carry, total_free)
            if pay > 0:
                paid_owner = pay * self.policy.owner_share_percent // 100
                paid_treasury = pay - paid_owner
                lines, left = [], pay
                ids = [i for i in free if free[i] > 0]
                for n, i in enumerate(ids):
                    part = left if n == len(ids) - 1 else pay * free[i] // total_free
                    part = min(part, free[i], left)
                    left -= part
                    if part:
                        lines.append((agent_account(i), -part))
                pay -= left
                paid_owner = pay * self.policy.owner_share_percent // 100
                paid_treasury = pay - paid_owner
                lines += [(OWNER_POOL, paid_owner), (TREASURY, paid_treasury)]
                self.ledger.post(day, "settlement", lines, memo="daily settlement")
                self.carry -= pay
        self.log("settlement", net=net, owner=paid_owner, treasury=paid_treasury, carry=self.carry)
        return {"net": net, "owner": paid_owner, "treasury": paid_treasury, "carry": self.carry}

    def payout(self, amount, owner_confirmed=False):
        """Paper payout from the owner pool. Needs the owner's confirmation."""
        if not owner_confirmed:
            raise Refused(["payout needs the owner's confirmation"])
        paid_today = -self.ledger.tag_total("payout", self.day, self.day)
        if paid_today + amount > self.policy.daily_payout_limit:
            raise Refused(["daily payout limit reached"])
        self.ledger.transfer(self.day, "payout", OWNER_POOL, WORLD, amount, memo="owner payout",
                             allow_owner_pool_debit=True)
        self.log("payout", amount=amount)

    def next_day(self):
        self.day += 1
