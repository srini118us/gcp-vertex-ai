"""Load the Delay Root Cause Skill as plain system prompt text.

Honest note on how the Skill is loaded. This reads SKILL.md (and any files
under reference/) from disk and returns their text so the caller can place it
in the Claude system prompt. It does NOT use native Claude Agent Skills or any
server side Skill execution. The Skill is instruction content only, which keeps
it reusable by any Claude based agent without coupling to this server.
"""
import os

DEFAULT_SKILL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "skills", "delay-root-cause"
)


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2].strip()
    return text


def load_skill(skill_dir: str = DEFAULT_SKILL_DIR) -> str:
    """Return the Skill body plus any reference material, as one prompt string."""
    skill_path = os.path.join(skill_dir, "SKILL.md")
    with open(skill_path, encoding="utf-8") as fh:
        body = _strip_frontmatter(fh.read())

    ref_path = os.path.join(skill_dir, "reference", "cause-codes.md")
    if os.path.exists(ref_path):
        with open(ref_path, encoding="utf-8") as fh:
            body += "\n\n# Reference: cause codes\n\n" + fh.read()
    return body
