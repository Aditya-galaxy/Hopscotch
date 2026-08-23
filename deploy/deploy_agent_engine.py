"""Deploy the supervisor to Vertex AI Agent Engine Runtime.

Everything else runs on Cloud Run Jobs, which is right for a scheduled sweep: it
wakes, works, and scales to zero. Agent Engine Runtime is a different shape -- a
managed, always-addressable agent you query -- and it suits the one agent that
answers a question rather than performing a pass.

WHY THE AGENT IS DEFINED IN THIS FILE rather than imported from the package:
agent_engines.create() ships the agent by cloudpickle, and cloudpickle
serialises classes defined in __main__ BY VALUE while importing everything else
BY REFERENCE. An agent that imports `hopscotch.schemas` therefore needs the whole
package present remotely -- which failed twice with ModuleNotFoundError before
this was obvious. Defining the schema and the agent here makes the deployment
self-contained, and a deployed agent should not drag an entire codebase with it
anyway.

Run:  GOOGLE_CLOUD_PROJECT=... python deploy/deploy_agent_engine.py
"""
from __future__ import annotations

import argparse
import os
import sys

import vertexai
from google.adk.agents import LlmAgent
from pydantic import BaseModel, Field
from vertexai import agent_engines

DISPLAY_NAME = "hopscotch-supervisor"
SUPERVISOR_MODEL = "gemini-3.7-flash"

# The managed container inherits nothing from your shell. Gemini 3.x publisher
# models are served ONLY from the global endpoint, so without this the deployed
# agent runs in us-central1, calls the model regionally, and every query comes
# back 404 -- the third time this exact bug has appeared in this project, and
# the first time inside somebody else's container.
ENV_VARS = {
    "GOOGLE_GENAI_USE_VERTEXAI": "true",
    "GOOGLE_CLOUD_LOCATION": "global",
}

REQUIREMENTS = [
    "google-adk>=2.7",
    "google-genai",
    "google-cloud-aiplatform[agent_engines]",
    "pydantic>=2",
]


class DailyBrief(BaseModel):
    """Mirrors hopscotch.schemas.DailyBrief. Defined here so cloudpickle embeds
    the class rather than a reference the remote container cannot resolve."""
    brief_date: str = ""
    headline: str = Field(description="One sentence. The single most important thing.")
    needs_you_today: list[str] = Field(default_factory=list)
    moved_overnight: list[str] = Field(default_factory=list)
    watch: list[str] = Field(default_factory=list)
    cases_open: int = 0
    generated_by: str = "coordinator"


INSTRUCTION = """\
You supervise a fleet of special education compliance agents. You write the
coordinator's daily brief from a caseload and an activity log.

- `headline` is one sentence. If they read nothing else, what do they need?
- `needs_you_today` is only what a HUMAN must do. The fleet already sends
  notices; do not list those. Overdue cases, failed notices and incomplete
  intake belong here.
- `moved_overnight` is what the fleet did unattended. Specific and brief.
- `watch` is not urgent yet but will be within a week.
- Use student references exactly as given. Never invent a case, a date or a
  number. Leave an empty list empty rather than padding it.
- No preamble, no encouragement, no restating the question.
"""

supervisor = LlmAgent(
    name="coordinator",
    model=SUPERVISOR_MODEL,
    instruction=INSTRUCTION,
    output_schema=DailyBrief,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    ap.add_argument("--location", default=os.environ.get("MODEL_ARMOR_LOCATION", "us-central1"))
    ap.add_argument("--bucket", default=os.environ.get("STAGING_BUCKET", ""))
    args = ap.parse_args()

    if not args.project:
        print("set GOOGLE_CLOUD_PROJECT", file=sys.stderr)
        return 2

    vertexai.init(project=args.project, location=args.location,
                  staging_bucket=args.bucket or f"gs://{args.project}-agentengine")

    existing = [a for a in agent_engines.list()
                if getattr(a, "display_name", "") == DISPLAY_NAME]
    if existing:
        print(f"updating {existing[0].resource_name}")
        remote = existing[0].update(agent_engine=supervisor,
                                    requirements=REQUIREMENTS, env_vars=ENV_VARS)
    else:
        print(f"creating {DISPLAY_NAME} — builds a container, several minutes")
        remote = agent_engines.create(
            agent_engine=supervisor, requirements=REQUIREMENTS,
            env_vars=ENV_VARS, display_name=DISPLAY_NAME,
            description="Hopscotch supervisor: the coordinator's daily brief",
            min_instances=0, max_instances=1)

    print(f"\nAGENT_ENGINE_RUNTIME={remote.resource_name.rsplit('/', 1)[-1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
