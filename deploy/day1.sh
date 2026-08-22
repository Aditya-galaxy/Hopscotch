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
ARMOR_TEMPLATE="${ARMOR_TEMPLATE:-agentx-skill-review}"
BUDGET_USD="${BUDGET_USD:-60}"

say() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
have() { eval "$1" >/dev/null 2>&1; }

say "1/9  project"
if have "gcloud projects describe $PROJECT_ID"; then
  echo "    exists"
else
  gcloud projects create "$PROJECT_ID"
fi
gcloud config set project "$PROJECT_ID" >/dev/null
if [ "$(gcloud billing projects describe "$PROJECT_ID" --format='value(billingEnabled)' 2>/dev/null)" = "True" ]; then
  echo "    billing already enabled"
else
  # Billing accounts cap how many projects they may fund. If this fails with a
  # quota error, free a slot or build in a project that is already funded --
  # do not burn a day on it.
  gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT" >/dev/null
  echo "    billing linked to $BILLING_ACCOUNT"
fi

say "2/9  APIs"
gcloud services enable \
  aiplatform.googleapis.com run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com firestore.googleapis.com pubsub.googleapis.com \
  cloudscheduler.googleapis.com cloudtrace.googleapis.com \
  modelarmor.googleapis.com billingbudgets.googleapis.com \
  --project="$PROJECT_ID"

say "3/9  budget alert"
# Two things bite here. The amount must be in the BILLING ACCOUNT's currency --
# passing 60USD to an INR account is rejected as INVALID_ARGUMENT with no hint
# about why. And --filter-projects wants projects/{project_id}, not the project
# number. Neither is fatal to the build, so a failure warns loudly and carries
# on rather than stranding the bootstrap over an alert.
CURRENCY="$(gcloud beta billing accounts describe "$BILLING_ACCOUNT" \
  --format='value(currencyCode)' 2>/dev/null || echo USD)"
: "${BUDGET_AMOUNT:=}"
if [ -z "$BUDGET_AMOUNT" ]; then
  case "$CURRENCY" in
    USD) BUDGET_AMOUNT=60 ;;
    INR) BUDGET_AMOUNT=5000 ;;
    EUR|GBP) BUDGET_AMOUNT=55 ;;
    *)   BUDGET_AMOUNT=60 ;;
  esac
fi
if gcloud billing budgets list --billing-account="$BILLING_ACCOUNT" \
     --format='value(displayName)' 2>/dev/null | grep -qx "agentx"; then
  echo "    exists"
elif gcloud billing budgets create \
      --billing-account="$BILLING_ACCOUNT" --display-name="agentx" \
      --budget-amount="$BUDGET_AMOUNT" \
      --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 \
      --filter-projects="projects/$PROJECT_ID" >/dev/null 2>&1; then
  echo "    ${BUDGET_AMOUNT} ${CURRENCY}, alerts at 50% and 90%"
else
  echo "    WARNING: budget not created. Set one by hand before you walk away --"
  echo "    you are personally liable above the credit cap."
fi

say "4/9  firestore"
if have "gcloud firestore databases describe --database='(default)' --project=$PROJECT_ID"; then
  echo "    exists"
else
  gcloud firestore databases create --location="$REGION" --project="$PROJECT_ID"
fi

say "5/9  model armor template"
# Model Armor is REGIONAL and only answers on its regional endpoint. Without
# this override gcloud hits the default host and reports PERMISSION_DENIED on a
# project you plainly have access to -- a genuinely misleading error. Set as an
# env var rather than `gcloud config set` so this script never mutates the
# user's persistent configuration.
export CLOUDSDK_API_ENDPOINT_OVERRIDES_MODELARMOR="https://modelarmor.${REGION}.rep.googleapis.com/"
if have "gcloud model-armor templates describe $ARMOR_TEMPLATE --location=$REGION --project=$PROJECT_ID"; then
  echo "    exists"
else
  gcloud model-armor templates create "$ARMOR_TEMPLATE" \
    --location="$REGION" --project="$PROJECT_ID" \
    --pi-and-jailbreak-filter-settings-enforcement=enabled \
    --pi-and-jailbreak-filter-settings-confidence-level=low-and-above \
    --malicious-uri-filter-settings-enforcement=enabled
fi
echo "    screens scanned documents AND SKILL.md content -- same boundary,"
echo "    two subjects. Confidence low-and-above: a missed injection costs more"
echo "    than a coordinator dismissing a false positive."

say "6/9  runtime identity (least privilege)"
# The job gets exactly two roles. Not Editor. The whole project is about
# per-agent scoping -- starting with an over-permissioned runtime undercuts it.
if ! have "gcloud iam service-accounts describe $RUN_SA@$PROJECT_ID.iam.gserviceaccount.com --project=$PROJECT_ID"; then
  gcloud iam service-accounts create "$RUN_SA" \
    --display-name="AgentX tick runtime" --project="$PROJECT_ID"
fi
for role in roles/datastore.user roles/cloudtrace.agent \
            roles/aiplatform.user roles/modelarmor.user; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$RUN_SA@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="$role" --condition=None >/dev/null
done
echo "    datastore.user, cloudtrace.agent, aiplatform.user, modelarmor.user"

# Cloud Build runs as the project's default compute service account, and on
# projects created before the current defaults it lacks read access to its OWN
# source-upload bucket. The failure surfaces as a 403 storage.objects.get on a
# run-sources-* object, which reads like a bug in your build rather than a
# missing grant. Do it before the first deploy, not after the first confusing
# error.
PNUM="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
BUILD_SA="${PNUM}-compute@developer.gserviceaccount.com"
for role in roles/cloudbuild.builds.builder roles/storage.objectViewer \
            roles/artifactregistry.writer roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$BUILD_SA" --role="$role" --condition=None >/dev/null 2>&1 || true
done

say "7/9  deploy the job"
gcloud run jobs deploy "$JOB" \
  --source . --region="$REGION" --project="$PROJECT_ID" \
  --service-account="$RUN_SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_LOCATION=global,MODEL_ARMOR_LOCATION=$REGION,MODEL_ARMOR_TEMPLATE=$ARMOR_TEMPLATE" \
  --max-retries=1 --task-timeout=10m --memory=512Mi

say "8/9  schedule it (hourly)"
# Hourly, not daily. Same near-zero cost -- the job scales to zero between runs
# -- but by submission the trace history is ~240 unattended executions instead
# of 10. Trace density is what makes the "weeks of async operation" claim land.
if ! have "gcloud iam service-accounts describe $SCHED_SA@$PROJECT_ID.iam.gserviceaccount.com --project=$PROJECT_ID"; then
  gcloud iam service-accounts create "$SCHED_SA" \
    --display-name="AgentX scheduler" --project="$PROJECT_ID"
fi
# IAM is eventually consistent: a service account created a second ago is not
# yet visible to the binding API, which reports "does not exist" rather than
# "not yet". Wait for it instead of failing the bootstrap on a race.
for attempt in 1 2 3 4 5 6; do
  if gcloud run jobs add-iam-policy-binding "$JOB" --region="$REGION" \
       --project="$PROJECT_ID" \
       --member="serviceAccount:$SCHED_SA@$PROJECT_ID.iam.gserviceaccount.com" \
       --role=roles/run.invoker >/dev/null 2>&1; then
    break
  fi
  [ "$attempt" = 6 ] && { echo "    scheduler binding failed after 6 tries"; exit 1; }
  sleep 5
done

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

say "9/9  first run"
gcloud scheduler jobs run agentx-hourly --location="$REGION" --project="$PROJECT_ID"

cat <<DONE

The clock is running. Verify:

  gcloud run jobs executions list --job=$JOB --region=$REGION --project=$PROJECT_ID
  gcloud logging read 'resource.type=cloud_run_job' --limit=20 --project=$PROJECT_ID
  open "https://console.cloud.google.com/traces/list?project=$PROJECT_ID"

Do not delete this schedule before you record the demo. The trace history it
accumulates between now and submission is the proof of asynchronous operation.
DONE
