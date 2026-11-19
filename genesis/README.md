# Genesis core (play money only)

Rebuilt on 19 November 2026 from the plan "Project Genesis: Architecture and Roadmap"
(https://claude.ai/artifact/XUHyo9sjqLBcARoDe1PYBo). Covers roadmap Stages 2 to 4 and Gate 1.

- `owner_policy.yaml`: the owner's limits. Only the owner edits it.
- `genesis/policy.py`: loads the policy, read-only, paper mode only.
- `genesis/ledger.py`: append-only double-entry ledger.
- `genesis/core.py`: agents, lifecycle, six replication rules, kill switch, daily 85/15 settlement, paper payout.
- `tests/test_gate1.py`: 17 tests. Run `python3 -m pytest -q tests`.
- `run_paper.py`: 90-day modeled run. Run `python3 run_paper.py 1`. Earnings are assumed numbers, not real.

Not built here: trading gateway, dashboard, store, wallets, anything with real money.
Next step: Stage 5 (trading agents on live prices, play money) or the business engine (store).

## Born-free agents (added 19 November 2026)
- `Genesis.born_free()`: a clone starts with no budget, only $1 for its first thoughts, paid by its parent.
- It earns from customer jobs first; `unlock_trading()` lets it trade only with money it earned.
- With no work it runs out, goes on probation and shuts down.
- `run_born_free.py`: modeled run. `python3 run_born_free.py 30 300` (customers per day). Assumed numbers, play money.
