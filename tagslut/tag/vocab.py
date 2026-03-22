from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from tagslut.library.models import VocabAlias, VocabTerm

DJ_DOMAINS = frozenset({"genre", "energy", "role", "familiarity", "workflow"})


def normalize_to_vocab(domain: str, raw_value: str, session: Session) -> str | None:
    normalized_domain = domain.strip().casefold()
    normalized_value = raw_value.strip().casefold()
    if not normalized_domain or not normalized_value:
        return None
    if normalized_domain not in DJ_DOMAINS:
        return None

    direct = session.scalar(
        select(VocabTerm.canonical_value).where(
            VocabTerm.domain == normalized_domain,
            VocabTerm.canonical_value == raw_value,
        )
    )
    if direct is not None:
        return str(direct)

    alias_value = session.scalar(
        select(VocabTerm.canonical_value)
        .join(VocabAlias, VocabAlias.vocab_term_id == VocabTerm.id)
        .where(
            VocabTerm.domain == normalized_domain,
            VocabAlias.alias == raw_value,
        )
    )
    if alias_value is not None:
        return str(alias_value)

    direct_folded = session.scalar(
        select(VocabTerm.canonical_value).where(
            VocabTerm.domain == normalized_domain,
            VocabTerm.canonical_value.ilike(raw_value),
        )
    )
    if direct_folded is not None:
        return str(direct_folded)

    alias_folded = session.scalar(
        select(VocabTerm.canonical_value)
        .join(VocabAlias, VocabAlias.vocab_term_id == VocabTerm.id)
        .where(
            VocabTerm.domain == normalized_domain,
            VocabAlias.alias.ilike(raw_value),
        )
    )
    if alias_folded is not None:
        return str(alias_folded)

    return None
