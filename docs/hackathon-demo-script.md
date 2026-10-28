# Hackathon demo script (target 2:30–2:50)

Record only what works on the day. Before recording: keys set, `/api/v1/health` shows
`investigation_review: "configured"`, and one test report has run so the guidance cache is warm.
Use one of your own tomato or potato photos (a built-in sample is not included yet).

| Time | On screen | Say |
| --- | --- | --- |
| 0:00–0:20 | A spotted tomato leaf photo | "One photo of a sick leaf can fit several problems: early blight, late blight, a nutrient issue. Guessing wrong costs a farmer the crop, or money spent on the wrong spray." |
| 0:20–0:45 | Report wizard: add photo, crop, a place or GPS, speak or type the symptoms, submit | "RootCause takes a photo, a few words in the farmer's language, and the field location." |
| 0:45–1:15 | Summary card, **Field conditions**, **Possible causes** with evidence-fit chips | "The first stage analyses the photos, pulls recent weather and Sentinel-2 satellite greenness, and scores every cause with transparent rules. Each point added or removed has a reason." |
| 1:15–1:45 | **Sources** tab: a guidance card, then **Open source** to the publisher's page | "Tavily searches only approved agricultural research and extension publishers. Each page is re-checked for the crop and the disease before anyone sees it, and dose instructions are stripped out." |
| 1:45–2:15 | **Review** tab: summary, supports / doesn't fit, the follow-up question; tap an answer and show *What changed* | "NVIDIA Nemotron on Nebius cross-examines the evidence: what fits, what contradicts, what is unknown, and the one field check that best separates the causes. The farmer answers, and the review updates. Scores never change: Nemotron can question the triage, not overrule it." |
| 2:15–2:35 | **How this result was checked**: Nemotron row with provider, model and duration; then `/api/v1/health` | "Every result shows which providers really ran. If Nemotron fails, the triage still arrives and says so; it is never swapped for another model." |
| 2:35–2:50 | Next steps with *Source-backed* and *Safety referral* badges | "RootCause never invents chemical doses. It gives safe next steps, says when to call the local extension office or KVK, and is honest about what it doesn't know." |

Fallbacks: if Tavily finds no source for the chosen crop, show the *internal evidence only* label
in the Review tab and say so; do not reuse an old screenshot as if it were live.
