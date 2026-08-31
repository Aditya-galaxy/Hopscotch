#!/usr/bin/env bash
# Day 1 provisioning probe.
#
# The way this project dies is discovering on day 6 that a personal Google
# Cloud account cannot provision Agent Gateway, or that Veo is gated in your
# region. This script fails loudly and early instead. A red line here is
# information, not a problem -- every component has a documented fallback in
# the build plan.
set -uo pipefail

PROJECT="${GOOGLE_CLOUD_PROJECT:?set GOOGLE_CLOUD_PROJECT}"
LOCATION="${GOOGLE_CLOUD_LOCATION:-us-central1}"

pass() { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; }
try()  { if eval "$2" >/dev/null 2>&1; then pass "$1"; else fail "$1"; fi; }

echo "Probing ${PROJECT} in ${LOCATION}"
echo
echo "APIs"
for api in aiplatform.googleapis.com run.googleapis.com firestore.googleapis.com \
           cloudscheduler.googleapis.com \
           modelarmor.googleapis.com cloudtrace.googleapis.com; do
  try "$api" "gcloud services list --enabled --project=$PROJECT --filter=config.name=$api --format='value(config.name)' | grep -q ."
done

echo
echo "Model access"
try "gemini-3.5-flash" "gcloud ai models list --region=$LOCATION --project=$PROJECT"
echo "  NOTE  confirm Veo + Gemma region availability manually before day 8"

echo
echo "Agent Platform components"
try "Agent Engine Runtime" "gcloud ai reasoning-engines list --region=$LOCATION --project=$PROJECT"
echo "  NOTE  Agent Registry / Gateway / Identity may need org-level setup that"
echo "        a personal account lacks. If so: fall back to a Cloud Run policy"
echo "        proxy enforcing the same registry/*.agent.yaml scopes, and say so"
echo "        plainly in the README. Documented fallback beats a silent gap."

echo
echo "Budget guard"
try "budget configured" "gcloud billing budgets list --billing-account=\$(gcloud billing projects describe $PROJECT --format='value(billingAccountName)' | cut -d/ -f2)"
echo "  Set a \$60 alert today. You are personally liable above the credit cap."
