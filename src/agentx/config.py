"""Central configuration. Every environment-dependent value enters here."""
import os
from dataclasses import dataclass

PROJECT_NAME = "AgentX"          # `make rename NAME=...` rewrites this tree
PROJECT_SLUG = "agentx"

FLASH = "gemini-3.5-flash"          # required: Gemini 3.5 or newer
PRO = "gemini-3.5-pro"              # supervisor adjudication only -- cost control
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
    tick_topic: str
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
            tick_topic=os.environ.get("TICK_TOPIC", "agentx-tick"),
            armor_template=os.environ.get("MODEL_ARMOR_TEMPLATE", ""),
            use_vertex=os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "true").lower() == "true",
        )


settings = Settings.from_env()

# Escalation ladder, in days remaining before the statutory deadline.
ESCALATION_LADDER = (14, 7, 2)
