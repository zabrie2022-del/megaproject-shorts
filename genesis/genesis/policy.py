import yaml

REQUIRED = ["mode", "owner_share_percent", "max_agents", "max_births_per_day",
            "monthly_model_budget", "monthly_server_budget", "capital_per_agent",
            "agent_reserve", "max_leverage", "network_daily_loss_stop",
            "daily_payout_limit", "max_days_to_profit",
            "child_monthly_cost_estimate", "strategy_capacity"]
MONEY = ["monthly_model_budget", "monthly_server_budget", "capital_per_agent",
         "agent_reserve", "network_daily_loss_stop", "daily_payout_limit",
         "child_monthly_cost_estimate"]


def cents(dollars):
    return int(round(float(dollars) * 100))


class Policy:
    """Read-only view of owner_policy.yaml. Money values are held in cents."""

    def __init__(self, data):
        missing = [k for k in REQUIRED if k not in data]
        if missing:
            raise ValueError(f"owner policy is missing: {missing}")
        if data["mode"] != "paper":
            raise ValueError("this build runs in paper mode only")
        if not 0 <= data["owner_share_percent"] <= 100:
            raise ValueError("owner_share_percent must be 0-100")
        values = dict(data)
        for k in MONEY:
            values[k] = cents(values[k])
        values["strategy_capacity"] = {k: cents(v) for k, v in data["strategy_capacity"].items()}
        object.__setattr__(self, "_v", values)

    def __getattr__(self, name):
        try:
            return self._v[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        raise PermissionError("policy is read-only; edit owner_policy.yaml as the owner")

    @classmethod
    def load(cls, path="owner_policy.yaml"):
        with open(path) as f:
            return cls(yaml.safe_load(f))
