"""Resolve identities for tool-generated and AI-authored commits."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

BOT_NAME = "✨❯ Lucky Lucy"
BOT_EMAIL = "claude._.ai._.code@luckydonald.de"
BOT_AUTHOR = f"{BOT_NAME} <{BOT_EMAIL}>"

ENV_NAME = "BASE_SPLIT_NAME"
ENV_EMAIL = "BASE_SPLIT_EMAIL"
CONFIG_NAME = "base.split.name"
CONFIG_EMAIL = "base.split.email"
LUCKYDONALD_EMAIL_SUFFIX = "@luckydonald.de"
AI_IDENTITY_MARKERS = ("claude", "codex", "copilot")


@dataclass(frozen=True)
class CommitIdentity:
    name: str
    email: str

    @property
    def author(self) -> str:
        return f"{self.name} <{self.email}>"
    # end def
# end class


DEFAULT_IDENTITY = CommitIdentity(BOT_NAME, BOT_EMAIL)


def read_git_config(key: str, cwd: Path) -> str | None:
    result = subprocess.run(
        ["git", "config", "--get", key],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    # end if
    value = result.stdout.strip()
    return value or None
# end def


def identity_with_default_name(name: str | None, email: str) -> CommitIdentity:
    return CommitIdentity((name or BOT_NAME).strip() or BOT_NAME, email.strip())
# end def


def direct_identity(
    cwd: Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> CommitIdentity | None:
    environment = os.environ if environ is None else environ
    environment_email = environment.get(ENV_EMAIL, "").strip()
    if environment_email:
        return identity_with_default_name(environment.get(ENV_NAME), environment_email)
    # end if

    config_email = read_git_config(CONFIG_EMAIL, cwd)
    if config_email:
        return identity_with_default_name(read_git_config(CONFIG_NAME, cwd), config_email)
    # end if
    return None
# end def


def is_ai_identity(commit_identity: CommitIdentity) -> bool:
    value = f"{commit_identity.name}\n{commit_identity.email}".casefold()
    return any(marker in value for marker in AI_IDENTITY_MARKERS)
# end def


def remaining_identity(
    author: CommitIdentity,
    committer: CommitIdentity,
) -> CommitIdentity | None:
    if author == committer:
        return None
    # end if
    for candidate in (author, committer):
        if not is_ai_identity(candidate):
            return candidate
        # end if
    # end for
    return None
# end def


def normal_git_identity(cwd: Path) -> CommitIdentity | None:
    email = read_git_config("user.email", cwd)
    if not email:
        return None
    # end if
    return identity_with_default_name(read_git_config("user.name", cwd), email)
# end def


def resolve_identity(
    cwd: Path,
    *,
    remaining: CommitIdentity | None = None,
    environ: Mapping[str, str] | None = None,
) -> CommitIdentity:
    configured = direct_identity(cwd, environ=environ)
    if configured is not None:
        return configured
    # end if

    git_identity = normal_git_identity(cwd)
    fallback_candidates = [candidate for candidate in (remaining, git_identity) if candidate is not None]
    if any(
        candidate.email.casefold().endswith(LUCKYDONALD_EMAIL_SUFFIX)
        for candidate in fallback_candidates
    ):
        return DEFAULT_IDENTITY
    # end if
    fallback = remaining or git_identity
    if fallback is None:
        return DEFAULT_IDENTITY
    # end if
    return fallback
# end def
