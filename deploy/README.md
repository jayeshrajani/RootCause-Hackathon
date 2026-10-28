# Deploying to Google Cloud Run

Two services built by Cloud Build: `rootcause-api` (FastAPI) and `rootcause-web` (Next.js
standalone). Images are built remotely, so no local Docker is needed.

> Status: these files have been written and statically checked, but have **not been deployed or
> built with Docker yet**. Expect to fix small issues on the first run.

What runs where:

| Service | Image | Keys (Secret Manager) |
| --- | --- | --- |
| `rootcause-api` | `apps/api/Dockerfile` (no torch/FAISS: reference photos are off) | `cerebras-api-key`, `nebius-api-key`, `tavily-api-key` |
| `rootcause-web` | `apps/web/Dockerfile` (API URL baked in at build time) | none |

The NVIDIA Nemotron review runs through Nebius Token Factory's API; the app itself stays on Cloud
Run.

## One-time setup

```bash
PROJECT=<project-id>; REGION=asia-south1
gcloud config set project $PROJECT
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com secretmanager.googleapis.com
gcloud artifacts repositories create rootcause --repository-format=docker --location=$REGION

# Dedicated runtime identity (not the default compute account).
gcloud iam service-accounts create rootcause --display-name="RootCause API"
SA=rootcause@$PROJECT.iam.gserviceaccount.com

# Secrets. Type each key at the prompt; never put keys in files, the repo or shell history.
for s in cerebras-api-key nebius-api-key tavily-api-key; do
  read -rs -p "$s: " value && printf '%s' "$value" | gcloud secrets create $s --data-file=- && echo
  gcloud secrets add-iam-policy-binding $s \
    --member=serviceAccount:$SA --role=roles/secretmanager.secretAccessor
done

# Cloud Build deploys as its service account; it needs to run and impersonate.
CB=$(gcloud projects describe $PROJECT --format='value(projectNumber)')@cloudbuild.gserviceaccount.com
gcloud projects add-iam-policy-binding $PROJECT --member=serviceAccount:$CB --role=roles/run.admin
gcloud projects add-iam-policy-binding $PROJECT --member=serviceAccount:$CB \
  --role=roles/artifactregistry.writer
gcloud iam service-accounts add-iam-policy-binding $SA --member=serviceAccount:$CB \
  --role=roles/iam.serviceAccountUser
```

Optional satellite evidence: register the project for Earth Engine, grant `$SA`
`roles/earthengine.viewer` and `roles/serviceusage.serviceUsageConsumer`, and pass
`_GOOGLE_CLOUD_PROJECT_ID=$PROJECT` below.

## Deploy

The web bundle needs the API URL and the API needs the web URL (CORS), so the first deploy runs
twice:

```bash
# 1st run: creates both services.
gcloud builds submit --config deploy/cloudbuild.yaml

API=$(gcloud run services describe rootcause-api --region $REGION --format='value(status.url)')
WEB=$(gcloud run services describe rootcause-web --region $REGION --format='value(status.url)')

# 2nd run (and every later deploy): wires the URLs together.
gcloud builds submit --config deploy/cloudbuild.yaml \
  --substitutions=_API_URL=$API,_WEB_URL=$WEB
```

## Verify

```bash
curl -s $API/api/v1/health
```

Expect `analysis_mode: "ai"`, `investigation_review: "configured"`,
`agronomy_search: "configured"` and `investigation_strict: true`. After one real report from the
web app, `investigation_last_success_at` shows the time of the last successful Nemotron call
(`investigation_last_error` shows the error kind if it failed). Each result's
**How this result was checked** section lists every provider and its real status.

The deployment runs in strict mode (`ROOTCAUSE_HACKATHON_REQUIRE_LIVE_NEBIUS=true`): a missing
or failing Nemotron review is shown as unavailable, never replaced by another model or a mock.

## Cost and abuse controls

- `ROOTCAUSE_RATE_LIMIT_PER_HOUR` (default 40 here): per-client cap on every model-backed
  endpoint, using the client address Cloud Run appends to `X-Forwarded-For`.
- `ROOTCAUSE_INVESTIGATION_DAILY_LIMIT` (default 300): Nemotron reviews per instance per day.
- `--max-instances=2`: bounds both cost and the in-memory limits above.
- Tavily results are cached for 6 hours per crop/condition/country.
- Add a billing budget alert on the project before sharing the URL.

Limits are kept in memory, reset on restart and apply per instance: fine for a demo, not for
billing-grade enforcement. Follow-up answers are also held in memory for an hour; session
affinity sends a browser back to the same instance, and an expired answer is reported clearly.
