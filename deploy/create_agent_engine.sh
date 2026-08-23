#!/usr/bin/env bash
# Create the Vertex AI Agent Engine instance that hosts Memory Bank.
#
# Memory Bank is not a standalone service -- it lives inside an Agent Engine
# instance and is addressed by that instance's id. An EMPTY instance is enough:
# we are using it for cross-session memory, not to host agent code, so this
# costs a fraction of a full deployment and takes seconds instead of minutes.
#
# There is no gcloud surface for this, hence curl.
set -euo pipefail
PROJECT="${GOOGLE_CLOUD_PROJECT:?set GOOGLE_CLOUD_PROJECT}"
REGION="${MODEL_ARMOR_LOCATION:-us-central1}"
NAME="${AGENT_ENGINE_NAME:-agentx-memory}"
API="https://${REGION}-aiplatform.googleapis.com/v1beta1/projects/${PROJECT}/locations/${REGION}/reasoningEngines"
TOKEN="$(gcloud auth print-access-token)"

existing="$(curl -s -H "Authorization: Bearer $TOKEN" "$API" \
  | python3 -c "
import json,sys
d=json.load(sys.stdin) or {}
for e in d.get('reasoningEngines', []):
    if e.get('displayName')=='${NAME}':
        print(e['name'].rsplit('/',1)[-1]); break
")"

if [ -n "$existing" ]; then
  echo "AGENT_ENGINE_ID=$existing   (existing)"
  exit 0
fi

op="$(curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"displayName\":\"${NAME}\",\"description\":\"Hopscotch cross-session memory\"}" "$API")"
id="$(printf '%s' "$op" | python3 -c "
import json,sys
print(json.load(sys.stdin)['name'].split('/reasoningEngines/')[1].split('/')[0])
")"
echo "AGENT_ENGINE_ID=$id   (created)"
echo
echo "Add it to .env and to the Cloud Run job:"
echo "  gcloud run jobs update agentx-tick --region=$REGION \\"
echo "    --update-env-vars=AGENT_ENGINE_ID=$id"
