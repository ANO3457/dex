"""What a project declares, in terms no format owns.

Tier 1 of the project seam returns :class:`ProjectDefinitions`, and every format
that reaches that tier returns this same type. So it lives here rather than
beside the reader that happened to define it first: `dbt_project` imports the
dbt semantic reader and the MetricFlow dialect map at module scope, and a second
format returning its declarations from there would import dbt's reader to state
that it declares a unique key. That is not a hypothetical tidiness argument. The
rule the Ossie format is held to is that neither format imports the other's
reader, and an import that arrives transitively breaks it exactly as thoroughly
as one written by hand.

A leaf module, in the idiom :mod:`exmergo_dex_core.semantic_catalog` already
sets for the other neutral read model: pydantic and nothing else, so it stays
importable in a base install and cannot grow a dependency on any one format's
world. The names are re-exported from `dbt_project`, where they have been public
since v1.

**The vocabulary is the warehouse's, not any format's.** ``model`` is the
referable name the format uses for a relation, ``relation`` is the physical name
where the format could resolve one, and ``source`` records which channel of the
format stated it. A format with no equivalent of a field leaves it unset rather
than inventing one, because an absent declaration and a guessed one read the
same downstream and only one of them is true.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = [
    "DeclaredColumnMeaning",
    "DeclaredCompositeKey",
    "DeclaredForeignKey",
    "DeclaredKey",
    "DeclaredPopulation",
    "DeclaredPopulationFilter",
    "DeclaredRelationship",
    "ModelDeclaration",
    "ProjectDefinitions",
]


class DeclaredForeignKey(BaseModel):
    """One declared join: child column to parent column.

    ``relation`` / ``to_relation`` carry quote-stripped physical names when the
    format resolves them; a format that resolves by name alone leaves them None,
    and downstream resolution is name-based.
    """

    model: str
    relation: str | None = None
    column: str
    to_model: str
    to_relation: str | None = None
    to_column: str
    source: str


class DeclaredRelationship(BaseModel):
    """A declared physical relationship with every ordered key pair intact.

    Unlike :class:`DeclaredForeignKey`, this can state a composite join without
    pretending one member is independently a foreign key.
    """

    model: str
    relation: str | None = None
    to_model: str
    to_relation: str | None = None
    column_pairs: list[tuple[str, str]]
    source: str
    name: str | None = None


class DeclaredKey(BaseModel):
    """A column declared unique and/or not null on one model."""

    model: str
    relation: str | None = None
    column: str
    unique: bool = False
    not_null: bool = False
    source: str


class DeclaredCompositeKey(BaseModel):
    """A declared grain over several columns: the columns whose COMBINATION is
    unique, never any one of them alone.

    A distinct model from ``DeclaredKey`` rather than a widened ``column``:
    this declaration has no ``not_null`` variant and a different multiplicity
    (it is the model's own claim about several columns together, not one
    column's own test), so overloading ``column`` to sometimes hold a list would
    blur two different concepts into one field.
    """

    model: str
    relation: str | None = None
    columns: list[str]
    source: str


class DeclaredColumnMeaning(BaseModel):
    """What one column of a model is, in the model's own declaration (#491).

    The fields exploration reads back (#498): what part the column plays, the
    unit its values are in, how it adds up, and the ``<model>.<column>`` it
    references. Every one is optional because a declaration may be partial, and
    an unstated field stays unset rather than defaulted.
    """

    role: str | None = None
    unit: str | None = None
    additivity: str | None = None
    references: str | None = None


class DeclaredPopulationFilter(BaseModel):
    """One filter of a declared population: the values a column keeps or drops."""

    column: str
    includes: list[str | int | float | bool] | None = None
    excludes: list[str | int | float | bool] | None = None


class DeclaredPopulation(BaseModel):
    """Which rows a model keeps: a sentence, structured filters, or both."""

    rule: str | None = None
    filters: list[DeclaredPopulationFilter] = Field(default_factory=list)


class ModelDeclaration(BaseModel):
    """A model's declaration as the project states it (#491), read back (#498).

    The model's own statement of what one row is (``grain``), which rows are in
    (``population``) and what each column means (``columns``). ``source`` is the
    channel it was read from, as on every other declared object here. A format
    with no declarations leaves :attr:`ProjectDefinitions.model_declarations`
    empty rather than inventing one.
    """

    model: str
    relation: str | None = None
    grain: list[str] | None = None
    population: DeclaredPopulation | None = None
    columns: dict[str, DeclaredColumnMeaning] = Field(default_factory=dict)
    source: str


class ProjectDefinitions(BaseModel):
    """What the project declares, loaded once for consumers that must keep
    working without one.

    ``present`` False means no readable project: every collection is empty and
    consumers degrade instead of erroring. ``relationship_source`` and
    ``semantic_source`` record where each half came from (for dbt, ``"manifest"``
    is exact and ``"yaml"`` resolves by name; another format names its own
    channels). ``model_relations`` maps each model the project builds to its
    quote-stripped physical relation, keyed by the model's label (for dbt, the
    model name, and ``<name>.v<N>`` for a versioned model, one entry per
    version); every key is a model, so a consumer never has to tell a model
    from a source by its spelling. ``source_relations`` maps what the project
    reads but does not build (for dbt, ``source.table``) the same way.
    ``primary_entities``
    maps model names to their declared grain column; ``metric_models`` lists
    models reachable from any metric. ``declared_composite_keys`` carries
    multi-column grain declarations -- something a column-level test structurally
    cannot express. ``declared_grains`` maps a model label to the grain its
    declaration states (for dbt, ``config.meta.dex.grain``, #491): one column or
    several, the model's own statement of what one row is rather than a test's,
    and the first source `maintain verify` checks a grain from (#496).
    ``model_declarations`` maps a model label to its whole declaration
    (:class:`ModelDeclaration`), which `explore --use-project` reads back (#498).
    ``built_relation_names`` is bare table names (lowered) the
    project builds or sources, from files alone (populated even with no compiled
    artifact, unlike ``model_relations``) -- explore's orphan-relation
    down-ranking reads this, so a format that declares relations without building
    them leaves it empty and says so in a note. ``notes`` are analyst-readable
    caveats for the caller's envelope, and the channel a tier-1 read uses to say
    what it could not do, since the tier may not raise.
    """

    present: bool = False
    project_dir: str | None = None
    manifest_loaded: bool = False
    manifest_stale: bool = False
    relationship_source: str | None = None
    semantic_source: str | None = None
    foreign_keys: list[DeclaredForeignKey] = Field(default_factory=list)
    declared_relationships: list[DeclaredRelationship] = Field(default_factory=list)
    declared_keys: list[DeclaredKey] = Field(default_factory=list)
    declared_composite_keys: list[DeclaredCompositeKey] = Field(default_factory=list)
    model_relations: dict[str, str] = Field(default_factory=dict)
    source_relations: dict[str, str] = Field(default_factory=dict)
    primary_entities: dict[str, str] = Field(default_factory=dict)
    declared_grains: dict[str, list[str]] = Field(default_factory=dict)
    model_declarations: dict[str, ModelDeclaration] = Field(default_factory=dict)
    metric_models: list[str] = Field(default_factory=list)
    built_relation_names: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
