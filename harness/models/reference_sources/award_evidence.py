"""Preserve the award level stated by an official listing, without promotion."""
import re


def award_evidence_kind(award):
    level = ' '.join(str(award or '').casefold().split())
    if re.search(r'\bfinalists?\b', level):
        return 'award_finalist'
    if re.search(r'\bshort\s?list(?:ed)?\b', level):
        return 'award_shortlist'
    if re.fullmatch(r'(?:grand prix|gold|silver|bronze|platinum)(?: award| winner)?|winner', level):
        return 'award_winner'
    return 'award_listing'
