"""Keyword-matched rule loading for Neural Pipeline.

Rules live in phase rule folders (manager/rules/ and workers/rules/).
Each rule has YAML frontmatter with keywords and a score. Rules are
loaded into agent context only when their keywords match the current
task content, keeping context lean.
"""
import re
from pathlib import Path
from typing import Any


def parse_rule(path: Path) -> dict[str, Any] | None:
    """Parse a rule file into structured data.

    Returns dict with keys: path, id, keywords, enabled, score, history, body.
    Returns None if the file can't be parsed or is disabled.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None

    frontmatter, body = _split_frontmatter(text)
    if frontmatter is None:
        # No frontmatter -- treat the whole file as a rule with no keywords
        return {
            "path": path,
            "id": path.stem,
            "keywords": [],
            "enabled": True,
            "score": 0,
            "history": {"loaded": 0, "successes": 0, "failures": 0, "last_scored": None},
            "body": text.strip(),
        }

    if not frontmatter.get("enabled", True):
        return None

    return {
        "path": path,
        "id": frontmatter.get("id", path.stem),
        "keywords": frontmatter.get("keywords", []),
        "enabled": True,
        "score": frontmatter.get("score", 0),
        "history": frontmatter.get("history", {
            "loaded": 0, "successes": 0, "failures": 0, "last_scored": None,
        }),
        "body": body.strip(),
    }


def load_rules(rules_dir: Path) -> list[dict[str, Any]]:
    """Load all enabled rules from a directory."""
    if not rules_dir.is_dir():
        return []
    rules = []
    for f in sorted(rules_dir.glob("*.md")):
        rule = parse_rule(f)
        if rule is not None:
            rules.append(rule)
    return rules


def match_rules(
    rules: list[dict[str, Any]],
    task_text: str,
    min_score: float = -5.0,
) -> list[dict[str, Any]]:
    """Return rules whose keywords match the task text.

    Rules with no keywords always match (global rules).
    Rules below min_score are excluded (too harmful).
    Returned list is sorted by score descending (best rules first).
    """
    task_lower = task_text.lower()
    matched = []

    for rule in rules:
        if rule["score"] < min_score:
            continue

        keywords = rule["keywords"]
        if not keywords:
            # Global rule -- always matches
            matched.append(rule)
            continue

        # Match if any keyword appears in the task text
        for kw in keywords:
            if kw.lower() in task_lower:
                matched.append(rule)
                break

    return sorted(matched, key=lambda r: r["score"], reverse=True)


def load_matched_rules(rules_dir: Path, task_text: str) -> list[dict[str, Any]]:
    """Load rules and return only those matching the task text."""
    all_rules = load_rules(rules_dir)
    return match_rules(all_rules, task_text)


def format_rules_for_context(rules: list[dict[str, Any]]) -> str:
    """Format matched rules as text for injection into agent context."""
    if not rules:
        return ""
    parts = ["## Loaded Rules\n"]
    for rule in rules:
        score_str = f"(score: {rule['score']:+d})" if rule["score"] != 0 else ""
        parts.append(f"### {rule['id']} {score_str}\n{rule['body']}\n")
    return "\n".join(parts)


def update_rule_score(path: Path, delta: int) -> bool:
    """Update a rule's score by delta, clamped to [-5, +5].

    Returns True if successful.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return False

    frontmatter, body = _split_frontmatter(text)
    if frontmatter is None:
        return False

    old_score = frontmatter.get("score", 0)
    new_score = max(-5, min(5, old_score + delta))
    frontmatter["score"] = new_score

    # Update loaded count
    history = frontmatter.get("history", {})
    history["loaded"] = history.get("loaded", 0) + 1
    if delta > 0:
        history["successes"] = history.get("successes", 0) + 1
    elif delta < 0:
        history["failures"] = history.get("failures", 0) + 1
    frontmatter["history"] = history

    # Rebuild the file
    new_text = _build_frontmatter(frontmatter) + "\n" + body
    path.write_text(new_text, encoding="utf-8")
    return True


# -- Frontmatter Parsing --

_FM_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _split_frontmatter(text: str) -> tuple[dict | None, str]:
    """Split YAML frontmatter from body. Returns (frontmatter_dict, body)."""
    m = _FM_PATTERN.match(text)
    if not m:
        return None, text

    import yaml
    try:
        fm = yaml.safe_load(m.group(1))
    except Exception:
        return None, text

    body = text[m.end():]
    return fm or {}, body


def _build_frontmatter(data: dict) -> str:
    """Serialize a dict back to YAML frontmatter block."""
    import yaml
    fm_str = yaml.dump(data, default_flow_style=False, sort_keys=False).strip()
    return f"---\n{fm_str}\n---\n"
