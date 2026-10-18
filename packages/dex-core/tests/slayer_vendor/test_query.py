"""A governed `explore semantic query` over a SLayer layer (#680).

SLayer renders and dex executes. What this release promises: a saved measure
grouped by a column returns the numbers hand-written SQL does; the PII gate
screens every grouped column and every column a filter names, looked up in the
`.dex/` cache through the catalog's physical columns before anything renders;
a filter dex cannot read, a connector SLayer has no dialect for and a relation
the connection lacks are each refused by name; a SLayer resolution error comes
back redacted; and on a billed connector the query stops for confirmation
before any spend.

Needs the real `[slayer]` extra, so it skips without it; the `slayer-sqlglot` CI
job is where it runs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from exmergo_dex_core.slayer import dependency
from exmergo_dex_core.slayer.dependency import SLAYER_VERSION

if dependency.installed_version() != SLAYER_VERSION:
    pytest.skip(
        f"the [slayer] extra (SLayer {SLAYER_VERSION}) is not installed",
        allow_module_level=True,
    )

from exmergo_dex_core.cli import main
from exmergo_dex_core.engine import DexEngine
from exmergo_dex_core.explore.semantic import SemanticBackendError
from exmergo_dex_core.explore.semantic.backend import resolve_semantic_layer
from exmergo_dex_core.explore.semantic.model import SemanticQuery
from exmergo_dex_core.slayer import render
from exmergo_dex_core.slayer.loader import FORMAT_VERSION

duckdb = pytest.importorskip("duckdb")

BASE = "semantics/slayer"


def model(name: str, *, table: str | None = None, **fields: Any) -> dict[str, Any]:
    return {
        "version": FORMAT_VERSION,
        "name": name,
        "sql_table": table or f"shop.main.{name}",
        "data_source": "wh",
        **fields,
    }


ORDERS = model(
    "orders",
    default_time_dimension="ordered_at",
    filters=["status <> 'test'"],
    columns=[
        {"name": "order_id", "type": "INT", "primary_key": True},
        {"name": "customer_id", "type": "INT"},
        {"name": "status", "type": "TEXT"},
        {"name": "amount", "type": "DOUBLE"},
        {"name": "ordered_at", "type": "TIMESTAMP"},
        # Named nothing like PII, and backed by a column that is: only the
        # catalog's physical columns can tell the gate what it reads.
        {"name": "buyer", "type": "TEXT", "sql": "contact_email"},
    ],
    measures=[
        {"name": "revenue", "formula": "amount:sum"},
        {"name": "order_count", "formula": "*:count"},
    ],
    joins=[{"target_model": "customers", "join_pairs": [["customer_id", "id"]]}],
)
CUSTOMERS = model(
    "customers",
    columns=[
        {"name": "id", "type": "INT", "primary_key": True},
        {"name": "email", "type": "TEXT"},
        {"name": "tier", "type": "TEXT"},
    ],
    measures=[{"name": "customer_count", "formula": "*:count"}],
)

ROWS = [
    (1, 1, "paid", 10.0, "2026-01-03", "a@example.com"),
    (2, 1, "paid", 5.5, "2026-01-20", "a@example.com"),
    (3, 2, "open", 7.0, "2026-02-01", "b@example.com"),
    (4, 2, "paid", 2.5, "2026-02-14", "b@example.com"),
    (5, 3, "refunded", 4.0, "2026-03-09", "c@example.com"),
    # Excluded by the model's own filter, so a number that counts it is wrong.
    (6, 3, "test", 1000.0, "2026-03-10", "c@example.com"),
]


def _warehouse(root: Path) -> Path:
    path = root / "shop.duckdb"
    conn = duckdb.connect(str(path))
    conn.execute(
        "CREATE TABLE orders (order_id INT, customer_id INT, status VARCHAR, "
        "amount DOUBLE, ordered_at TIMESTAMP, contact_email VARCHAR)"
    )
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)", ROWS)
    conn.execute("CREATE TABLE customers (id INT, email VARCHAR, tier VARCHAR)")
    conn.executemany(
        "INSERT INTO customers VALUES (?, ?, ?)",
        [(1, "a@example.com", "gold"), (2, "b@example.com", "free")],
    )
    conn.close()
    return path


def _repo(root: Path, *models: dict[str, Any], connector: str = "duckdb") -> Path:
    names: list[str] = []
    for entry in models:
        name = f"models/wh/{entry['name']}.yaml"
        path = root / BASE / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(entry, sort_keys=False), encoding="utf-8")
        names.append(name)
    warehouse = _warehouse(root)
    (root / ".dex").mkdir(exist_ok=True)
    (root / ".dex" / "config.yml").write_text(
        f"connector: {connector}\nduckdb:\n  path: {warehouse}\n"
        f"semantic:\n  vendor: slayer\n  slayer:\n    base_dir: {BASE}\n"
        "    models:\n" + "".join(f"      - {name}\n" for name in names),
        encoding="utf-8",
    )
    return root


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return _repo(tmp_path, ORDERS, CUSTOMERS)


def _run(capsys, root: Path, *argv: str) -> tuple[int, dict]:
    rc = main(["--repo-root", str(root), *argv])
    return rc, json.loads(capsys.readouterr().out)


def _query(capsys, root: Path, *argv: str) -> tuple[int, dict]:
    return _run(capsys, root, "explore", "semantic", "query", *argv)


def _by_hand(root: Path, sql: str) -> list[list[Any]]:
    conn = duckdb.connect(str(root / "shop.duckdb"), read_only=True)
    try:
        return [list(row) for row in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def _errors(envelope: dict) -> str:
    return " ".join(envelope["errors"])


# --- the numbers -------------------------------------------------------------------


def test_a_saved_measure_grouped_by_a_column_matches_hand_written_sql(repo, capsys):
    rc, envelope = _query(capsys, repo, "orders.revenue", "--group-by", "orders.status")

    assert rc == 0, envelope["errors"]
    data = envelope["data"]
    assert data["columns"] == ["orders.status", "orders.revenue"]
    assert sorted(data["cells"]) == sorted(
        _by_hand(
            repo,
            "SELECT status, SUM(amount) FROM orders WHERE status <> 'test' "
            "GROUP BY status",
        )
    )
    assert (data["vendor"], data["execution"]) == ("slayer", "dex")
    # dex executed it, so the cost guard applied and nothing says otherwise.
    assert not any("cost guard" in warning for warning in envelope["warnings"])


def test_a_filtered_bucketed_query_matches_hand_written_sql(repo, capsys):
    rc, envelope = _query(
        capsys,
        repo,
        "orders.revenue,orders.order_count",
        "--grain",
        "month",
        "--where",
        "status = 'paid'",
        "--order-by",
        "orders.ordered_at",
    )

    assert rc == 0, envelope["errors"]
    by_hand = _by_hand(
        repo,
        "SELECT date_trunc('month', ordered_at), SUM(amount), COUNT(*) FROM orders "
        "WHERE status <> 'test' AND status = 'paid' GROUP BY 1 ORDER BY 1",
    )
    assert [cells[1:] for cells in envelope["data"]["cells"]] == [
        row[1:] for row in by_hand
    ]
    assert len(envelope["data"]["cells"]) == 2


def test_order_and_limit_reach_the_result(repo, capsys):
    rc, envelope = _query(
        capsys,
        repo,
        "orders.revenue",
        "--group-by",
        "orders.status",
        "--order-by=-orders.revenue",
        "--limit",
        "1",
    )

    assert rc == 0, envelope["errors"]
    assert envelope["data"]["cells"] == [["paid", 18.0]]


def test_an_unprofiled_relation_is_disclosed(repo, capsys):
    _, envelope = _query(capsys, repo, "orders.revenue")

    assert any(
        "name heuristic" in note and "shop.main.orders" in note
        for note in envelope["data"]["notes"]
    )


# --- the PII gate ------------------------------------------------------------------


def test_a_pii_group_by_is_refused_by_its_name(repo, capsys):
    rc, envelope = _query(
        capsys, repo, "customers.customer_count", "--group-by", "customers.email"
    )

    assert rc != 0
    assert envelope["reason"] == "guard"
    assert "customers.email" in _errors(envelope)
    assert "would surface PII" in _errors(envelope)


def test_a_pii_group_by_is_refused_from_the_profile_through_its_physical_column(
    repo, capsys
):
    """`buyer` reads `contact_email`, which the profile flags: the heuristic would pass
    the token, so the refusal is the cache speaking through the catalog."""

    rc, profiled = _run(capsys, repo, "explore", "profile", "shop.main.orders")
    assert rc == 0, profiled["errors"]

    rc, envelope = _query(capsys, repo, "orders.revenue", "--group-by", "orders.buyer")

    assert rc != 0
    assert "orders.buyer" in _errors(envelope)
    assert "profiled and flagged" in _errors(envelope)


@pytest.mark.parametrize(
    "clause",
    [
        "buyer IS NOT NULL",
        # Through the declared join, to the model the column lives on.
        "customers.email = 'a@example.com'",
        # Inside an aggregation's argument, which SLayer's own walker skips.
        "count(customers.email) > 0",
    ],
)
def test_a_pii_filter_is_refused(repo, capsys, clause):
    _run(capsys, repo, "explore", "profile", "shop.main.orders")

    rc, envelope = _query(capsys, repo, "orders.revenue", "--where", clause)

    assert rc != 0
    assert envelope["reason"] == "guard"
    assert "would surface PII" in _errors(envelope)


@pytest.mark.parametrize("clause", ["status =", "status == {state}"])
def test_a_filter_dex_cannot_read_is_refused(repo, capsys, clause):
    rc, envelope = _query(capsys, repo, "orders.revenue", "--where", clause)

    assert rc != 0
    assert envelope["reason"] == "guard"
    assert "cannot read the dimensions its own filter dialect names" in _errors(
        envelope
    )


def test_a_filtered_query_with_no_single_root_is_refused_by_the_metric(repo, capsys):
    """The filter is read against the query's root, so a metric that names none
    is the problem stated, rather than a filter the gate could not read."""

    rc, envelope = _query(capsys, repo, "orders.revnue", "--where", "status = 'paid'")

    assert rc != 0
    assert "no such metric in this semantic layer: orders.revnue" in _errors(envelope)


def test_the_gate_runs_before_anything_renders(repo, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("rendered a query the gate should have refused")

    monkeypatch.setattr(render.SlayerRenderer, "render", boom)
    layer = resolve_semantic_layer(DexEngine.from_repo(repo))

    with pytest.raises(SemanticBackendError, match="would surface PII"):
        layer.query(
            SemanticQuery(
                metrics=["customers.customer_count"], group_by=["customers.email"]
            )
        )


# --- the other refusals ------------------------------------------------------------


def test_a_connector_with_no_slayer_dialect_is_refused(repo, capsys):
    rc, envelope = _query(capsys, repo, "orders.revenue", "--connector", "clickhouse")

    assert rc != 0
    assert "no SLayer dialect for connector 'clickhouse'" in _errors(envelope)


def test_a_relation_the_connection_lacks_is_refused_before_it_runs(tmp_path, capsys):
    root = _repo(
        tmp_path,
        model(
            "orders",
            table="shop.main.archived_orders",
            columns=[
                {"name": "amount", "type": "DOUBLE"},
            ],
            measures=[{"name": "revenue", "formula": "amount:sum"}],
        ),
    )

    rc, envelope = _query(capsys, root, "orders.revenue")

    assert rc != 0
    assert "shop.main.archived_orders" in _errors(envelope)
    assert "does not have" in _errors(envelope)
    assert "sql_table" in _errors(envelope)


def test_a_slayer_resolution_error_is_reported_redacted(repo, capsys, monkeypatch):
    def unresolvable(*_a, **_k):
        raise ValueError("no path to model x via postgres://dex:hunter2@db/x")

    monkeypatch.setattr(render.SlayerRenderer, "render", unresolvable)

    rc, envelope = _query(capsys, repo, "orders.revenue")

    assert rc != 0
    assert "could not resolve the metric query" in _errors(envelope)
    assert "hunter2" not in json.dumps(envelope)


def test_the_filter_reader_needs_the_query_s_root(repo):
    layer = resolve_semantic_layer(DexEngine.from_repo(repo))

    assert layer.filter_refs(["status = 'paid'"]) is None
    assert layer.filter_refs(
        ["status = 'paid' and customers.tier = 'gold'"], source_model="orders"
    ) == ["orders.status", "customers.tier"]


# --- the billed path ---------------------------------------------------------------


def test_a_billed_connector_asks_before_any_spend(
    fake_bq_client, tmp_path, capsys, monkeypatch
):
    import exmergo_dex_core.connect as connect_mod
    from exmergo_dex_core.adapters.bigquery import BigQueryAdapter
    from exmergo_dex_core.config import BigQueryTarget, load_config
    from exmergo_dex_core.connect import new_cost_gate
    from exmergo_dex_core.storage import FilesystemStore

    customers = model(
        "customers",
        table="test-proj.shop.customers",
        columns=[{"name": "id", "type": "INT"}, {"name": "email", "type": "TEXT"}],
        measures=[{"name": "customer_count", "formula": "*:count"}],
    )
    name = "models/wh/customers.yaml"
    path = tmp_path / BASE / name
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(customers), encoding="utf-8")
    (tmp_path / ".dex").mkdir()
    (tmp_path / ".dex" / "config.yml").write_text(
        "connector: bigquery\nbigquery:\n  project: test-proj\n"
        "budget:\n  session_ceiling: 1073741824\n"
        f"semantic:\n  vendor: slayer\n  slayer:\n    base_dir: {BASE}\n"
        f"    models:\n      - {name}\n",
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    store = FilesystemStore(tmp_path)

    def opener(**opened):
        return BigQueryAdapter(
            project="test-proj",
            cost_gate=new_cost_gate(
                "bigquery",
                config,
                store,
                budget=opened.get("budget"),
                confirmed=opened.get("confirmed", False),
                command=opened.get("command"),
            ),
            target=BigQueryTarget(),
            client=fake_bq_client,
            principal_type="user",
        )

    monkeypatch.setattr(connect_mod, "open_adapter", opener)

    _, envelope = _query(
        capsys, tmp_path, "customers.customer_count", "--group-by", "customers.id"
    )

    assert envelope["status"] == "needs_confirmation", envelope["errors"]
    assert envelope["cost"]["estimate"] > 0
    assert fake_bq_client.query_calls, "nothing was priced, so nothing was proven"
    assert all(call.dry_run for call in fake_bq_client.query_calls)
    assert "test-proj.shop.customers" in fake_bq_client.query_calls[-1].sql.replace(
        "`", ""
    )
