#!/usr/bin/env bash
# Live evidence of which Gemini Enterprise Agent Platform components this
# project actually uses. Everything printed here is fetched at run time, so it
# is checkable rather than claimed -- including the components we do NOT have,
# which are printed just as plainly.
set -uo pipefail
cd "$(dirname "$0")/.."

P="${GOOGLE_CLOUD_PROJECT:-kronagent}"
R="${REGION:-us-central1}"
PY=".venv/bin/python"

bold() { printf "\n\033[1m%s\033[0m\n" "$1"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; }
warn() { printf "  \033[33m~\033[0m %s\n" "$1"; }
no()   { printf "  \033[31m✗\033[0m %s\n" "$1"; }

bold "Agent Registry — our agents, in Google's managed registry"
"$PY" - "$P" "$R" <<'PYEOF'
import json, subprocess, sys, urllib.request, urllib.error
P, R = sys.argv[1], sys.argv[2]
tok = subprocess.run(["gcloud", "auth", "print-access-token"],
                     capture_output=True, text=True).stdout.strip()
url = f"https://agentregistry.googleapis.com/v1/projects/{P}/locations/{R}/agents"
try:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
    agents = json.loads(urllib.request.urlopen(req, timeout=25).read()).get("agents", [])
except urllib.error.HTTPError as ex:
    print(f"  \033[31m✗\033[0m Agent Registry unreachable: HTTP {ex.code}")
    raise SystemExit(0)
except Exception as ex:
    print(f"  \033[31m✗\033[0m Agent Registry unreachable: {type(ex).__name__}")
    raise SystemExit(0)

# Ours are the ones backed by a reasoningEngine in this project; the rest are
# Google's own first-party entries, which are not evidence of anything we built.
mine = [a for a in agents if "reasoningEngines" in a.get("agentId", "")]
print(f"  \033[32m✓\033[0m {len(agents)} agents visible, {len(mine)} of them ours\n")
for a in mine:
    eng = a["agentId"].rsplit(":", 1)[-1]
    proto = (a.get("protocols") or [{}])[0]
    print(f"      {a.get('displayName','(unnamed)')}")
    print(f"        {a.get('description','')}")
    print(f"        engine {eng} · protocol {proto.get('type','?')} "
          f"· {len(proto.get('interfaces', []))} interface(s)")
    print()
PYEOF

bold "Agent Runtime and Memory Bank — Vertex AI Agent Engine"
# Queried over REST rather than `gcloud ai reasoning-engines`, which does not
# exist in every gcloud version and reports a bare "Invalid choice" when absent
# -- indistinguishable from the engine not being there.
"$PY" - "$P" "$R" "${AGENT_ENGINE_ID:-1792847717332942848}" \
       "${AGENT_ENGINE_RUNTIME:-398279945219997696}" <<'PYEOF2'
import json, subprocess, sys, urllib.request, urllib.error
P, R, *ids = sys.argv[1:]
tok = subprocess.run(["gcloud", "auth", "print-access-token"],
                     capture_output=True, text=True).stdout.strip()
for eid in ids:
    u = (f"https://{R}-aiplatform.googleapis.com/v1/projects/{P}/locations/{R}"
         f"/reasoningEngines/{eid}")
    try:
        req = urllib.request.Request(u, headers={"Authorization": f"Bearer {tok}"})
        d = json.loads(urllib.request.urlopen(req, timeout=25).read())
        print(f"  \033[32m✓\033[0m {d.get('displayName','(unnamed)')} — "
              f"engine {eid}, created {d.get('createTime','?')[:10]}")
    except urllib.error.HTTPError as ex:
        print(f"  \033[31m✗\033[0m engine {eid}: HTTP {ex.code}")
    except Exception as ex:
        print(f"  \033[31m✗\033[0m engine {eid}: {type(ex).__name__}")
PYEOF2

bold "Model Armor — guardrails, invoked per document"
BLOCKED=$(gcloud logging read \
  'resource.labels.job_name=agentx-tick AND textPayload:"Model Armor blocked"' \
  --project="$P" --limit=1 --format="value(textPayload)" 2>/dev/null | head -1)
[ -n "$BLOCKED" ] && ok "last block: ${BLOCKED##*: }" || warn "no block recorded yet"

bold "Agent Observability — OTel spans reaching Cloud Trace"
TOK=$(gcloud auth print-access-token 2>/dev/null)
N=$("$PY" -c "
import json,urllib.request,sys
u='https://cloudtrace.googleapis.com/v1/projects/$P/traces?pageSize=5&startTime=2026-08-29T00:00:00Z'
r=urllib.request.Request(u,headers={'Authorization':'Bearer $TOK'})
print(len(json.loads(urllib.request.urlopen(r,timeout=20).read()).get('traces',[])))
" 2>/dev/null)
[ "${N:-0}" -gt 0 ] && warn "$N traces present — OTel-compliant, not the branded product" \
                    || warn "no traces in the window"

bold "Unattended operation"
EX=$(gcloud run jobs executions list --job=agentx-tick --region="$R" --project="$P" \
       --format="value(metadata.name)" 2>/dev/null | wc -l | tr -d " ")
SINCE=$(gcloud run jobs executions list --job=agentx-tick --region="$R" --project="$P" \
       --format="value(metadata.creationTimestamp)" 2>/dev/null | tail -1 | cut -dT -f1)
ok "$EX Cloud Run job executions since $SINCE"
SCHED=$(gcloud scheduler jobs list --location="$R" --project="$P" \
       --format="value(schedule,state)" 2>/dev/null | head -1)
ok "Cloud Scheduler: ${SCHED:-unknown}"

bold "What we do NOT have, stated plainly"
no "Agent Identity — geminienterprise.googleapis.com is NOT OFFERED on this"
no "  project. Agent identity is registry-declared and resolved by name;"
no "  what the gateway enforces is a scope table, not attested zero-trust."
no "Agent Gateway — substituted with in-process policy enforcement in"
no "  src/hopscotch/gateway.py. Same two responsibilities, ours not Google's."
echo
