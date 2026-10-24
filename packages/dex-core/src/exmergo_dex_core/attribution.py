"""How a commit of what dex wrote credits dex as a co-author.

dex never commits: the agent or person driving it does. So the credit cannot be
written by the engine, only handed to whoever commits. `transform apply` reports
it, once it has written something, as a trailer for the commit message.

A forge credits a `Co-authored-by` trailer to the account that has the
trailer's email verified, so the email is the identity. On GitHub that is the
`exmergo-dex` user. A trailer is read only from a commit message's last
paragraph, so it goes after a blank line, with nothing after it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Contributor:
    """A name and the email a forge recognises the contributor's account by."""

    name: str
    email: str


DEX = Contributor(name="Dex", email="dex@exmergo.com")


def co_author_trailer(contributor: Contributor) -> str:
    return f"Co-authored-by: {contributor.name} <{contributor.email}>"


#: The trailer a commit of files dex wrote ends with.
COMMIT_TRAILER = co_author_trailer(DEX)
