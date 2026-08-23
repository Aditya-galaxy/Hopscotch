"""Every third-party import in src/ must be declared in requirements.txt.

This exists because the same bug shipped three times: google-cloud-aiplatform,
then google-cloud-texttospeech, each installed locally and each missing from
requirements. Both worked perfectly on my machine and failed inside the
container -- once silently, until the swallowed exception was logged.

A missing dependency is not a subtle failure, but it IS invisible until the
code path runs in the environment that lacks it, and some of these paths only
run on an escalation.
"""
import ast
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
REQS = Path(__file__).resolve().parents[1] / "requirements.txt"

# Namespace packages and transitive deps every google-cloud-* package pulls in.
# Declaring these directly would pin versions we do not control.
PROVIDED_TRANSITIVELY = {
    "google", "google.cloud", "google.auth", "google.protobuf",
}

# import name -> distribution name, where they differ
DISTRIBUTION = {
    "google.adk": "google-adk",
    "google.genai": "google-genai",
    "google.cloud.firestore": "google-cloud-firestore",
    "google.cloud.aiplatform": "google-cloud-aiplatform",
    "google.cloud.modelarmor_v1": "google-cloud-modelarmor",
    "google.cloud.texttospeech": "google-cloud-texttospeech",
    "google.cloud.storage": "google-cloud-storage",
    "google.api_core": "google-api-core",
    "opentelemetry": "opentelemetry-sdk",
    "yaml": "pyyaml",
    "pydantic": "pydantic",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "vertexai": "google-cloud-aiplatform",
}


def declared() -> set[str]:
    text = REQS.read_text().lower()
    return {re.split(r"[<>=\[]", line.strip())[0]
            for line in text.splitlines()
            if line.strip() and not line.startswith("#")}


def imported() -> set[str]:
    found: set[str] = set()
    for py in SRC.rglob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.add(node.module)
    return found


def test_every_third_party_import_is_declared():
    declared_dists = declared()
    missing = []
    for mod in sorted(imported()):
        top = mod.split(".")[0]
        if top in sys.stdlib_module_names or top == "hopscotch":
            continue
        if any(mod == p or mod.startswith(p + ".") for p in PROVIDED_TRANSITIVELY) \
                and not any(mod.startswith(k) for k in DISTRIBUTION):
            continue
        dist = next((d for prefix, d in DISTRIBUTION.items()
                     if mod == prefix or mod.startswith(prefix + ".")), None)
        if dist is None:
            dist = top.replace("_", "-")
        if dist.lower() not in declared_dists:
            missing.append(f"{mod} -> needs '{dist}' in requirements.txt")
    assert not missing, "undeclared dependencies:\n  " + "\n  ".join(missing)
