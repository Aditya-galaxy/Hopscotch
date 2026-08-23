"""Central configuration. Every environment-dependent value enters here."""
import os
from dataclasses import dataclass

PROJECT_NAME = "Hopscotch"          # `make rename NAME=...` rewrites this tree
PROJECT_SLUG = "hopscotch"

FLASH = "gemini-3.5-flash"          # workers
# Supervisor tier. NOT a "pro" model: no pro-tier model at or above Gemini 3.5
# is available in this project -- 2.5-pro and 3.1-pro-preview both respond but
# are below the version floor this project targets. So the supervisor gets the
# NEWEST model instead of the largest one, which is a real tier difference and
# an honest one.
SUPERVISOR = "gemini-3.7-flash"
GEMMA = "gemma-4-26b-a4b-it-maas"   # triage + redaction; global endpoint only


@dataclass(frozen=True)
class Settings:
    project_id: str
    location: str
    armor_location: str
    agent_engine_id: str
    firestore_db: str
    cases_collection: str
    deadletter_collection: str
    audit_collection: str
    armor_template: str
    use_vertex: bool

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            project_id=os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
            # GOOGLE_CLOUD_LOCATION is the MODEL location and defaults to
            # `global`, because Gemini 3.x and Gemma publisher models are served
            # only from the global endpoint -- a regional call 404s even though
            # models.list() reports the model as present in that region. ADK
            # builds its own client from this variable, so it has to be the
            # model location or every agent call fails.
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
            # Model Armor is genuinely regional and has no global endpoint, so
            # it carries its own setting rather than inheriting the above.
            armor_location=os.environ.get("MODEL_ARMOR_LOCATION", "us-central1"),
            # Vertex AI Agent Engine instance that hosts Memory Bank and
            # sessions. Created once by deploy/create_agent_engine.sh.
            agent_engine_id=os.environ.get("AGENT_ENGINE_ID", ""),
            firestore_db=os.environ.get("FIRESTORE_DATABASE", "(default)"),
            cases_collection=os.environ.get("CASES_COLLECTION", "cases"),
            deadletter_collection=os.environ.get("DEADLETTER_COLLECTION", "deadletter"),
            audit_collection=os.environ.get("AUDIT_COLLECTION", "audit"),
            armor_template=os.environ.get("MODEL_ARMOR_TEMPLATE", ""),
            # ADK reads this raw env var ITSELF to decide Vertex vs the Gemini
            # Developer API, and its default is NOT ours. Setting our default to
            # true here does nothing for ADK -- the variable has to be present in
            # the environment. It worked locally because the shell exported it and
            # failed in the container, which is the whole shape of the bug.
            use_vertex=os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "true").lower() == "true",
        )


settings = Settings.from_env()

# Escalation ladder, in days remaining before the statutory deadline.
ESCALATION_LADDER = (14, 7, 2)
