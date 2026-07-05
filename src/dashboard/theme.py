"""Team-color palettes + shared UI helpers for the broadcast dashboard."""
from __future__ import annotations

import hashlib


# Curated team color palettes (primary + accent). Names match src/simulator/teams.py.
TEAM_PALETTES: dict[str, dict[str, str]] = {
    "Mumbai Mavericks":     {"primary": "#00a86b", "accent": "#1fd1a0", "text_on": "#ffffff"},
    "Chennai Chargers":     {"primary": "#f9a825", "accent": "#ffca28", "text_on": "#1a1a1a"},
    "Bengaluru Blazers":    {"primary": "#e53935", "accent": "#ef5350", "text_on": "#ffffff"},
    "Kolkata Kings":        {"primary": "#5e35b1", "accent": "#7e57c2", "text_on": "#ffffff"},
    "Delhi Dynamos":        {"primary": "#1e88e5", "accent": "#42a5f5", "text_on": "#ffffff"},
    "Hyderabad Hawks":      {"primary": "#ff7043", "accent": "#ffab91", "text_on": "#1a1a1a"},
    "Rajasthan Royals":     {"primary": "#ec407a", "accent": "#f48fb1", "text_on": "#ffffff"},
    "Punjab Panthers":      {"primary": "#d32f2f", "accent": "#e57373", "text_on": "#ffffff"},
    "Lucknow Lions":        {"primary": "#00acc1", "accent": "#26c6da", "text_on": "#ffffff"},
    "Gujarat Giants":       {"primary": "#455a64", "accent": "#78909c", "text_on": "#ffffff"},
}

# Fallback palette pool for unknown team names
_FALLBACK_POOL = [
    {"primary": "#13a87c", "accent": "#22c9a0", "text_on": "#ffffff"},
    {"primary": "#f59e0b", "accent": "#fbbf24", "text_on": "#1a1a1a"},
    {"primary": "#3b82f6", "accent": "#60a5fa", "text_on": "#ffffff"},
    {"primary": "#a855f7", "accent": "#c084fc", "text_on": "#ffffff"},
    {"primary": "#ef4444", "accent": "#f87171", "text_on": "#ffffff"},
]


def team_palette(name: str) -> dict[str, str]:
    """Return a stable color palette for any team name."""
    if name in TEAM_PALETTES:
        return TEAM_PALETTES[name]
    # deterministic pick from pool via name hash
    h = int(hashlib.md5(name.encode()).hexdigest(), 16)
    return _FALLBACK_POOL[h % len(_FALLBACK_POOL)]


def team_short(name: str) -> str:
    """Return a 3-letter uppercase code for a team name.

    Prefers first letters of each word:
        Mumbai Mavericks    -> MUM
        Chennai Chargers    -> CHE
        Delhi Dynamos       -> DEL
    Falls back to first 3 letters for single-word names.
    """
    words = name.split()
    if len(words) >= 2:
        return words[0][:3].upper()
    return name[:3].upper()
