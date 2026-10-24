"""`transform plan` warns when an edit contradicts what the model declares (#495).

Each test reads three states (the prior SQL and declaration, the authored SQL
and the post-change declaration, and the difference) and pins which side a
contradiction blames: an edit that breaks an unchanged declaration blames the
SQL, a declaration changed without its SQL blames the declaration, and a change
made to both in one plan is silent. What dex cannot read is reported as
unchecked, never as a rule removed.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

import pytest
import yaml

from exmergo_dex_core.cache import ColumnProfile, Dataset, DexCache
from exmergo_dex_core.cli import main
from exmergo_dex_core.transform.contradictions import pair_rows, warnings
from exmergo_dex_core.transform.drafting import draft

from .conftest import MODEL_PATH, PRIOR_MODEL

# The fake BigQuery project row attribution's own metered tests run on; absent
# without the bigquery extra, which skips only the one test that needs it.
with contextlib.suppress(pytest.skip.Exception):
    from .test_row_attribution import metered_project, orders_bq_client  # noqa: F401

pytest.importorskip("sqlglot")

SAME = object()

STG = (
    "select order_id, customer_id, status, amount from {{ source('raw', 'orders') }}\n"
)
EXCLUDING = (
    "select order_id, amount from {{ ref('stg_orders') }} where status <> 'cancelled'\n"
)
KEEPING = "select order_id, amount from {{ ref('stg_orders') }}\n"


def _yml(model: str = "fct", *, grain=None, filters=None, columns=None) -> str:
    dex: dict = {}
    if grain is not None:
        dex["grain"] = grain
    if filters is not None:
        dex["population"] = {"filters": filters}
    entry: dict = {"name": model}
    if dex:
        entry["config"] = {"meta": {"dex": dex}}
    if columns:
        entry["columns"] = [
            {"name": name, "config": {"meta": {"dex": facts}}}
            for name, facts in columns.items()
        ]
    return yaml.safe_dump({"version": 2, "models": [entry]}, sort_keys=False)


def _found(
    prior_sql: str,
    sql: str,
    *,
    prior_yml: str | None = None,
    yml: object = SAME,
    others: dict[str, str] | None = None,
    prior_others: dict[str, str] | None = None,
    cache: DexCache | None = None,
    cumulative: dict[str, set[str]] | None = None,
) -> tuple[list[dict], list[str]]:
    """The contradictions draft reports for ``fct``, and their warnings."""

    base = {"models/stg_orders.sql": STG, **(others or {})}
    prior = {**base, **(prior_others or {}), "models/fct.sql": prior_sql}
    files = {**base, "models/fct.sql": sql}
    if prior_yml is not None:
        prior["models/fct.yml"] = prior_yml
    post_yml = prior_yml if yml is SAME else yml
    if post_yml is not None:
        files["models/fct.yml"] = post_yml
    drafts, draft_warnings = draft(
        ["fct"],
        files,
        ["models"],
        cache,
        dialect="duckdb",
        cumulative=cumulative,
        prior=prior,
    )
    assert not any("could not check 'fct'" in w for w in draft_warnings), draft_warnings
    found = drafts["fct"]["contradictions"]
    return found, warnings("fct", found)


EXCLUDES_CANCELLED = _yml(filters=[{"column": "status", "excludes": ["cancelled"]}])


# --- population -------------------------------------------------------------------


def test_a_removed_exclusion_blames_the_sql_and_names_both_fixes():
    [found], [warning] = _found(EXCLUDING, KEEPING, prior_yml=EXCLUDES_CANCELLED)

    assert found == {
        "check": "population",
        "status": "contradicted",
        "rule": "population.filters status excludes ['cancelled']",
        "column": "status",
        "stale": "sql",
        "prior": "status <> 'cancelled'",
        "preexisting": False,
    }
    assert warning.startswith(
        "'fct' declares population.filters status excludes ['cancelled'], and the "
        "filter behind it (`status <> 'cancelled'`) is gone; the SQL looks stale."
    )
    assert "Restore the filter if the declared population still holds" in warning
    assert "update the declaration in this same plan" in warning


def test_a_changed_predicate_is_a_contradiction_too():
    [found], [warning] = _found(
        EXCLUDING,
        EXCLUDING.replace("<> 'cancelled'", "not in ('cancelled', 'returned')"),
        prior_yml=EXCLUDES_CANCELLED,
    )

    assert found["stale"] == "sql"
    assert found["prior"] == "status <> 'cancelled'"
    assert found["authored"] == "NOT status IN ('cancelled', 'returned')"
    assert "changed from `status <> 'cancelled'` to" in warning


def test_a_filter_removed_from_a_cte_is_found_through_the_lineage():
    prior = (
        "with base as (select * from {{ ref('stg_orders') }} o "
        "where o.status != 'cancelled')\nselect order_id, amount from base\n"
    )
    [found], _ = _found(
        prior,
        prior.replace(" o where o.status != 'cancelled'", ""),
        prior_yml=EXCLUDES_CANCELLED,
    )
    assert (found["check"], found["stale"]) == ("population", "sql")


def test_a_reformat_or_an_alias_rename_of_the_predicate_is_silent():
    prior = (
        "select o.order_id, o.amount from {{ ref('stg_orders') }} o "
        "where o.status <> 'cancelled'\n"
    )
    reformatted = (
        "select\n  s.order_id,\n  s.amount\nfrom {{ ref('stg_orders') }} as s\n"
        "where   s.status != 'cancelled'\n"
    )
    assert _found(prior, reformatted, prior_yml=EXCLUDES_CANCELLED) == ([], [])


def test_not_in_and_a_chain_of_inequalities_compare_equal():
    rule = _yml(filters=[{"column": "status", "excludes": ["cancelled", "returned"]}])
    prior = KEEPING.rstrip() + " where status not in ('cancelled', 'returned')\n"
    authored = (
        KEEPING.rstrip() + " where status <> 'returned' and status <> 'cancelled'\n"
    )
    assert _found(prior, authored, prior_yml=rule) == ([], [])


def test_an_allowlist_that_omits_the_excluded_value_implements_the_exclusion():
    authored = KEEPING.rstrip() + " where status in ('shipped', 'completed')\n"
    assert _found(EXCLUDING, authored, prior_yml=EXCLUDES_CANCELLED) == ([], [])


def test_an_unsupported_macro_predicate_is_unchecked_never_removed():
    authored = KEEPING.rstrip() + " where {{ active_only() }}\n"
    [found], [warning] = _found(EXCLUDING, authored, prior_yml=EXCLUDES_CANCELLED)

    assert found["status"] == "unchecked"
    assert "stale" not in found and "preexisting" not in found
    assert "active_only" in found["reason"]
    assert "Nothing was assumed removed" in warning
    assert "is gone" not in warning


def test_a_model_dex_cannot_read_at_all_is_one_warning_naming_every_rule():
    rule = _yml(
        grain=["order_id"],
        filters=[{"column": "status", "excludes": ["cancelled"]}],
        columns={"amount": {"role": "measure"}},
    )
    authored = KEEPING.rstrip() + " where {{ active_only() }}\n"
    found, [warning] = _found(EXCLUDING, authored, prior_yml=rule)

    assert [(f["check"], f["status"]) for f in found] == [
        ("population", "unchecked"),
        ("grain", "unchecked"),
        ("columns", "unchecked"),
    ]
    assert warning.startswith(
        "'fct': could not check this edit against its declared population.filters "
        "status excludes ['cancelled']; its declared grain [order_id]; and its "
        "declared amount as a measure: "
    )


def test_a_function_around_the_column_is_unchecked():
    authored = KEEPING.rstrip() + " where lower(status) <> 'cancelled'\n"
    [found], _ = _found(EXCLUDING, authored, prior_yml=EXCLUDES_CANCELLED)
    assert found["status"] == "unchecked"
    assert "LOWER(status)" in found["reason"]


# --- which side looks stale --------------------------------------------------------


def test_an_intentional_change_to_both_sides_in_one_plan_is_silent():
    # The exclusion is dropped from the SQL and from the declaration together.
    assert _found(EXCLUDING, KEEPING, prior_yml=EXCLUDES_CANCELLED, yml=_yml()) == (
        [],
        [],
    )
    # The exclusion widens on both sides together.
    widened = EXCLUDING.replace("<> 'cancelled'", "not in ('cancelled', 'returned')")
    rule = _yml(filters=[{"column": "status", "excludes": ["cancelled", "returned"]}])
    assert _found(EXCLUDING, widened, prior_yml=EXCLUDES_CANCELLED, yml=rule) == (
        [],
        [],
    )


def test_a_declaration_only_change_blames_the_declaration_not_the_sql():
    rule = _yml(filters=[{"column": "status", "excludes": ["cancelled", "returned"]}])
    [found], [warning] = _found(
        EXCLUDING, EXCLUDING, prior_yml=EXCLUDES_CANCELLED, yml=rule
    )

    assert found["stale"] == "declaration"
    assert "its SQL filters `status <> 'cancelled'`, which does not implement it" in (
        warning
    )
    assert "the declaration looks stale, or the plan is half done" in warning
    assert "SQL looks stale" not in warning
    assert "changed from" not in warning


def test_a_new_declaration_that_matches_the_sql_is_silent():
    assert _found(EXCLUDING, EXCLUDING, yml=EXCLUDES_CANCELLED) == ([], [])


def test_both_sides_changed_and_still_disagreeing_blames_neither_alone():
    rule = _yml(filters=[{"column": "status", "excludes": ["cancelled", "returned"]}])
    [found], [warning] = _found(
        EXCLUDING, KEEPING, prior_yml=EXCLUDES_CANCELLED, yml=rule
    )
    assert found["stale"] == "either"
    assert "changes both the SQL and the declaration" in warning


def test_a_preexisting_contradiction_is_silent_on_an_unrelated_edit():
    # The declaration already said cancelled orders are out; the SQL already
    # kept them. This plan only adds a column.
    authored = KEEPING.replace("amount", "amount, customer_id")
    assert _found(KEEPING, authored, prior_yml=EXCLUDES_CANCELLED) == ([], [])


def test_a_preexisting_contradiction_the_edit_touches_is_reported_as_such():
    prior = KEEPING.rstrip() + " where status <> 'returned'\n"
    authored = KEEPING.rstrip() + " where status <> 'pending'\n"
    [found], [warning] = _found(prior, authored, prior_yml=EXCLUDES_CANCELLED)
    assert found["stale"] == "sql"
    assert found["preexisting"] is True
    assert "already disagreed before this plan" in warning


# --- grain and columns ------------------------------------------------------------


MONTHLY = (
    "select customer_id, month, sum(amount) as revenue\n"
    "from {{ ref('stg_monthly') }}\ngroup by customer_id, month\n"
)
MONTHLY_STG = "select customer_id, month, amount from {{ source('raw', 'm') }}\n"


def test_a_changed_group_by_contradicts_the_declared_grain():
    [found], [warning] = _found(
        MONTHLY,
        "select customer_id, max(month) as month, sum(amount) as revenue\n"
        "from {{ ref('stg_monthly') }}\ngroup by customer_id\n",
        prior_yml=_yml(grain=["customer_id", "month"]),
        others={"models/stg_monthly.sql": MONTHLY_STG},
    )

    assert found["check"] == "grain"
    assert found["stale"] == "sql"
    assert found["prior"].startswith("[customer_id, month]")
    assert found["authored"].startswith("[customer_id]")
    assert warning.startswith(
        "'fct' declares grain [customer_id, month], and its SQL now reads at grain "
        "[customer_id]"
    )


def test_a_dropped_grain_column_is_one_contradiction_not_two():
    prior_yml = _yml(
        grain=["customer_id", "month"],
        columns={"month": {"role": "time"}, "revenue": {"role": "measure"}},
    )
    [found], [warning] = _found(
        MONTHLY,
        "select customer_id, sum(amount) as revenue\n"
        "from {{ ref('stg_monthly') }}\ngroup by customer_id\n",
        prior_yml=prior_yml,
        others={"models/stg_monthly.sql": MONTHLY_STG},
    )
    assert (found["check"], found["column"]) == ("grain", "month")
    assert "its SQL does not select month" in warning


def test_a_removed_declared_column_says_why_it_mattered():
    prior_yml = _yml(
        columns={
            "amount": {
                "role": "measure",
                "aggregation": "sum",
                "unit": "currency:EUR",
            }
        }
    )
    [found], [warning] = _found(
        EXCLUDING,
        EXCLUDING.replace("order_id, amount", "order_id"),
        prior_yml=prior_yml,
    )
    assert found["check"] == "columns"
    assert found["rule"] == "amount as a measure (aggregation sum, unit currency:EUR)"
    assert "its SELECT list does not produce amount" in warning


def test_a_grain_the_sql_cannot_establish_is_unchecked_only_when_touched():
    # No cache, so no key is proven; the grain is withheld on both sides.
    rule = _yml(grain=["order_id"])
    assert _found(
        EXCLUDING, EXCLUDING.replace("amount", "amount * 2 as amount"), prior_yml=rule
    ) == ([], [])


# --- additivity -------------------------------------------------------------------


STANDINGS = (
    "select race_id, driver_id, season_points from {{ source('f1', 'standings') }}\n"
)
STANDINGS_YML = _yml(
    "stg_standings",
    columns={"season_points": {"role": "measure", "additivity": "semi_additive"}},
)


def test_summing_a_declared_season_to_date_column_names_the_parent():
    [found], [warning] = _found(
        "select driver_id, max(season_points) as points\n"
        "from {{ ref('stg_standings') }}\ngroup by driver_id\n",
        "select driver_id, sum(season_points) as points\n"
        "from {{ ref('stg_standings') }}\ngroup by driver_id\n",
        others={
            "models/stg_standings.sql": STANDINGS,
            "models/stg_standings.yml": STANDINGS_YML,
        },
    )

    assert found["check"] == "additivity"
    assert found["declared_on"] == "stg_standings"
    assert found["stale"] == "sql"
    assert found["authored"] == "SUM(season_points)"
    assert warning.startswith(
        "'stg_standings' declares season_points semi_additive (it does not add "
        "across time), and 'fct' aggregates it with SUM(season_points)"
    )


def test_averaging_a_declared_ratio_is_a_re_aggregation():
    funnel = "select channel, conversion_rate from {{ source('web', 'funnel') }}\n"
    funnel_yml = _yml(
        "stg_funnel",
        columns={
            "conversion_rate": {
                "role": "measure",
                "additivity": "non_additive",
                "unit": "fraction",
            }
        },
    )
    [found], _ = _found(
        "select channel, conversion_rate from {{ ref('stg_funnel') }}\n",
        "select channel, avg(conversion_rate) as conversion_rate\n"
        "from {{ ref('stg_funnel') }}\ngroup by channel\n",
        others={"models/stg_funnel.sql": funnel, "models/stg_funnel.yml": funnel_yml},
    )
    assert found["check"] == "additivity"
    assert found["authored"] == "AVG(conversion_rate)"
    assert "a ratio" in found["rule"]


def test_an_additive_declaration_outranks_the_cumulative_check():
    cache = DexCache(
        datasets=[
            Dataset(
                identifier="wh.main.stg_standings",
                columns=[ColumnProfile(name="season_points", data_type="integer")],
            )
        ]
    )
    common = {
        "cache": cache,
        "cumulative": {"wh.main.stg_standings": {"season_points"}},
    }
    prior = (
        "select driver_id, max(season_points) as p\n"
        "from {{ ref('stg_standings') }} group by 1\n"
    )
    authored = prior.replace("max(", "sum(")
    [found], [warning] = _found(
        prior, authored, others={"models/stg_standings.sql": STANDINGS}, **common
    )
    assert found["check"] == "additivity" and "declared_on" not in found
    assert "is a running total" in warning

    additive = _yml(
        "stg_standings",
        columns={"season_points": {"role": "measure", "additivity": "additive"}},
    )
    assert _found(
        prior,
        authored,
        others={
            "models/stg_standings.sql": STANDINGS,
            "models/stg_standings.yml": additive,
        },
        **common,
    ) == ([], [])


def test_a_new_model_has_nothing_to_contradict():
    drafts, _ = draft(
        ["fct"],
        {
            "models/stg_orders.sql": STG,
            "models/fct.sql": KEEPING,
            "models/fct.yml": EXCLUDES_CANCELLED,
        },
        ["models"],
        None,
        dialect="duckdb",
        prior={"models/stg_orders.sql": STG},
    )
    assert "contradictions" not in drafts["fct"]


def test_row_attribution_is_cited_and_never_re_measured():
    found = [
        {
            "check": "population",
            "status": "contradicted",
            "stale": "sql",
            "column": "status",
        }
    ]
    pair_rows(
        found,
        [
            {
                "path": "models/fct.sql",
                "changes": [
                    {"kind": "predicate_removed", "prior": "amount > 0", "delta": 7},
                    {
                        "kind": "predicate_removed",
                        "prior": "o.status <> 'x'",
                        "delta": 2,
                    },
                ],
            }
        ],
    )
    assert found[0]["row_delta"] == 2


# --- end to end -------------------------------------------------------------------


DECLARED = """version: 2
models:
  - name: fct_orders
    config:
      meta:
        dex:
          population:
            rule: Cancelled orders are excluded.
            filters:
              - column: status
                excludes: ['CANCELLED']
"""

BAD_EDIT = PRIOR_MODEL.replace("status != 'CANCELLED' and ", "")


def _plan(repo: Path, warehouse: Path, capsys, *flags: str) -> dict:
    payload = repo / "edits.json"
    payload.write_text(
        json.dumps(
            {"edits": [{"path": MODEL_PATH, "kind": "model_sql", "content": BAD_EDIT}]}
        ),
        encoding="utf-8",
    )
    rc = main(
        [
            "--repo-root",
            str(repo),
            "transform",
            "plan",
            "drop the cancellation filter",
            "--edits-file",
            str(payload),
            "--connector",
            "duckdb",
            "--path",
            str(warehouse),
            *flags,
        ]
    )
    envelope = json.loads(capsys.readouterr().out)
    assert rc == 0, envelope
    return envelope


def test_on_duckdb_the_contradiction_cites_the_measured_row_delta(
    attributable_project, capsys
):
    repo, warehouse = attributable_project
    (repo / "analytics" / "models" / "marts" / "fct_orders.yml").write_text(
        DECLARED, encoding="utf-8"
    )
    envelope = _plan(repo, warehouse, capsys)

    [found] = envelope["data"]["declarations"]["fct_orders"]["contradictions"]
    [removed] = [
        c
        for c in envelope["data"]["row_attribution"][0]["changes"]
        if c["kind"] == "predicate_removed"
    ]
    assert removed["delta"] > 0
    assert found["row_delta"] == removed["delta"]
    [warning] = [w for w in envelope["warnings"] if "population.filters" in w]
    assert f"measured that change at +{removed['delta']} rows" in warning
    # A warning, never a refusal: the plan is stored and nothing is written.
    assert envelope["status"] == "ok" and envelope["data"]["plan_id"]
    assert (repo / "analytics" / MODEL_PATH).read_text() == PRIOR_MODEL


def test_naming_a_contradiction_opens_no_connection(
    attributable_project, capsys, monkeypatch
):
    import exmergo_dex_core.connect as connect
    from exmergo_dex_core.engine import DexEngine

    repo, warehouse = attributable_project
    (repo / "analytics" / "models" / "marts" / "fct_orders.yml").write_text(
        DECLARED, encoding="utf-8"
    )

    def refuse(*_args, **_kwargs):
        raise AssertionError("checking a declaration opened a warehouse connection")

    monkeypatch.setattr(connect, "open_adapter", refuse)
    monkeypatch.setattr(DexEngine, "_adapter", refuse)
    envelope = _plan(repo, warehouse, capsys, "--no-attribute-rows")

    [found] = envelope["data"]["declarations"]["fct_orders"]["contradictions"]
    assert found["stale"] == "sql" and "row_delta" not in found
    assert any(
        "named that change and did not measure it" in w for w in envelope["warnings"]
    )


def test_on_a_billed_connector_it_is_named_and_measured_only_on_request(
    request, tmp_path
):
    pytest.importorskip("google.cloud.bigquery")
    metered_project = request.getfixturevalue("metered_project")
    (tmp_path / "analytics" / "models" / "marts" / "fct_orders.yml").write_text(
        DECLARED, encoding="utf-8"
    )
    envelope, opened = metered_project()

    assert envelope.status.value == "ok"
    assert opened == [], "nothing opens before --attribute-rows authorizes it"
    [found] = envelope.data["declarations"]["fct_orders"]["contradictions"]
    assert (found["check"], found["stale"]) == ("population", "sql")
    assert "row_delta" not in found
    [warning] = [w for w in envelope.warnings if "population.filters" in w]
    assert "--attribute-rows" in warning
