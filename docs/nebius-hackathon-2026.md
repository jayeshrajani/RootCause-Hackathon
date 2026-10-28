# Nebius hackathon 2026: timeline, verification and submission notes

## Timeline

The first version of RootCause was built from 14 to 17 October 2026 and imported into this
repository as a snapshot ("first commit"), so its commit date does not show when that work
was done. It included:

- Next.js report wizard and results UI in five languages, with result translation
- FastAPI triage: photo and report analysis by Qwen 3.8 on Cerebras with a strict JSON schema
- Open-Meteo weather, Google Earth Engine Sentinel-2 NDVI/NDMI, DINOv2 + FAISS reference photos
- Deterministic evidence-fit scores with an evidence ledger, urgency and expert-review flags
- Voice input through Google Speech-to-Text

## Investigation stage (from 28 October 2026)

Everything after the first version:

| Area | New work |
| --- | --- |
| NVIDIA Nemotron on Nebius | `app/integrations/nebius.py`: OpenAI-compatible client for `nvidia/nemotron-3-super-120b-a12b` with JSON-schema output, reasoning control, bounded retries, a time budget and classified errors (auth, rate limit, timeout, outage, bad request, invalid output) |
| Evidence review | `app/services/investigation/nemotron_review.py`: compact evidence payload with backend-issued ids (no photos or coordinates), the investigation prompt, schema validation and one repair retry |
| Guardrails | `app/services/investigation/guardrails.py`: drops invented evidence/source ids and unlisted causes, requires retrieved sources for claims, rejects missing data used as evidence, removes chemical/dose/brand advice (adds an extension/KVK referral) and overconfident wording, never lowers expert-review flags |
| Tavily research | `app/integrations/tavily.py`, `app/services/knowledge/`: approved-publisher allowlist, server-built queries, independent URL and relevance validation, dose-free excerpts, optional Extract, 6-hour cache |
| Orchestration | `app/services/investigation/orchestrator.py`: wraps the existing triage, 55 s budget, honest per-step trace, strict mode, daily cap, review translation |
| Follow-up | `POST /api/v1/triage/follow-up`: one yes / no / not-sure answer, recorded as evidence, review redone, scores unchanged |
| Abuse and cost controls | Per-client hourly rate limit on model endpoints, daily review cap |
| Contract | Optional `investigation_review`, `agronomy_sources`, `integration_status`; new `/health` diagnostics |
| Web | Review and Sources tabs, provenance section, follow-up card, strings in five languages |
| Deployment | Dockerfiles, `deploy/cloudbuild.yaml` for Cloud Run with Secret Manager and strict mode |
| Docs and licence | MIT licence, this timeline, demo script, updated README and architecture |

## Why the integrations are substantial

Nemotron is not a label on a chat box. On every real AI triage it receives the scored evidence
ledger and the validated guidance, and its structured review becomes a visible part of the
result: supporting and contradicting evidence, open questions, the next field check, and next
steps tagged as source-backed, unverified or model suggestions. Tavily retrieval runs in the
same request and its pages are re-validated before Nemotron or the farmer sees them. The
deterministic rules stay authoritative: the review can explain and question the triage, but
cannot change its scores, ranking or urgency.

## Status: implemented, tested, live-verified

| Capability | Implemented | Automated tests | Live-verified |
| --- | --- | --- | --- |
| Nebius client and Nemotron review | Yes | Yes (mocked HTTP) | **Pending**: run `scripts/smoke_live.py nebius` with a key |
| Tavily search, validation, Extract, cache | Yes | Yes | **Pending**: run `scripts/smoke_live.py tavily` with a key |
| Guardrails | Yes | Yes | n/a (deterministic) |
| Orchestration, strict mode, trace, budget | Yes | Yes | Pending (end-to-end with keys) |
| Follow-up question | Yes | Yes (API and UI) | Pending |
| Results UI | Yes | Component tests, typecheck, lint, build | Pending manual check with live data |
| Cloud Run deployment | Config written | n/a | **Not deployed yet** |

Experimental parts: the lexical "source-backed" check (necessary, not sufficient), allowlist
coverage outside India and the USA, and translation of the review into Hindi and Punjabi (done by
the analysis model; Nemotron 3 Super does not officially support those languages).

## How judges can verify the integrations

1. Open the demo and submit a crop photo (tomato or potato works best), with a place name for
   weather and, if possible, GPS for satellite evidence.
2. On the result, open **How this result was checked**. The *Evidence review* row shows the
   provider `Nebius Token Factory`, the model `nvidia/nemotron-3-super-120b-a12b`, its real status
   and duration. *Guidance search* shows Tavily's status and the number of validated sources.
3. Open the **Review** tab (Nemotron's structured review) and the **Sources** tab (validated
   pages with links to the original publisher).
4. `GET <api-url>/api/v1/health` shows `investigation_review: "configured"`,
   `investigation_strict: true` and, after a report, `investigation_last_success_at`.
5. In code: start at `apps/api/app/services/investigation/orchestrator.py`. Run
   `pytest tests/test_investigation.py tests/test_guardrails.py` for behaviour without keys.

## Setup

See the README (keys) and [deploy/README.md](../deploy/README.md) (Cloud Run). Minimum for the
full experience: `CEREBRAS_API_KEY`, `NEBIUS_API_KEY`, `TAVILY_API_KEY`.

## Devpost description (draft)

**RootCause: evidence-driven crop investigation**

A farmer photographs a sick plant and says what is wrong. RootCause analyses the photos, checks
the field's recent weather and Sentinel-2 greenness, compares the leaves with labelled reference
photos, and scores each possible cause with transparent, rule-based evidence. Then it
investigates: Tavily retrieves guidance only from approved agricultural research and extension
publishers, and NVIDIA Nemotron 3 Super, served by Nebius Token Factory, cross-examines all of
it. It shows what supports the leading cause, what contradicts it, what is still unknown, and the
single field check that would best tell the leading causes apart. The farmer answers that
question and the review updates.

Deterministic guardrails keep it safe: Nemotron can only cite evidence and sources the backend
retrieved, cannot change scores or urgency, and any chemical dose or brand is removed in favour of
a referral to the local extension office or KVK. Every result shows which providers ran and what
happened, including failures. It is triage, never a diagnosis.

Built with Next.js, FastAPI, NVIDIA Nemotron 3 Super on Nebius Token Factory, Tavily, Qwen on
Cerebras, Open-Meteo, Google Earth Engine and Cloud Run.

## Technology feedback (for the project owner to complete)

- Nebius Token Factory (setup, latency, structured output, reasoning control): _to be completed_
- NVIDIA Nemotron 3 Super (instruction following, JSON reliability, grounding): _to be completed_
- Tavily (domain filtering, relevance, Extract): _to be completed_
