# The hosted semantic layer token goes to dbt Cloud and nowhere else.
#
# The host can come from .dex/config.yml, which a cloned repository, a fork or a
# pull request writes, and the token never does: it is the user's, from
# DBT_SL_TOKEN, ~/.dbt/dbt_cloud.yml or a host-supplied source. These tests hold
# the binding between the two. Every refusal is checked for two things: nothing
# was posted, and no token source was read, since a token read for a host that was
# always going to be refused is a token one bug away from being sent.

from __future__ import annotations

from typing import ClassVar

import pytest

from exmergo_dex_core import SemanticSource
from exmergo_dex_core.config import DexConfig, QueryLimits
from exmergo_dex_core.engine import DexEngine
from exmergo_dex_core.explore import semantic as sem
from exmergo_dex_core.explore.semantic.hosted import HostedDbtCloudBackend
from exmergo_dex_core.explore.semantic.hosted_transport import post_graphql
from exmergo_dex_core.semantic_hosts import check_semantic_layer_host
from exmergo_dex_core.storage import MemoryStore

HOSTILE_HOSTS = [
    "attacker.example",
    "evildbt.com",
    "evilgetdbt.com",
    "sl.cloud.getdbt.com.evil.example",
    "evil.example/x?",
    "evil.example#sl.cloud.getdbt.com",
    "u@sl.cloud.getdbt.com",
    "sl.cloud.getdbt.com:8443",
    "localhost",
    "127.0.0.1",
    "https://sl.cloud.getdbt.com",
    "sl.cloud.getdbt.com/api/graphql?",
    "sl.cloud.getdbt.com evil.example",
    "",
]

DBT_HOSTS = [
    "sl.cloud.getdbt.com",
    "SL.Cloud.GetDBT.com.",
    "  semantic-layer.cloud.getdbt.com  ",
    "ab123.semantic-layer.us1.dbt.com",
    "getdbt.com",
]


class _Client:
    posted: ClassVar[list[dict]] = []

    def __init__(self, **_kwargs) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False

    def post(self, url, *, headers, json):
        _Client.posted.append({"url": url, "headers": headers, "body": json})
        return _Response()


class _Response:
    status_code = 200

    @staticmethod
    def json() -> dict:
        return {"data": {"metrics": []}}


@pytest.fixture
def wire(monkeypatch):
    pytest.importorskip("httpx")
    import httpx

    _Client.posted = []
    monkeypatch.setattr(httpx, "Client", _Client)
    return _Client


@pytest.fixture
def tripwire_tokens(monkeypatch, tmp_path):
    """Every ambient token source, armed: reading any of them fails the test."""

    import exmergo_dex_core.connect as connect

    class _Tripwire(dict):
        def get(self, key, default=None):
            if key == "DBT_SL_TOKEN":
                raise AssertionError("DBT_SL_TOKEN was read for a refused host")
            return super().get(key, default)

    def _no_file_read(_env):
        raise AssertionError("~/.dbt/dbt_cloud.yml was read for a refused host")

    monkeypatch.setattr(connect, "_dbt_cloud_service_token", _no_file_read)
    monkeypatch.delenv("DBT_SL_HOST", raising=False)
    monkeypatch.delenv("DBT_SL_ENV_ID", raising=False)
    monkeypatch.delenv("DEX_SL_ALLOWED_HOSTS", raising=False)
    monkeypatch.setenv("DBT_SL_TOKEN", "ambient-token")
    return _Tripwire


def _config(host: str) -> DexConfig:
    return DexConfig(
        semantic={"backend": "dbt_cloud", "host": host, "environment_id": "42"}
    )


def _engine(config: DexConfig, **kwargs) -> DexEngine:
    return DexEngine(config=config, store=MemoryStore(), **kwargs)


@pytest.mark.parametrize("host", HOSTILE_HOSTS)
def test_a_repository_host_never_receives_the_token(host, wire, tripwire_tokens):
    """GHSA-28xv: `semantic.host` in .dex/config.yml pointing anywhere but dbt
    Cloud is refused, naming the host, before a token is read or a byte is sent."""

    from exmergo_dex_core.connect import (
        CredentialDiscoveryError,
        resolve_semantic_layer_connection,
    )

    with pytest.raises(CredentialDiscoveryError) as exc:
        resolve_semantic_layer_connection(
            _config(host).semantic, tripwire_tokens({"DBT_SL_TOKEN": "x"})
        )
    if host.strip():
        assert host.strip().lower().rstrip(".")[:40] in str(exc.value).lower()
    assert not wire.posted


@pytest.mark.parametrize("host", HOSTILE_HOSTS)
def test_the_engine_refuses_a_hostile_host_end_to_end(host, wire, tripwire_tokens):
    with pytest.raises(sem.SemanticBackendError):
        sem.resolve_backend(_engine(_config(host))).list_definitions()
    assert not wire.posted


@pytest.mark.parametrize("host", ["attacker.example", "evildbt.com"])
def test_dbt_sl_host_is_held_to_the_same_rule(host, wire, tripwire_tokens, monkeypatch):
    monkeypatch.setenv("DBT_SL_HOST", host)
    with pytest.raises(sem.SemanticBackendError, match="refusing to send"):
        sem.resolve_backend(_engine(_config("sl.cloud.getdbt.com")))
    assert not wire.posted


@pytest.mark.parametrize("host", HOSTILE_HOSTS)
def test_a_supplied_source_is_not_called_for_a_hostile_host(host, wire):
    """The `source=` path is safe only if the embedding host controls the config,
    so the config's host is checked there too, before the token callable runs."""

    def token() -> str:
        raise AssertionError("the token callable ran for a refused host")

    engine = _engine(_config(host), semantic_source=SemanticSource(token=token))
    with pytest.raises(sem.SemanticBackendError):
        sem.resolve_backend(engine)
    assert not wire.posted


@pytest.mark.parametrize("host", DBT_HOSTS)
def test_dbt_cloud_hosts_still_work(host, wire, monkeypatch):
    monkeypatch.delenv("DBT_SL_HOST", raising=False)
    monkeypatch.delenv("DBT_SL_ENV_ID", raising=False)
    monkeypatch.setenv("DBT_SL_TOKEN", "tok")
    sem.resolve_backend(_engine(_config(host))).list_definitions()
    expected = host.strip().lower().rstrip(".")
    assert wire.posted[0]["url"] == f"https://{expected}/api/graphql"
    assert wire.posted[0]["headers"]["Authorization"] == "Bearer tok"


def test_the_environment_may_name_an_exact_private_host(wire, monkeypatch):
    monkeypatch.delenv("DBT_SL_HOST", raising=False)
    monkeypatch.delenv("DBT_SL_ENV_ID", raising=False)
    monkeypatch.setenv("DBT_SL_TOKEN", "tok")
    monkeypatch.setenv("DEX_SL_ALLOWED_HOSTS", "other.example, sl.private.corp")
    sem.resolve_backend(_engine(_config("SL.Private.Corp"))).list_definitions()
    assert wire.posted[0]["url"] == "https://sl.private.corp/api/graphql"


def test_an_allowed_host_is_exact_not_a_suffix(wire, tripwire_tokens, monkeypatch):
    monkeypatch.setenv("DEX_SL_ALLOWED_HOSTS", "private.corp")
    with pytest.raises(sem.SemanticBackendError, match="refusing to send"):
        sem.resolve_backend(_engine(_config("sl.private.corp")))
    assert not wire.posted


def test_a_supplied_source_may_name_an_exact_private_host(wire, monkeypatch):
    # And only the source's list counts: the ambient one is not read on this path.
    monkeypatch.setenv("DEX_SL_ALLOWED_HOSTS", "ambient.corp")
    source = SemanticSource(token=lambda: "tok", allowed_hosts=("sl.private.corp",))
    sem.resolve_backend(
        _engine(_config("sl.private.corp"), semantic_source=source)
    ).list_definitions()
    assert wire.posted[0]["url"] == "https://sl.private.corp/api/graphql"

    ambient = _engine(_config("ambient.corp"), semantic_source=source)
    with pytest.raises(sem.SemanticBackendError, match="refusing to send"):
        sem.resolve_backend(ambient)


def test_config_cannot_widen_the_allowlist():
    """There is no config key for it, and an unknown one does nothing."""

    from exmergo_dex_core.config import SemanticConfig

    assert "allowed_hosts" not in SemanticConfig.model_fields


def test_the_backend_constructor_checks_the_host_itself():
    with pytest.raises(sem.SemanticBackendError, match="refusing to send"):
        HostedDbtCloudBackend("attacker.example", "42", "tok", QueryLimits())


@pytest.mark.parametrize(
    "url",
    [
        "https://attacker.example/api/graphql",
        "http://sl.cloud.getdbt.com/api/graphql",
        "https://sl.cloud.getdbt.com:8443/api/graphql",
        "https://u:p@sl.cloud.getdbt.com/api/graphql",
        "https://sl.cloud.getdbt.com/other",
        "https://sl.cloud.getdbt.com/api/graphql?next=attacker.example",
    ],
)
def test_the_transport_refuses_any_other_url(url, wire):
    with pytest.raises(sem.SemanticBackendError):
        post_graphql(url=url, token="tok", timeout=1.0, query="{ x }")  # noqa: S106
    assert not wire.posted


def test_check_returns_the_normalized_host():
    assert check_semantic_layer_host(" SL.cloud.getdbt.COM. ") == "sl.cloud.getdbt.com"


def test_the_dbt_cloud_file_never_falls_back_to_another_project(tmp_path, monkeypatch):
    """GHSA-28xv, second review: when the active project has no token, the first
    project holding one may belong to a dbt Cloud account the user never pointed
    dex at. That is a refusal, not a fallback."""

    from exmergo_dex_core.connect import (
        CredentialDiscoveryError,
        resolve_semantic_layer_connection,
    )

    (tmp_path / "dbt_cloud.yml").write_text(
        "context:\n  active-project: '1'\n"
        "projects:\n"
        "  - project-id: '1'\n"
        "  - project-id: '2'\n    token-value: other-accounts-token\n",
        encoding="utf-8",
    )
    env = {"DBT_CLOUD_CONFIG_DIR": str(tmp_path)}
    with pytest.raises(CredentialDiscoveryError, match="active project"):
        resolve_semantic_layer_connection(_config("sl.cloud.getdbt.com").semantic, env)

    (tmp_path / "dbt_cloud.yml").write_text(
        "context:\n  active-project: '2'\n"
        "projects:\n"
        "  - project-id: '2'\n    token-value: active-token\n",
        encoding="utf-8",
    )
    _host, _env, token, _kind = resolve_semantic_layer_connection(
        _config("sl.cloud.getdbt.com").semantic, env
    )
    assert token == "active-token"  # noqa: S105 (a test fixture, not a secret)
