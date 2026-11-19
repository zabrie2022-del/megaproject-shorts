import sqlite3

TAGS = {"capital", "external_revenue", "external_cost", "trading_result",
        "internal_transfer", "settlement", "payout"}
# Tags that count toward the network's realized net result.
RESULT_TAGS = ("external_revenue", "external_cost", "trading_result")
WORLD = "world"            # everything outside Genesis
OWNER_POOL = "owner_pool"  # the owner's settled share
TREASURY = "treasury"      # the ecosystem share, reserves, shared costs


def agent_account(agent_id):
    return f"agent:{agent_id}"


class LedgerError(Exception):
    pass


class Ledger:
    """Append-only double-entry ledger. Amounts are integer cents.
    Every transaction's lines sum to zero, so the books always balance."""

    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path)
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS tx(id INTEGER PRIMARY KEY, day INTEGER NOT NULL,
            tag TEXT NOT NULL, agent_id INTEGER, memo TEXT);
        CREATE TABLE IF NOT EXISTS line(tx_id INTEGER NOT NULL, account TEXT NOT NULL,
            amount INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS line_account ON line(account);
        CREATE TRIGGER IF NOT EXISTS tx_no_update BEFORE UPDATE ON tx
            BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
        CREATE TRIGGER IF NOT EXISTS tx_no_delete BEFORE DELETE ON tx
            BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
        CREATE TRIGGER IF NOT EXISTS line_no_update BEFORE UPDATE ON line
            BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
        CREATE TRIGGER IF NOT EXISTS line_no_delete BEFORE DELETE ON line
            BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
        """)

    def post(self, day, tag, lines, agent_id=None, memo="", allow_owner_pool_debit=False):
        if tag not in TAGS:
            raise LedgerError(f"unknown tag {tag}")
        if sum(a for _, a in lines) != 0:
            raise LedgerError("transaction does not balance")
        for account, amount in lines:
            if not isinstance(amount, int):
                raise LedgerError("amounts must be integer cents")
            if account == OWNER_POOL and amount < 0 and not allow_owner_pool_debit:
                raise LedgerError("only the payout service may take from the owner pool")
            if account != WORLD and amount < 0 and self.balance(account) + amount < 0:
                raise LedgerError(f"{account} cannot go below zero")
        with self.db:
            cur = self.db.execute("INSERT INTO tx(day, tag, agent_id, memo) VALUES (?,?,?,?)",
                                  (day, tag, agent_id, memo))
            self.db.executemany("INSERT INTO line VALUES (?,?,?)",
                                [(cur.lastrowid, a, amt) for a, amt in lines])
        return cur.lastrowid

    def transfer(self, day, tag, src, dst, amount, agent_id=None, memo="", **kw):
        if amount <= 0:
            raise LedgerError("transfer amount must be positive")
        return self.post(day, tag, [(src, -amount), (dst, amount)], agent_id, memo, **kw)

    def balance(self, account):
        return self.db.execute("SELECT COALESCE(SUM(amount),0) FROM line WHERE account=?",
                               (account,)).fetchone()[0]

    def internal_total(self):
        """All money Genesis holds: owner pool + treasury + every agent."""
        return self.db.execute("SELECT COALESCE(SUM(amount),0) FROM line WHERE account<>?",
                               (WORLD,)).fetchone()[0]

    def books_balance(self):
        return self.db.execute("SELECT COALESCE(SUM(amount),0) FROM line").fetchone()[0] == 0

    def net_result(self, day_from, day_to, agent_id=None):
        """Realized net result (revenue - costs +/- trading) for days in [from, to]."""
        q = ("SELECT COALESCE(SUM(l.amount),0) FROM line l JOIN tx t ON t.id=l.tx_id "
             "WHERE l.account<>? AND t.day BETWEEN ? AND ? AND t.tag IN (?,?,?)")
        args = [WORLD, day_from, day_to, *RESULT_TAGS]
        if agent_id is not None:
            q += " AND t.agent_id=?"
            args.append(agent_id)
        return self.db.execute(q, args).fetchone()[0]

    def tag_total(self, tag, day_from=0, day_to=10**9):
        return self.db.execute(
            "SELECT COALESCE(SUM(l.amount),0) FROM line l JOIN tx t ON t.id=l.tx_id "
            "WHERE l.account<>? AND t.tag=? AND t.day BETWEEN ? AND ?",
            (WORLD, tag, day_from, day_to)).fetchone()[0]
