"""Contracts for the capability gate.

A "skill" is a folder holding a SKILL.md plus optional scripts, references, and
assets -- the Agent Skills format, originally released by Anthropic and now read
by roughly 45 runtimes. That portability is the point and the problem: the same
folder is loaded by agents with wildly different permission models, and nothing
in the format carries provenance or a signature.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class Origin(str, Enum):
    """Where a skill came from. Drives policy -- see policy.py."""

    BUILTIN = "builtin"                  # ships with the runtime
    TRUSTED_REPO = "trusted_repo"        # an explicitly allow-listed publisher
    COMMUNITY = "community"              # a public marketplace
    CROSS_RUNTIME = "cross_runtime"      # imported from another agent runtime
    AGENT_AUTHORED = "agent_authored"    # the agent wrote this for itself


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Category(str, Enum):
    EXFILTRATION = "exfiltration"
    INJECTION = "injection"
    DESTRUCTIVE = "destructive"
    PERSISTENCE = "persistence"
    OBFUSCATION = "obfuscation"
    STRUCTURE = "structure"
    INTENT_MISMATCH = "intent_mismatch"


class Verdict(str, Enum):
    SAFE = "safe"
    CAUTION = "caution"
    DANGEROUS = "dangerous"


class Decision(str, Enum):
    APPROVE = "approve"
    QUARANTINE = "quarantine"
    REJECT = "reject"


class Finding(BaseModel):
    reviewer: str
    category: Category
    severity: Severity
    summary: str
    evidence: str = Field(default="", description="The offending text, truncated")
    file: str = "SKILL.md"
    line: int | None = None


class SkillFile(BaseModel):
    path: str
    size_bytes: int
    is_binary: bool = False
    is_symlink: bool = False
    is_executable: bool = False


class SkillPackage(BaseModel):
    """A parsed skill, normalized so every reviewer sees the same shape."""

    name: str
    description: str
    body: str = Field(description="SKILL.md below the frontmatter")
    frontmatter: dict = Field(default_factory=dict)
    files: list[SkillFile] = Field(default_factory=list)
    content_hash: str = Field(description="sha256 over every file, order-stable")
    origin: Origin = Origin.COMMUNITY
    source_ref: str = ""

    @property
    def total_bytes(self) -> int:
        return sum(f.size_bytes for f in self.files)


class ReviewerResult(BaseModel):
    reviewer: str
    ok: bool = True
    findings: list[Finding] = Field(default_factory=list)
    note: str = ""

    @property
    def verdict(self) -> Verdict:
        if any(f.severity in (Severity.CRITICAL, Severity.HIGH) for f in self.findings):
            return Verdict.DANGEROUS
        if self.findings:
            return Verdict.CAUTION
        return Verdict.SAFE


class ScanReport(BaseModel):
    skill_name: str
    content_hash: str
    origin: Origin
    verdict: Verdict
    decision: Decision
    reasoning: str
    results: list[ReviewerResult] = Field(default_factory=list)
    scanned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def findings(self) -> list[Finding]:
        return [f for r in self.results for f in r.findings]
