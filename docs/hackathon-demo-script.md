# Demo video script (2:40)

Target length 2:40 (the limit is 3:00), about 330 words of narration at a calm pace. Record on
the [hosted demo](https://rootcause-web-980426741953.asia-south1.run.app) so judges can repeat
every step. Speed up only the waits, and label them on screen.

## Before recording

- Open <https://rootcause-api-980426741953.asia-south1.run.app/api/v1/health> and check
  `investigation_review: "configured"`. This also wakes the Cloud Run instance.
- Do one dry run with the **potato** sample, then record with **tomato**, so the take runs a live
  Tavily search (a repeat within 6 hours is served from the cache and says "(cached)").
- Use a fresh incognito window for each take: the location prompt appears once per visit, and a
  visit allows 5 investigations.
- The analysing screen prints the field's coordinates. Override the location first (Chrome
  DevTools, Sensors, Location, for example Nashik `19.99, 73.79`; keep DevTools open in its own
  window), or tap **Not now** and search for a place instead.
- English interface, browser zoom 110–125 %, desktop width (summary card on the left, tabs on the
  right), bookmarks bar hidden.
- Capture the screen with the microphone on for the Hindi voice note. Record the English
  voice-over separately and lay it over the footage.

## Script

### 1. The problem (0:00–0:19)

**Screen:** the tomato sample photo, full screen; *Early blight? Late blight? Nutrient problem?*
appear one by one. Cut to the landing page with the demo URL in the address bar. Lower third:
*RootCause · for smallholder farmers and the extension workers who support them*.

**Say:** "A spotted tomato leaf could be early blight, late blight or a nutrient problem. Guess
wrong, and a smallholder farmer loses the crop, or pays for the wrong spray. A generic chatbot
will sound sure either way. RootCause gathers the evidence first, and shows its working."

### 2. The report (0:19–0:36)

**Screen:** **Start a crop report** → *Where's the patient?* → **Share location** → tap the
**Tomato** sample → tap the microphone, speak, **Stop**. The report sends itself once the voice
note is transcribed.

**Say:** "A farmer adds a photo, here a built-in sample, shares where the field is, and just says
what's wrong, in Hindi or English."

**Farmer, in Hindi (subtitled):** "नीचे की पत्तियों पर भूरे धब्बे हैं, चार दिन से फैल रहे हैं।"
*(Brown spots on the lower leaves, spreading for four days.)*

### 3. Analysis (0:36–0:46)

**Screen:** *Identifying your crop*, then *Checking the evidence*, sped up through to *Looking up
official agricultural guidance* and *Cross-checking the evidence*. Caption: *Sped up · real run
about 45 s*.

**Say:** "Stage one: Gemini reads the photo and what the farmer said, and Open-Meteo adds the
past week's weather at the field."

### 4. The triage (0:46–0:59)

**Screen:** the summary card (likely cause, urgency, *Not a diagnosis*), **Field conditions**,
then **Possible causes**: the top cause's evidence fit and its weather chip.

**Say:** "Deterministic rules turn that into an evidence-fit score for each cause. It isn't a
probability, and every point the weather adds or removes is listed with its reason."

### 5. Official guidance, found by Tavily (0:59–1:18)

**Screen:** the **Sources** tab and its cards; **Open source** on one card, the publisher's page,
then back. Caption: *New in this edition: Tavily + NVIDIA Nemotron investigation*.

**Say:** "Then RootCause investigates. Tavily searches only thirty approved research and
extension publishers, like ICAR, FAO and university extension services. Extract pulls the best
pages, and each one is re-checked for this crop and disease, with dose instructions stripped,
before Nemotron or the farmer sees it."

### 6. The cross-examination: Nemotron 3 Ultra (1:18–1:40)

**Screen:** the **Review** tab: *Cross-checked by NVIDIA Nemotron*, *Checked against official
guidance* and the summary; *What supports the leading cause* and *What doesn't fit* with their
evidence chips; stop on *One question to narrow it down*. Caption: *NVIDIA Nemotron 3 Ultra ·
Nebius Token Factory*.

**Say:** "Now NVIDIA Nemotron 3 Ultra, on Nebius Token Factory, takes the case. It doesn't
diagnose; it cross-examines. From the evidence ledger and the guidance, it names what supports
the leading cause, what doesn't fit, and the one field check that would best tell the causes
apart."

### 7. The follow-up: Nemotron 3 Super (1:40–1:58)

**Screen:** tap **Yes** or **No** (*Not sure* leaves the review unchanged); trim the *Updating
the review…* wait; *What changed after your answer* appears at the top of the review. Caption:
*NVIDIA Nemotron 3 Super · follow-up review*.

**Say:** "The farmer answers with one tap, and the faster Nemotron 3 Super redoes the review and
shows what changed. The answer is recorded as evidence, but the scores never move: Nemotron can
question the triage, not overrule it."

### 8. Guardrails and provenance (1:58–2:15)

**Screen:** *Safe next steps* with the *Backed by source* and *Safety referral* badges (open
*Removed by safety checks* if it is there), then **How this result was checked**: *Guidance
search* (Tavily, validated sources), *Evidence review* (Nebius Token Factory, the model, its
time, round 2) and *Satellite: Not set up*.

**Say:** "Guardrails strip anything that cites unknown evidence, names an unlisted cause, sounds
over-certain or gives a chemical dose, and point the farmer to the local extension office
instead. And every result shows what really ran, including what didn't."

### 9. Under the hood (2:15–2:31)

**Screen:** the repository on GitHub,
[apps/api/app/integrations/nebius.py](../apps/api/app/integrations/nebius.py):
`NebiusClient._body` (`response_format` with a strict JSON schema, `chat_template_kwargs`), then
`FallbackNebiusClient`.

**Say:** "Under the hood: one OpenAI-compatible Token Factory endpoint, strict JSON-schema output
and low reasoning effort. Ultra handles the heavy reasoning, Super the quick follow-ups, and each
is the other's fallback, inside a 55-second budget."

### 10. Close (2:31–2:40)

**Screen:** the result's summary card, then an end card: *RootCause*, the demo URL,
`github.com/jayeshrajani/RootCause-Hackathon`, *MIT licence*.

**Say:** "Evidence first. Models reason. Rules protect. Sources substantiate. Farmers decide."

## If the take goes wrong

- *Which crop is this?* appears: tap **Tomato** and trim the pause.
- *Evidence-only review: official guidance was not verified* (Tavily found nothing): retake once;
  if it happens again, keep it and say "No approved source matched this time, and the review
  says so."
- *Evidence review unavailable*: retake. Never splice in footage from an earlier run.
- Running long: shorten segment 4 first, then segment 9.

Upload to YouTube as **Public**, under 3:00, then add the link to the README (the links under the
introduction and *Hackathon submission*) and to Devpost.
