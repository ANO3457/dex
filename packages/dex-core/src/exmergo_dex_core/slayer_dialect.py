"""The SLayer query dialect: which columns a SLayer filter names.

The PII gate refuses a filtered query unless the backend can say which dimensions
the filter names (:func:`.explore.semantic.policy.requested_dimension_refs`). A
SLayer filter is a Mode-B expression, Python syntax with SQL operator spellings
admitted (``status = 'paid'``, ``email IS NULL``, ``sum(amount) > 100``), so
neither sqlglot nor MetricFlow's Jinja patterns can read it. SLayer's own reader
can, and this module is built on it: ``parse_filter_expr`` turns a clause into
the pinned release's typed tree, and the references in that tree resolve to
``model.column`` tokens, the key the SLayer catalog gives each dimension.

**Fail-closed, which SLayer's own extractor is not.** SLayer's drift code has an
extractor (``_filter_refs_dsl``), but it is private and returns ``[]`` when a
clause does not parse, which here would read as "this filter names nothing" and
let every column it named past the gate. :func:`filter_refs` returns ``None``
instead for anything it cannot account for, and the neutral gate then refuses
the query:

- a clause that does not parse;
- a clause carrying ``{var}`` syntax anywhere, quoted or not. SLayer fills a
  query's placeholders from the model's declared defaults when the caller passes
  none, which dex never does, and substitutes them raw, so ``country == {c}``
  with ``c: email`` renders as a comparison against the ``email`` column. What a
  placeholder becomes is decided after the gate has run;
- a dotted reference that does not resolve to exactly one model through the
  declared joins (unknown, ambiguous, or circular), because the token the gate
  would screen is then a guess;
- a node the pinned release's grammar did not have when this was written.

**Every reference counts, aggregation arguments included.** SLayer's
``walk_parsed_refs`` treats an aggregation's and a transform's arguments as
opaque by design, which is right for drift tagging and wrong for screening:
``rank(sum(amount), partition_by=customers.email) <= 1`` partitions by a PII
column it would never surface. So the tree is walked whole, every field of every
node, and a reference anywhere in it is reported. Over-reporting is the safe
direction: a token that names no dimension is screened by name and passes.

A leaf beside :mod:`.metricflow_dialect`, importing nothing of dex's. It does
import SLayer, so it is reached only where the ``[slayer]`` extra is known to be
installed.
"""

from __future__ import annotations

# First, before any SLayer import: importing SLayer rewrites sqlglot's reserved
# keywords process-wide, and this module undoes that (see `sqlglot_keywords`).
from .slayer import sqlglot_keywords  # noqa: F401

# isort: split

from collections.abc import Iterator, Mapping
from decimal import Decimal

from pydantic import BaseModel
from slayer.core.models import SlayerModel
from slayer.core.query import has_variable_syntax
from slayer.engine.syntax import (
    AggCall,
    Arith,
    BoolOp,
    Cmp,
    DottedRef,
    Literal,
    Placeholder,
    Ref,
    ScalarCall,
    StarSource,
    TransformCall,
    TupleLit,
    UnaryOp,
    parse_filter_expr,
)
from slayer.sql.column_expansion import resolve_ref_target

__all__ = ["filter_refs"]

# Every node of the pinned release's Mode-B tree. A node outside this set is one
# the walk below has never seen, so it cannot know whether it carries a reference.
_KNOWN_NODES = (
    AggCall,
    Arith,
    BoolOp,
    Cmp,
    DottedRef,
    Literal,
    Placeholder,
    Ref,
    ScalarCall,
    StarSource,
    TransformCall,
    TupleLit,
    UnaryOp,
)

# Field values that are data rather than structure: an operator, a function name,
# a kwarg's name, a literal's value.
_SCALARS = (str, int, float, Decimal, bool, type(None))


def filter_refs(
    clauses: list[str],
    source_model: str,
    *,
    models: Mapping[str, SlayerModel],
) -> list[str] | None:
    """Every ``model.column`` token a set of SLayer filter clauses names, or None.

    ``source_model`` is the model the query is rooted at, the ``model`` of its
    ``model.measure`` metric; ``models`` maps each model's name to the validated
    model, which is where the declared joins a dotted reference walks live. A
    bare reference resolves to the source model, a dotted one through those joins
    to the model it ends on (``customers.regions.name`` from ``orders`` is
    ``regions.name``).

    In clause order and expression order, duplicates included, matching
    :func:`.metricflow_dialect.filter_refs`: de-duplication belongs to the caller
    that merges these with the group-by tokens. Never raises: anything it cannot
    account for is None, and None is the gate's cue to refuse.
    """

    try:
        source = models.get(source_model)
        if source is None:
            return None
        refs: list[str] = []
        for clause in clauses:
            if has_variable_syntax(clause):
                return None
            parsed = parse_filter_expr(clause)
            refs.extend(_token(node, source, models) for node in _references(parsed))
        return refs
    except Exception:
        return None


def _references(node: object) -> Iterator[Ref | DottedRef]:
    """Every reference in a parsed tree, in expression order, every field read."""

    if isinstance(node, (Ref, DottedRef)):
        yield node
    elif isinstance(node, BaseModel):
        if not isinstance(node, _KNOWN_NODES):
            raise ValueError(type(node).__name__)
        for name in type(node).model_fields:
            yield from _references(getattr(node, name))
    elif isinstance(node, (tuple, list)):
        for item in node:
            yield from _references(item)
    elif not isinstance(node, _SCALARS):
        raise ValueError(type(node).__name__)


def _token(
    node: Ref | DottedRef, source: SlayerModel, models: Mapping[str, SlayerModel]
) -> str:
    """The ``model.column`` a reference names, resolved through declared joins."""

    if isinstance(node, Ref):
        return f"{source.name}.{node.name}"
    *qualifiers, leaf = node.parts
    target = resolve_ref_target(
        qualifiers=tuple(qualifiers),
        source_model=source,
        models_by_name=dict(models),
    )
    if target is None:
        raise ValueError(".".join(node.parts))
    return f"{target.name}.{leaf}"
