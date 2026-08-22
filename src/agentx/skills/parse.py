"""Parse a skill folder into a normalized SkillPackage.

Deliberately tolerant: a hostile skill will not have well-formed frontmatter,
and refusing to parse it means refusing to scan it. Anything malformed becomes
a finding later rather than an exception here.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from .model import Origin, SkillFile, SkillPackage

_FRONTMATTER = "---"
_BINARY_SNIFF = 8192
IGNORED_DIRS = {".git", "__pycache__", ".DS_Store", "node_modules"}


def split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter, body). Never raises on malformed YAML."""
    if not text.startswith(_FRONTMATTER):
        return {}, text
    parts = text.split(_FRONTMATTER, 2)
    if len(parts) < 3:
        return {}, text
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}, text
    if not isinstance(meta, dict):
        return {}, parts[2]
    return meta, parts[2].lstrip("\n")


def _looks_binary(path: Path) -> bool:
    try:
        chunk = path.open("rb").read(_BINARY_SNIFF)
    except OSError:
        return False
    return b"\x00" in chunk


def parse_skill(root: Path, *, origin: Origin = Origin.COMMUNITY,
                source_ref: str = "") -> SkillPackage:
    root = Path(root)
    manifest_path = root / "SKILL.md"
    raw = manifest_path.read_text(encoding="utf-8", errors="replace") \
        if manifest_path.is_file() else ""
    meta, body = split_frontmatter(raw)

    files: list[SkillFile] = []
    hasher = hashlib.sha256()
    for p in sorted(root.rglob("*"), key=lambda x: str(x.relative_to(root))):
        if any(part in IGNORED_DIRS for part in p.parts):
            continue
        if p.is_symlink():
            # Recorded, never followed. A symlink out of the skill folder is
            # how a package reaches files it was never granted.
            files.append(SkillFile(path=str(p.relative_to(root)), size_bytes=0,
                                   is_symlink=True))
            hasher.update(f"symlink:{p.relative_to(root)}".encode())
            continue
        if not p.is_file():
            continue
        stat = p.stat()
        rel = str(p.relative_to(root))
        files.append(SkillFile(
            path=rel, size_bytes=stat.st_size,
            is_binary=_looks_binary(p),
            is_executable=bool(stat.st_mode & 0o111),
        ))
        hasher.update(rel.encode())
        hasher.update(p.read_bytes())

    return SkillPackage(
        name=str(meta.get("name") or root.name),
        description=str(meta.get("description") or ""),
        body=body,
        frontmatter=meta if isinstance(meta, dict) else {},
        files=files,
        content_hash=hasher.hexdigest(),
        origin=origin,
        source_ref=source_ref or str(root),
    )
