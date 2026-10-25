"""What an edit's content actually contains, read from the content itself.

A host deciding whether a change may be applied offline needs to know whether it
carries executable or authority-bearing content, and it cannot take that from the
edit's declared :class:`~..transform.plans.EditKind` or from the filename. Both
are supplied by whoever authored the edit, and both describe where the file goes
rather than what is in it. A ``semantic_yml`` edit is a declaration of metrics
until it also carries a ``post-hook``, at which point applying it means the next
build runs SQL the repository chose, and nothing about the kind or the extension
says so.

So the verdict here is computed from content and operation only. The kind is not
consulted, deliberately, and a caller passing a kind that contradicts its own
content gets the content's answer.

Three properties matter more than the taxonomy:

**Silence never reads as safe.** Content that does not parse is
:attr:`ArtifactClass.UNKNOWN`, never ``DECLARATIVE``. A classifier that fell back
to "declarative" on anything it could not read would be most confident exactly
where it understood least.

**A signal is reported even when it did not decide the class.** A document
carrying both a hook and a ``grants`` block classifies as executable, and the
grant is still listed, because a host applying its own policy needs the evidence
rather than the verdict alone.

**Nothing here is rendered.** :func:`~..dbt_project.jinja_regions` is a scanner,
so this says what a template *names*, never what it produces. A macro call is a
signal because its meaning lives in code the repository controls, which is the
fact a host offline in a disposable checkout is actually asking about.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .. import metricflow_dialect
from ..dbt_project import jinja_regions
from ..edits import Edit, EditOp


class ArtifactClass(str, Enum):
    """What the content is, as distinct from where it is filed."""

    #: Statements of fact the build reads: models, columns, tests, metrics.
    DECLARATIVE = "declarative"
    #: Content that runs, or that makes something else run: SQL, jinja, hooks.
    EXECUTABLE = "executable"
    #: Content that confers rights rather than running: grants, external storage.
    AUTHORITY_BEARING = "authority_bearing"
    #: Values, not instructions: a seed's rows.
    DATA = "data"
    #: dex could not read it. Never a synonym for "declarative and safe".
    UNKNOWN = "unknown"


#: Signals whose presence makes content executable, and the ones that make it
#: authority-bearing. Kept as data rather than as branches so the two lists are
#: readable next to each other and a new signal has to declare which it is.
EXECUTABLE_SIGNALS = frozenset(
    {
        "pre_hook",
        "post_hook",
        "on_run_start",
        "on_run_end",
        "run_operation",
        "run_query",
        "statement_block",
        "macro_call",
        "jinja_statement",
        "jinja_expression",
        "python_model",
        "sql_statement",
        # A dependency declaration: `dbt deps` fetches whatever it names and the
        # next build runs that package's macros and materializations. The
        # source type is in the name, so a host can choose to admit, say, a hub
        # package pinned to an exact version.
        "dependency_hub",
        "dependency_git",
        "dependency_local",
        "dependency_tarball",
        "dependency_private",
        "dependency",
    }
)

AUTHORITY_SIGNALS = frozenset(
    {
        "grants",
        "external_location",
        # dbt_project.yml keys that change which code runs (`dispatch` reroutes
        # macro resolution to another package) or how dbt behaves project-wide.
        "dispatch",
        "flags",
        # A profiles.yml target: the adapter, role and credentials a build
        # connects as.
        "profile",
        # A .dex/config.yml key that changes what dex's own guards allow.
        "dex_config",
        # A read of the dbt child's environment, which is the agent's.
        "env_var",
    }
)

#: Signals that leave the verdict unknown: dex can see that the content depends
#: on something but not on what, so neither declarative nor a weaker class is a
#: claim it can make.
UNKNOWN_SIGNALS = frozenset({"env_var_computed"})

#: Jinja callees that name something the project already declares, rather than
#: running code of the repository's choosing. `doc` is here because a
#: `{{ doc('...') }}` in a description is the single most common jinja call in a
#: schema.yml and flagging it would make the signal useless.
_DECLARATIVE_CALLEES = frozenset(
    {"ref", "source", "var", "config", "this", "target", "doc"}
)

#: Hub, git, local, tarball and private package sources, keyed by the field
#: that names each in a packages.yml or dependencies.yml entry.
_DEPENDENCY_SOURCES = {
    "package": "dependency_hub",
    "git": "dependency_git",
    "local": "dependency_local",
    "tarball": "dependency_tarball",
    "private": "dependency_private",
}

#: Top-level dbt_project.yml keys that carry authority rather than declare.
_PROJECT_AUTHORITY_KEYS = ("dispatch", "flags")

#: Top-level .dex/config.yml keys that change what dex reads, connects to, or
#: allows: the budget and guards, the payload limits, the PII and blob
#: clearances, on-demand profiling, the connector, and the semantic host.
_DEX_CONFIG_AUTHORITY_KEYS = (
    "budget",
    "guards",
    "query",
    "pii_overrides",
    "blob_overrides",
    "auto_profile",
    "connector",
    "semantic",
)

#: Config keys that schedule execution, and the class each implies. Both the
#: hyphenated dbt spelling and the underscored jinja spelling appear in real
#: projects, and a leading `+` is how dbt_project.yml writes a config key.
_CONFIG_SIGNALS: dict[str, str] = {
    "pre-hook": "pre_hook",
    "pre_hook": "pre_hook",
    "post-hook": "post_hook",
    "post_hook": "post_hook",
    "on-run-start": "on_run_start",
    "on_run_start": "on_run_start",
    "on-run-end": "on_run_end",
    "on_run_end": "on_run_end",
    "grants": "grants",
    "location_root": "external_location",
    "external_location": "external_location",
    "operations": "run_operation",
}

_RUN_OPERATION = re.compile(r"\brun[-_]operation\b")
_PYTHON_MODEL = re.compile(r"^\s*def\s+model\s*\(", re.MULTILINE)
_SQL_STATEMENT = re.compile(
    r"^\s*(?:--[^\n]*\n|\s)*(?:with|select|\{\{|\{%)", re.IGNORECASE
)


class ArtifactSignal(BaseModel):
    """One reason the content was classified as it was.

    ``where`` is a YAML path (``semantic_models[0].config.post-hook``) or a line
    reference (``line 12``), whichever locates the finding in the file a reviewer
    will open. It is never the value itself: a hook's body is SQL the repository
    wrote, and echoing it into a payload would put repository-controlled text into
    a host's logs for no gain over naming where to look.
    """

    signal: str
    where: str
    detail: str | None = None


class ArtifactClassification(BaseModel):
    """What one edit's content contains.

    ``basis`` says what was read to reach the verdict, which is the field that
    keeps ``UNKNOWN`` honest: ``content`` means dex read the edit's own content,
    ``existing_content`` means it read the file a delete removes, and ``absent``
    means there was nothing to read at all. The three are different states and a
    host treating them alike is treating "I looked and found nothing" the same as
    "I could not look".
    """

    path: str
    artifact_class: ArtifactClass
    signals: list[ArtifactSignal] = Field(default_factory=list)
    basis: str = "content"
    parsed: bool = False

    def __getitem__(self, key: str) -> Any:
        if key in type(self).model_fields:
            return getattr(self, key)
        raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        return key in type(self).model_fields

    def get(self, key: str, default: Any = None) -> Any:
        if key in type(self).model_fields:
            return getattr(self, key)
        return default

    def data(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "artifact_class": self.artifact_class.value,
            "basis": self.basis,
            "parsed": self.parsed,
            "signals": [s.model_dump(exclude_none=True) for s in self.signals],
        }


def _jinja_signals(
    content: str, *, where_prefix: str = "", in_filter: bool = False
) -> list[ArtifactSignal]:
    """Every executable signal the jinja in ``content`` carries.

    A region with no call at all is still a signal (``jinja_expression``): the
    content's meaning depends on a value dex cannot see, which is the same problem
    for a host as a macro call and a worse one to leave silent.

    ``in_filter`` narrows the MetricFlow-callee exception to exactly the
    context that grammar is defined for: the value of a ``filter`` key. A
    repository macro that happens to be named ``Dimension`` and is called from
    anywhere else (a description, a config value) is still a macro the
    repository wrote, and reporting it as ``macro_call`` is the correct,
    unnarrowed answer there.
    """

    signals: list[ArtifactSignal] = []
    try:
        regions, _masked = jinja_regions(content)
    except Exception:
        return [
            ArtifactSignal(
                signal="jinja_expression",
                where=where_prefix or "content",
                detail="jinja present but could not be scanned",
            )
        ]

    for region in regions:
        where = (
            f"{where_prefix}line {region.line}"
            if where_prefix
            else f"line {region.line}"
        )
        callees = {call.callee for call in region.calls}
        if _RUN_OPERATION.search(region.body):
            signals.append(ArtifactSignal(signal="run_operation", where=where))
        for call in region.calls:
            if call.callee == "config":
                # Keyword arguments are not resolved by the scanner, so the
                # region body is read for the key names. Naming the key without
                # its value is the whole disclosure a host needs.
                for key, signal in _CONFIG_SIGNALS.items():
                    if re.search(
                        rf"\b{re.escape(key.replace('-', '_'))}\s*=", region.body
                    ):
                        signals.append(
                            ArtifactSignal(
                                signal=signal, where=where, detail=f"config({key})"
                            )
                        )
            elif call.callee == "run_query":
                signals.append(ArtifactSignal(signal="run_query", where=where))
            elif call.callee == "statement":
                signals.append(ArtifactSignal(signal="statement_block", where=where))
            elif in_filter and call.callee in metricflow_dialect.FILTER_CALLEES:
                # A metric filter's own grammar, not a macro the repository
                # wrote: `Dimension`/`TimeDimension`/`Entity` dispatch into the
                # semantic layer's resolution against definitions the project
                # already declares. Still reported, because a host applying
                # its own policy wants the reference even where it did not
                # decide the class.
                token = call.args[0] if call.args and call.args[0] else None
                signals.append(
                    ArtifactSignal(
                        signal="semantic_ref",
                        where=where,
                        detail=f"{call.callee}({token})" if token else call.callee,
                    )
                )
            elif call.callee == "env_var":
                # dbt renders jinja in YAML too, so this reads the dbt child's
                # environment into whatever the content renders into. The
                # variable is named, never its value; a computed name cannot be
                # named at all, so the verdict cannot be either.
                name = call.args[0] if call.args else None
                signals.append(
                    ArtifactSignal(signal="env_var", where=where, detail=name)
                    if name
                    else ArtifactSignal(
                        signal="env_var_computed",
                        where=where,
                        detail="variable name is not a literal",
                    )
                )
            elif call.callee not in _DECLARATIVE_CALLEES:
                signals.append(
                    ArtifactSignal(signal="macro_call", where=where, detail=call.callee)
                )
        if region.kind == "statement" and not callees:
            signals.append(ArtifactSignal(signal="jinja_statement", where=where))
        elif region.kind == "expression" and not callees:
            signals.append(ArtifactSignal(signal="jinja_expression", where=where))
    return signals


def _in_filter_clause(path: str) -> bool:
    """Whether ``path`` names the value of a ``filter`` key under a metric (or
    an item of a list under one): a metric's own filter, its measure's,
    ratio's, or an input metric's, and nothing wider.

    ``metrics[...]`` anchors this to where MetricFlow's filter grammar is
    actually defined. A ``filter`` key elsewhere, ``models[0].config.filter``
    for instance, names no such grammar: it is not MetricFlow's, dex does not
    know what it means, and treating it as one would narrow past what #445
    asks for.
    """

    if not path.startswith("metrics["):
        return False
    stripped = re.sub(r"\[\d+\]$", "", path)
    return stripped.endswith(".filter")


def _walk_yaml(node: Any, path: str, signals: list[ArtifactSignal]) -> None:
    """Collect signals from a parsed YAML document, tracking where each sits."""

    if isinstance(node, dict):
        for key, value in node.items():
            key_text = str(key)
            here = f"{path}.{key_text}" if path else key_text
            signal = _CONFIG_SIGNALS.get(key_text.lstrip("+"))
            if signal is not None:
                signals.append(ArtifactSignal(signal=signal, where=here))
            _walk_yaml(value, here, signals)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _walk_yaml(item, f"{path}[{i}]", signals)
    elif isinstance(node, str):
        if "{{" in node or "{%" in node:
            signals.extend(
                _jinja_signals(
                    node, where_prefix=f"{path}: ", in_filter=_in_filter_clause(path)
                )
            )
        elif _RUN_OPERATION.search(node):
            signals.append(ArtifactSignal(signal="run_operation", where=path))


def _document_signals(document: Any, signals: list[ArtifactSignal]) -> None:
    """Signals a document carries by its shape rather than by any one key.

    Read from the content, never the path: a dependency list, a profile, and a
    dex config are recognizable from what they hold, and a host classifying an
    edit before it lands cannot trust the filename to say which file it is.
    """

    if not isinstance(document, dict):
        return

    entries = document.get("packages")
    if isinstance(entries, list):
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            where = f"packages[{i}]"
            source = next((k for k in _DEPENDENCY_SOURCES if k in entry), None)
            if source is None:
                signals.append(ArtifactSignal(signal="dependency", where=where))
                continue
            detail = None
            if source == "package":
                # The package and its pin are the facts a host's policy turns
                # on. A git URL is not echoed: it can carry a token.
                version = entry.get("version")
                if isinstance(version, list):
                    version = ",".join(str(v) for v in version)
                detail = (
                    f"{entry.get('package')}@{version}"
                    if version
                    else (str(entry.get("package")))
                )
            signals.append(
                ArtifactSignal(
                    signal=_DEPENDENCY_SOURCES[source],
                    where=f"{where}.{source}",
                    detail=detail,
                )
            )

    signals.extend(
        ArtifactSignal(signal=key, where=key)
        for key in _PROJECT_AUTHORITY_KEYS
        if key in document
    )

    for key, value in document.items():
        if isinstance(value, dict) and isinstance(value.get("outputs"), dict):
            signals.append(
                ArtifactSignal(signal="profile", where=f"{key}.outputs", detail=key)
            )

    signals.extend(
        ArtifactSignal(signal="dex_config", where=key, detail=key)
        for key in _DEX_CONFIG_AUTHORITY_KEYS
        if key in document
    )


def _looks_like_delimited_data(content: str) -> bool:
    """A header row and at least one body row, every row the same width.

    Deliberately strict. Guessing "this is data" wrong in the permissive
    direction would classify a file dex failed to understand as inert values,
    which is the one mistake this module exists to avoid, so anything ragged,
    single-rowed, or single-columned falls through to UNKNOWN instead.
    """

    lines = [line for line in content.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    widths = {len(line.split(",")) for line in lines}
    return len(widths) == 1 and next(iter(widths)) > 1


def classify_content(
    content: str | None, *, path: str, basis: str = "content"
) -> ArtifactClassification:
    """Classify one piece of content. ``path`` locates it; it never decides.

    The decision order is content-shaped rather than kind-shaped: read the jinja,
    then try YAML as a *mapping* (a bare SQL statement parses as a YAML string,
    which is why a scalar is not a declaration), then fall back to the shapes a
    non-YAML file can honestly be shown to have.
    """

    if content is None:
        return ArtifactClassification(
            path=path,
            artifact_class=ArtifactClass.UNKNOWN,
            basis="absent",
            parsed=False,
        )

    signals: list[ArtifactSignal] = []
    parsed = False

    if _PYTHON_MODEL.search(content):
        signals.append(ArtifactSignal(signal="python_model", where="content"))

    document: Any = None
    try:
        document = yaml.safe_load(content)
        parsed = True
    except yaml.YAMLError:
        parsed = False

    if parsed and isinstance(document, (dict, list)):
        _document_signals(document, signals)
        _walk_yaml(document, "", signals)
        return _verdict(
            path, signals, basis, parsed=True, default=ArtifactClass.DECLARATIVE
        )

    # Not a declaration. Everything below reads the raw text, because a YAML
    # scalar and a parse failure are the same situation here: whatever this is,
    # it is not a structured document dex can walk.
    signals.extend(_jinja_signals(content))
    if _SQL_STATEMENT.match(content):
        signals.append(ArtifactSignal(signal="sql_statement", where="line 1"))
        return _verdict(
            path, signals, basis, parsed=False, default=ArtifactClass.EXECUTABLE
        )
    if signals:
        return _verdict(
            path, signals, basis, parsed=False, default=ArtifactClass.EXECUTABLE
        )
    if _looks_like_delimited_data(content):
        return ArtifactClassification(
            path=path, artifact_class=ArtifactClass.DATA, basis=basis, parsed=False
        )
    if not content.strip():
        # An empty file declares nothing and runs nothing. Reporting it as
        # declarative would be a claim; reporting it as unknown is the fact.
        return ArtifactClassification(
            path=path, artifact_class=ArtifactClass.UNKNOWN, basis=basis, parsed=parsed
        )
    return ArtifactClassification(
        path=path, artifact_class=ArtifactClass.UNKNOWN, basis=basis, parsed=parsed
    )


def _verdict(
    path: str,
    signals: list[ArtifactSignal],
    basis: str,
    *,
    parsed: bool,
    default: ArtifactClass,
) -> ArtifactClassification:
    """Execution outranks an unknown, which outranks authority; all three
    outrank the default.

    A document that both runs something and grants something is executable, and
    the grant stays in ``signals``. Reporting the weaker of two true findings as
    the verdict would understate what applying the change does. An unknown sits
    above authority because dex cannot rule out that the part it could not read
    is the stronger finding.
    """

    names = {s.signal for s in signals}
    if names & EXECUTABLE_SIGNALS:
        artifact_class = ArtifactClass.EXECUTABLE
    elif names & UNKNOWN_SIGNALS:
        artifact_class = ArtifactClass.UNKNOWN
    elif names & AUTHORITY_SIGNALS:
        artifact_class = ArtifactClass.AUTHORITY_BEARING
    else:
        artifact_class = default
    return ArtifactClassification(
        path=path,
        artifact_class=artifact_class,
        signals=signals,
        basis=basis,
        parsed=parsed,
    )


def classify_edit(
    edit: Edit, *, existing_content: str | None = None
) -> ArtifactClassification:
    """Classify one edit from what it will put on disk.

    A delete carries no content of its own, so it is classified from the file it
    removes where the caller can supply it, and reported as ``absent`` where it
    cannot. Removing executable content is itself a change to what runs, which is
    why a delete is classified at all rather than waved through.
    """

    if edit.op is EditOp.DELETE:
        return classify_content(
            existing_content, path=edit.path, basis="existing_content"
        )
    return classify_content(edit.new_content, path=edit.path, basis="content")
