#!/usr/bin/env bash
# Day 1 bootstrap. Idempotent -- safe to re-run after a partial failure.
#
# Goal is narrow and non-negotiable: get the unattended clock ticking TODAY.
# It does not need to do anything intelligent yet. It needs to be RUNNING, so
# that by submission there are ten days of real trace history behind it. That
# is the one artifact nobody who starts on the 25th can produce.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID (e.g. agentx-hack-0821)}"
BILLING_ACCOUNT="${BILLING_ACCOUNT:?set BILLING_ACCOUNT (gcloud billing accounts list)}"
REGION="${REGION:-us-central1}"
JOB="agentx-tick"
RUN_SA="agentx-tick"
SCHED_SA="agentx-scheduler"
BUDGET_USD="${BUDGET_USD:-60}"

say() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
have() { eval "$1" >/dev/null 2>&1; }

say "1/8  project"
if have "gcloud projects describe $PROJECT_ID"; then
  echo "    exists"
else
  gcloud projects create "$PROJECT_ID"
fi
gcloud config set project "$PROJECT_ID" >/dev/null
gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT" >/dev/null
echo "    billing linked to $BILLING_ACCOUNT"

say "2/8  APIs"
gcloud services enable \
  aiplatform.googleapis.com run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com firestore.googleapis.com pubsub.googleapis.com \
  cloudscheduler.googleapis.com cloudtrace.googleapis.com \
  modelarmor.googleapis.com billingbudgets.googleapis.com \
  --project="$PROJECT_ID"

say "3/8  budget alert (\$${BUDGET_USD})"
# You are personally liable above the credit cap. This is not optional.
if gcloud billing budgets list --billing-account="$BILLING_ACCOUNT" \
     --format='value(displayName)' 2>/dev/null | grep -qx "agentx"; then
  echo "    exists"
else
  gcloud billing budgets create \
    --billing-account="$BILLING_ACCOUNT" --display-name="agentx" \
    --budget-amount="${BUDGET_USD}USD" \
    --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 \
    --filter-projects="projects/$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
fi

say "4/8  firestore"
if have "gcloud firestore databases describe --database='(default)' --project=$PROJECT_ID"; then
  echo "    exists"
else
  gcloud firestore databases create --location="$REGION" --project="$PROJECT_ID"
fi

say "5/8  runtime identity (least privilege)"
# The job gets exactly two roles. Not Editor. The whole project is about
# per-agent scoping -- starting with an over-permissioned runtime undercuts it.
if ! have "gcloud iam service-accounts describe $RUN_SA@$PROJECT_ID.iam.gserviceaccount.com --project=$PROJECT_ID"; then
  gcloud iam service-accounts create "$RUN_SA" \
    --display-name="AgentX tick runtime" --project="$PROJECT_ID"
fi
for role in roles/datastore.user roles/cloudtrace.agent; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$RUN_SA@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="$role" --condition=None >/dev/null
done
echo "    datastore.user + cloudtrace.agent"

say "6/8  deploy the job"
gcloud run jobs deploy "$JOB" \
  --source . --region="$REGION" --project="$PROJECT_ID" \
  --service-account="$RUN_SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_LOCATION=$REGION" \
  --max-retries=1 --task-timeout=10m --memory=512Mi

say "7/8  schedule it (hourly)"
# Hourly, not daily. Same near-zero cost -- the job scales to zero between runs
# -- but by submission the trace history is ~240 unattended executions instead
# of 10. Trace density is what makes the "weeks of async operation" claim land.
if ! have "gcloud iam service-accounts describe $SCHED_SA@$PROJECT_ID.iam.gserviceaccount.com --project=$PROJECT_ID"; then
  gcloud iam service-accounts create "$SCHED_SA" \
    --display-name="AgentX scheduler" --project="$PROJECT_ID"
fi
gcloud run jobs add-iam-policy-binding "$JOB" --region="$REGION" --project="$PROJECT_ID" \
  --member="serviceAccount:$SCHED_SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --role=roles/run.invoker >/dev/null

URI="https://run.googleapis.com/v2/projects/$PROJECT_ID/locations/$REGION/jobs/$JOB:run"
if have "gcloud scheduler jobs describe agentx-hourly --location=$REGION --project=$PROJECT_ID"; then
  gcloud scheduler jobs update http agentx-hourly --location="$REGION" --project="$PROJECT_ID" \
    --schedule="0 * * * *" --uri="$URI" --http-method=POST \
    --oauth-service-account-email="$SCHED_SA@$PROJECT_ID.iam.gserviceaccount.com" >/dev/null
else
  gcloud scheduler jobs create http agentx-hourly --location="$REGION" --project="$PROJECT_ID" \
    --schedule="0 * * * *" --uri="$URI" --http-method=POST \
    --oauth-service-account-email="$SCHED_SA@$PROJECT_ID.iam.gserviceaccount.com"
fi

say "8/8  first run"
gcloud scheduler jobs run agentx-hourly --location="$REGION" --project="$PROJECT_ID"

cat <<DONE

The clock is running. Verify:

  gcloud run jobs executions list --job=$JOB --region=$REGION --project=$PROJECT_ID
  gcloud logging read 'resource.type=cloud_run_job' --limit=20 --project=$PROJECT_ID
  open "https://console.cloud.google.com/traces/list?project=$PROJECT_ID"

Do not delete this schedule before you record the demo. The trace history it
accumulates between now and submission is the proof of asynchronous operation.
DONE
