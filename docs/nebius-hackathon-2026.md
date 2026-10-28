# Nebius x NVIDIA Global AI Hackathon: timeline, verification and submission notes

Track: **Best Apps and Agents**. RootCause also makes a functional runtime call to the Tavily API
on every real report, so it qualifies for **Best Use of Tavily**.

## Timeline

All of RootCause was built inside the Submission Period, which opened on 26 August 2026. It was
developed in two stages; the first stage was imported into this repository as snapshots, so its
commit dates do not show when that work was done.

**First version (14 to 17 October 2026):**

- Next.js photo-first report flow (built-in sample photos, voice note, location prompt) and
  results UI in five languages, with result translation and a per-visit investigation limit
- FastAPI triage: photo and report analysis by Gemini Flash (priority and fallback keys), with
  Qwen 3.8 on Cerebras as fallback, under a strict JSON schema
- Open-Meteo weather, Google Earth Engine Sentinel-2 NDVI/NDMI, DINOv2 + FAISS reference photos
- Deterministic evidence-fit scores with an evidence ledger, urgency and expert-review flags
- Voice input (Gemini, with Google Speech-to-Text as fallback) and read-aloud (Gemini TTS)
- The *Treat it* tab: generic, label-first treatment guidance and nearby agri-input shops
  (Gemini grounded on Google Maps)
- Cloud Run deployment files (Dockerfiles, Cloud Build)

## Investigation stage (from 28 October 2026)

The Nemotron and Tavily investigation and the work to integrate it with the first version:

| Area | New work |
| --- | --- |
| NVIDIA Nemotron on Nebius | `app/integrations/nebius.py`: OpenAI-compatible client with JSON-schema output, reasoning control, bounded retries, a time budget and classified errors (auth, rate limit, timeout, outage, bad request, invalid output). Nemotron 3 Ultra (`nvidia/Nemotron-3-Ultra-550b-a55b`) runs the review and Nemotron 3 Super (`nvidia/nemotron-3-super-120b-a12b`) the follow-up re-review; each falls back to the other |
| Evidence review | `app/services/investigation/nemotron_review.py`: compact evidence payload with backend-issued ids (no photos or coordinates), the investigation prompt, schema validation and one repair retry |
| Guardrails | `app/services/investigation/guardrails.py`: drops invented evidence/source ids and unlisted causes, requires retrieved sources for claims, rejects missing data used as evidence, removes chemical/dose/brand advice (adds an extension/KVK referral) and overconfident wording, never lowers expert-review flags |
| Tavily research | `app/integrations/tavily.py`, `app/services/knowledge/`: approved-publisher allowlist, server-built queries, independent URL and relevance validation, dose-free excerpts, optional Extract, 6-hour cache |
| Orchestration | `app/services/investigation/orchestrator.py`: wraps the existing triage, 55 s budget, honest per-step trace, strict mode, daily cap, review translation |
| Follow-up | `POST /api/v1/triage/follow-up`: one yes / no / not-sure answer, recorded as evidence, review redone, scores unchanged |
| Abuse and cost controls | Per-client hourly rate limit on crop identification, translation, transcription and follow-up; daily review cap; every per-IP limit (including the first version's) reads the proxy-appended client address, so it cannot be spoofed |
| Contract | Optional `investigation_review`, `agronomy_sources`, `integration_status`; new `/health` diagnostics |
| Web | Review and Sources tabs (next to the existing *Treat it* tab), provenance section, follow-up card, the guidance and cross-check steps on the analysis screen, strings in five languages |
| Deployment | Nebius and Tavily keys in Secret Manager, strict mode, session affinity and the time budget added to the Cloud Run pipeline |
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

Live checks ran on 28 October 2026 against the real Nebius Token Factory and Tavily APIs, from a
local run of the app (timings are single runs, not benchmarks).

| Capability | Implemented | Automated tests | Live-verified |
| --- | --- | --- | --- |
| Nebius client and Nemotron review | Yes | Yes (mocked HTTP) | **Yes**: `smoke_live.py` passed; all model ids found in the Token Factory catalog; schema-valid reviews from Nemotron 3 Ultra, Super and Nano |
| Tavily search, validation, Extract, cache | Yes | Yes | **Yes**: 4 validated publisher pages for tomato early and late blight. Found live: searches with `country=india` returned nothing, so they now retry worldwide |
| Guardrails | Yes | Yes | n/a (deterministic) |
| Orchestration, strict mode, trace, budget | Yes | Yes | **Yes**: a full report (tomato sample, Pune, Hindi) returned a completed review grounded in 4 sources and translated into Hindi, with the full provider trace |
| Follow-up question | Yes | Yes (API and UI) | **Yes**: answer recorded, round 2 review from Nemotron 3 Super, scores unchanged, a second answer refused (409) |
| Results UI | Yes | Component tests, typecheck, lint, build | Pending manual check with live data |
| Cloud Run deployment | Config written | n/a | **Not deployed yet** |

Experimental parts: the lexical "source-backed" check (necessary, not sufficient), allowlist
coverage outside India and the USA, and translation of the review into Hindi and Punjabi (done by
the analysis model, not by Nemotron).

## How judges can verify the integrations

1. Open the demo and submit a crop photo, or tap a built-in sample (tomato or potato works best),
   with a place name for weather and, if possible, GPS for satellite evidence.
2. On the result, open **How this result was checked**. The *Evidence review* row shows the
   provider `Nebius Token Factory`, the model (`nvidia/Nemotron-3-Ultra-550b-a55b`, or
   `nvidia/nemotron-3-super-120b-a12b` after a follow-up answer or a fallback), its real status
   and duration. *Guidance search* shows Tavily's status and the number of validated sources.
3. Open the **Review** tab (Nemotron's structured review) and the **Sources** tab (validated
   pages with links to the original publisher).
4. `GET <api-url>/api/v1/health` shows `investigation_review: "configured"`,
   `investigation_strict: true` and, after a report, `investigation_last_success_at`.
5. In code: start at `apps/api/app/services/investigation/orchestrator.py`. Run
   `pytest tests/test_investigation.py tests/test_guardrails.py` for behaviour without keys.

## Setup

See the README (keys) and [deploy/README.md](../deploy/README.md) (Cloud Run). Minimum for the
full experience: `GEMINI_API_KEY` (or `CEREBRAS_API_KEY`), `NEBIUS_API_KEY`, `TAVILY_API_KEY`.

## Devpost description (draft)

**RootCause: evidence-driven crop investigation**

A farmer photographs a sick plant and says what is wrong. RootCause analyses the photos, checks
the field's recent weather and Sentinel-2 greenness, compares the leaves with labelled reference
photos, and scores each possible cause with transparent, rule-based evidence. Then it
investigates: Tavily retrieves guidance only from approved agricultural research and extension
publishers, and NVIDIA Nemotron 3 Ultra, served by Nebius Token Factory, cross-examines all of
it. It shows what supports the leading cause, what contradicts it, what is still unknown, and the
single field check that would best tell the leading causes apart. The farmer answers that
question and Nemotron 3 Super updates the review.

Deterministic guardrails keep it safe: Nemotron can only cite evidence and sources the backend
retrieved, cannot change scores or urgency, and any chemical dose or brand is removed in favour of
a referral to the local extension office or KVK. Every result shows which providers ran and what
happened, including failures. It is triage, never a diagnosis.

Built with Next.js, FastAPI, NVIDIA Nemotron 3 Ultra and Super on Nebius Token Factory, Tavily,
Gemini (with Qwen on Cerebras as fallback), Open-Meteo, Google Earth Engine and Cloud Run.

## Technology feedback (draft from the build; edit before submitting)

Nebius Token Factory

- The OpenAI-compatible endpoint worked with plain `httpx`; strict `json_schema` output and the
  `chat_template_kwargs` reasoning switch were accepted by Nemotron 3 Ultra, Super and Nano.
- The `/v1/models` catalog made model ids easy to verify, but their casing differs by family
  (`nvidia/Nemotron-3-Ultra-550b-a55b`, `nvidia/nemotron-3-super-120b-a12b`,
  `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`), which is easy to get wrong. Case-insensitive ids or
  short aliases would help.
- Latency for the same model and prompt size varied between runs (Super took 7.5–18 s for a
  ~2,700-token prompt). Published per-model latency guidance would make tier choices easier.

NVIDIA Nemotron

- All three sizes returned schema-valid reviews on the first attempt in our live runs, and kept
  to the backend-issued evidence and source ids.
- Reviews are written in English; native Hindi and Punjabi output would remove our separate
  translation step for farmers.

Tavily

- `include_domains` combined with `country="india"` returned no results for queries that
  returned four relevant pages without `country`. We now retry worldwide; documenting how the
  two parameters interact would help.
- Search `content` sometimes contains site chrome (cookie notices, "Skip to content",
  breadcrumbs), which we strip; Extract gave cleaner, richer excerpts.
