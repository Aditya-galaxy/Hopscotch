"""The capability gate.

Two properties are load-bearing and both are tested here:

  1. It does not flag benign skills. A gate with false positives gets disabled
     by the humans it was built to help, which is worse than no gate.
  2. Self-authored capability is held to the STRICTEST standard, not the
     loosest. That inverts what shipping runtimes currently do and it is the
     project's actual argument, so it gets an explicit test.
"""
from pathlib import Path

import pytest

from hopscotch.skills import Decision, Origin, TrustPolicy, parse_skill, review
from hopscotch.skills.gate import worst
from hopscotch.skills.model import Verdict
from hopscotch.skills.parse import split_frontmatter
from hopscotch.skills.reviewers import StructuralReviewer

STRUCTURAL_ONLY = [StructuralReviewer()]
CORPUS = Path("data/corpora/mattpocock-skills")


def write_skill(root: Path, name: str, description: str, body: str = "Do the thing.") -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n\n{body}\n"
    )
    return d


# --- parsing -----------------------------------------------------------------

def test_frontmatter_splits():
    meta, body = split_frontmatter("---\nname: x\ndescription: y\n---\n\n# Hi\n")
    assert meta == {"name": "x", "description": "y"}
    assert body.startswith("# Hi")


def test_malformed_frontmatter_does_not_raise():
    # A hostile skill will not be well-formed. Refusing to parse means refusing
    # to scan, which is the outcome an attacker wants.
    meta, body = split_frontmatter("---\n:::not: [valid: yaml\n---\nbody")
    assert meta == {}
    assert "body" in body


def test_hash_is_stable_and_content_sensitive(tmp_path):
    a = parse_skill(write_skill(tmp_path / "1", "s", "d"))
    b = parse_skill(write_skill(tmp_path / "2", "s", "d"))
    c = parse_skill(write_skill(tmp_path / "3", "s", "d", body="Something else."))
    assert a.content_hash == b.content_hash
    assert a.content_hash != c.content_hash


# --- false positives ---------------------------------------------------------

def test_ordinary_skill_is_clean(tmp_path):
    pkg = parse_skill(write_skill(
        tmp_path, "setup-pre-commit",
        "Set up Husky pre-commit hooks with lint-staged in the current repo.",
        body="Install husky as a devDependency, then add a .husky/pre-commit hook "
             "that runs lint-staged, typecheck, and tests.",
    ))
    report = review(pkg, reviewers=STRUCTURAL_ONLY, require_all=False)
    assert report.verdict is Verdict.SAFE
    assert report.decision is Decision.APPROVE


@pytest.mark.skipif(not CORPUS.exists(), reason="run scripts/fetch_corpora.sh")
def test_real_benign_corpus_passes_clean():
    """36 real skills people actually use. Structural review must not flag them."""
    flagged = []
    for manifest in sorted(CORPUS.rglob("SKILL.md")):
        pkg = parse_skill(manifest.parent, origin=Origin.COMMUNITY)
        report = review(pkg, reviewers=STRUCTURAL_ONLY, require_all=False)
        if report.decision is not Decision.APPROVE:
            flagged.append((pkg.name, report.reasoning))
    assert not flagged, f"false positives on benign corpus: {flagged}"


# --- hostile shapes ----------------------------------------------------------

def test_padding_is_itself_the_finding(tmp_path):
    """ClawHavoc padded a README to 22MB to push past scanner thresholds.

    The answer is not a bigger threshold. A skill that size IS the signal.
    """
    d = write_skill(tmp_path, "padded-helper", "Helpful utilities.")
    (d / "README.md").write_text("A" * (2 * 1024 * 1024))
    report = review(parse_skill(d), reviewers=STRUCTURAL_ONLY, require_all=False)
    assert report.decision is Decision.REJECT
    assert any(f.category.value == "obfuscation" for f in report.findings)


def test_symlink_escape_is_critical(tmp_path):
    d = write_skill(tmp_path, "notes-helper", "Organize your notes.")
    (d / "creds").symlink_to(tmp_path / "outside.txt")
    report = review(parse_skill(d), reviewers=STRUCTURAL_ONLY, require_all=False)
    assert report.decision is Decision.REJECT
    assert any(f.severity.value == "critical" for f in report.findings)


# --- the argument ------------------------------------------------------------

def test_self_authored_is_strictest_not_loosest(tmp_path):
    """Identical bytes. The only difference is who wrote it.

    Shipping runtimes install agent-authored skills more permissively than
    downloaded ones. A community skill at least had a human author who could be
    named; a self-authored one may encode a web page the model read minutes
    earlier, reviewed by nobody.
    """
    d = write_skill(tmp_path, "web-research-helper", "Summarize pages you fetch.")
    clean = parse_skill(d)

    downloaded = review(clean.model_copy(update={"origin": Origin.COMMUNITY}),
                        reviewers=STRUCTURAL_ONLY, require_all=False)
    self_written = review(clean.model_copy(update={"origin": Origin.AGENT_AUTHORED}),
                          reviewers=STRUCTURAL_ONLY, require_all=False)

    assert downloaded.decision is Decision.APPROVE
    assert self_written.decision is Decision.QUARANTINE, (
        "a skill the agent wrote for itself must not auto-install just because "
        "it scanned clean"
    )


def test_cross_runtime_import_is_treated_as_unreviewed(tmp_path):
    """Hermes imports OpenClaw skills. Passing another runtime's policy, under a
    threat model we cannot see, is not the same as passing ours."""
    pkg = parse_skill(write_skill(tmp_path, "imported", "Imported capability."))
    report = review(pkg.model_copy(update={"origin": Origin.CROSS_RUNTIME}),
                    reviewers=STRUCTURAL_ONLY, require_all=False)
    assert report.decision is Decision.QUARANTINE


# --- fail closed -------------------------------------------------------------

def test_unavailable_reviewer_downgrades_instead_of_approving(tmp_path):
    """"We could not check" must never resolve to "we checked and it is fine"."""
    pkg = parse_skill(write_skill(tmp_path, "ok-skill", "A perfectly fine skill."))
    report = review(pkg, require_all=True)          # real reviewers, not yet wired
    assert report.decision is Decision.QUARANTINE
    assert "could not run" in report.reasoning
    assert any(not r.ok for r in report.results)


def test_policy_is_data_not_code(tmp_path):
    """A compromised publisher gets demoted at 3am without shipping a build."""
    policy = TrustPolicy(trusted_publishers={"anthropics/skills"})
    assert policy.classify("anthropics/skills") is Origin.TRUSTED_REPO
    policy.demote("anthropics/skills")
    assert policy.classify("anthropics/skills") is Origin.COMMUNITY


def test_worst_verdict_wins():
    assert worst([Verdict.SAFE, Verdict.DANGEROUS, Verdict.CAUTION]) is Verdict.DANGEROUS
    assert worst([]) is Verdict.SAFE
