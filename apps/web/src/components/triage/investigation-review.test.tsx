import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AgronomySources } from "@/components/triage/agronomy-sources";
import { EvidenceProvenance } from "@/components/triage/evidence-provenance";
import { InvestigationReviewPanel } from "@/components/triage/investigation-review";
import { TriageResult } from "@/components/triage/triage-result";
import { I18nProvider } from "@/lib/i18n";
import { readLatestTriageRaw } from "@/lib/triage-storage";
import type { AgronomySource, InvestigationReview, TriageResponse } from "@/types/triage";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const SOURCE: AgronomySource = {
  id: "S1",
  title: "Early blight of tomato",
  url: "https://agritech.tnau.ac.in/crop_protection/tomato.html",
  publisher: "Tamil Nadu Agricultural University",
  domain: "agritech.tnau.ac.in",
  region: "India",
  retrieved_at: "2026-10-20T09:00:00Z",
  published_at: "2025-03-11",
  excerpt: "Early blight causes brown spots with concentric rings on older leaves.",
  crop_relevance: true,
  condition_relevance: true,
  condition_keys: ["early_blight"],
  validation_status: "validated",
};

const REVIEW: InvestigationReview = {
  status: "completed",
  provider: "Nebius Token Factory",
  model: "nvidia/nemotron-3-super-120b-a12b",
  detail: null,
  generated_at: "2026-10-20T09:00:00Z",
  duration_ms: 8400,
  usage: { prompt_tokens: 1200, completion_tokens: 400, credits: null },
  language: "en",
  round: 1,
  grounding: "sources_and_evidence",
  leading_condition_key: "early_blight",
  reasoning_summary: "Ringed spots and a humid week fit early blight better than late blight.",
  evidence_consistent: "mixed",
  supporting_observations: [
    { text: "Ringed brown spots on lower leaves.", evidence_ids: ["ev_photo_1"], condition_key: "early_blight" },
  ],
  contradictions: [
    { text: "No white growth was reported.", evidence_ids: ["ev_farmer_report"], condition_key: "late_blight" },
  ],
  unresolved_questions: ["Is there white mould under the leaves?"],
  follow_up_question: {
    id: "fq_000000000001",
    text: "Do the spots have rings like a target?",
    category: "visible_pattern",
    discriminates: ["early_blight", "late_blight"],
    why: "Rings point to early blight.",
    options: ["yes", "no", "not_sure"],
    answer: null,
  },
  knowledge_findings: [
    {
      claim: "Early blight causes ringed spots on older leaves.",
      source_ids: ["S1"],
      applicability: "Indian guidance.",
      support_status: "source_backed",
      verified: true,
    },
  ],
  safe_next_steps: [
    {
      action: "Remove spotted lower leaves.",
      rationale: "Reduces spores.",
      priority: "within_days",
      source_ids: ["S1"],
      requires_expert_review: false,
      support_status: "source_backed",
    },
    {
      action: "Ask your local extension office or KVK about approved treatments.",
      rationale: "Approval differs by country.",
      priority: "within_days",
      source_ids: [],
      requires_expert_review: true,
      support_status: "safety_referral",
    },
  ],
  limitations: ["Satellite data was not available."],
  source_ids: ["S1"],
  guardrail_notes: ["Removed 1 item(s) that mentioned chemical products, doses or spray schedules."],
  previous_summary: null,
  what_changed: [],
};

function result(overrides: Partial<TriageResponse> = {}): TriageResponse {
  return {
    report_id: "rpt_0123456789abcdef",
    status: "completed",
    analysis_mode: "ai",
    response_language: "en",
    crop: "tomato",
    detected_crop: "tomato",
    location_label: "Pune",
    approximate_location: null,
    weather_summary: null,
    summary: "The spots may be early blight.",
    urgency: "moderate",
    urgency_reason: "Spreading upwards.",
    possible_causes: [],
    evidence: [
      { id: "ev_farmer_report", source: "farmer_report", availability: "available", observation: "Report", observed_at: null },
      { id: "ev_photo_1", source: "photo", availability: "available", observation: "Spots", observed_at: null },
    ],
    missing_information: [],
    recommended_actions: [],
    requires_expert_review: false,
    generated_at: "2026-10-20T09:00:00Z",
    data_sources: [],
    disclaimer: "Not a diagnosis.",
    investigation_review: REVIEW,
    agronomy_sources: [SOURCE],
    integration_status: [
      {
        step: "nemotron_review",
        provider: "Nebius Token Factory",
        model: "nvidia/nemotron-3-super-120b-a12b",
        status: "success",
        duration_ms: 8400,
        detail: "Reviewed the evidence ledger and retrieved guidance",
        usage: null,
      },
      {
        step: "satellite",
        provider: "Google Earth Engine (Sentinel-2)",
        model: null,
        status: "not_requested",
        duration_ms: null,
        detail: null,
        usage: null,
      },
    ],
    ...overrides,
  };
}

function renderWithI18n(ui: ReactNode) {
  return render(<I18nProvider>{ui}</I18nProvider>);
}

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
});
afterEach(() => vi.unstubAllGlobals());

describe("InvestigationReviewPanel", () => {
  it("shows the grounded review with evidence chips, support labels and safe source links", () => {
    renderWithI18n(<InvestigationReviewPanel result={result()} />);

    expect(screen.getByText("Cross-checked by NVIDIA Nemotron")).toBeTruthy();
    expect(screen.getByText("Checked against official guidance")).toBeTruthy();
    expect(screen.getByText("Evidence is mixed")).toBeTruthy();
    expect(screen.getByText("Ringed brown spots on lower leaves.")).toBeTruthy();
    expect(screen.getAllByText("Backed by source").length).toBe(2);
    expect(screen.getByText("Safety referral")).toBeTruthy();
    const links = screen.getAllByRole("link", { name: /S1 · Tamil Nadu Agricultural University/ });
    expect(links[0].getAttribute("href")).toBe(SOURCE.url);
    expect(links[0].getAttribute("rel")).toBe("noopener noreferrer");
    expect(screen.getByText(/cannot change the scores, ranking or urgency/)).toBeTruthy();
    expect(screen.getByText(/Removed by safety checks \(1\)/)).toBeTruthy();
  });

  it("labels an evidence-only review honestly", () => {
    const review = { ...REVIEW, grounding: "internal_evidence_only" as const, knowledge_findings: [] };
    renderWithI18n(<InvestigationReviewPanel result={result({ investigation_review: review, agronomy_sources: [] })} />);

    expect(screen.getByText("Evidence-only review: official guidance was not verified")).toBeTruthy();
  });

  it.each([
    ["not_configured", "Evidence review not set up"],
    ["unavailable", "Evidence review unavailable"],
    ["skipped", "Evidence review not run"],
  ] as const)("explains a %s review without hiding the triage", (status, title) => {
    const review = { ...REVIEW, status, detail: "Server detail." };
    renderWithI18n(<InvestigationReviewPanel result={result({ investigation_review: review })} />);

    expect(screen.getByText(title)).toBeTruthy();
    expect(screen.getByText("Server detail.")).toBeTruthy();
    expect(screen.getByText("The triage above is complete and unchanged.")).toBeTruthy();
    expect(screen.queryByText("Cross-checked by NVIDIA Nemotron")).toBeNull();
  });

  it("never links a non-https source", () => {
    const unsafe = { ...SOURCE, url: "javascript:alert(1)" };
    renderWithI18n(<InvestigationReviewPanel result={result({ agronomy_sources: [unsafe] })} />);

    expect(screen.queryByRole("link", { name: /S1/ })).toBeNull();
    expect(screen.getAllByText("S1 · Tamil Nadu Agricultural University").length).toBeGreaterThan(0);
  });
});

describe("follow-up question", () => {
  it("sends the answer and stores the updated result", async () => {
    const user = userEvent.setup();
    const answered = result({
      investigation_review: {
        ...REVIEW,
        round: 2,
        what_changed: ["Rings fit early blight."],
        follow_up_question: { ...REVIEW.follow_up_question!, answer: "yes" },
      },
    });
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(answered), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    renderWithI18n(<InvestigationReviewPanel result={result()} />);

    await user.click(screen.getByRole("button", { name: "Yes" }));

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toMatch(/\/api\/v1\/triage\/follow-up$/);
    expect(JSON.parse(init.body as string)).toEqual({
      report_id: "rpt_0123456789abcdef",
      question_id: "fq_000000000001",
      answer: "yes",
    });
    expect(JSON.parse(readLatestTriageRaw() ?? "{}").investigation_review.round).toBe(2);
  });

  it("explains an expired result", async () => {
    const user = userEvent.setup();
    const body = { error: { code: "follow_up_expired", message: "expired", details: [] } };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 410 })));
    renderWithI18n(<InvestigationReviewPanel result={result()} />);

    await user.click(screen.getByRole("button", { name: "No" }));

    expect(await screen.findByText(/This result has expired/)).toBeTruthy();
  });

  it("shows the recorded answer instead of buttons", () => {
    const review = { ...REVIEW, follow_up_question: { ...REVIEW.follow_up_question!, answer: "not_sure" as const } };
    renderWithI18n(<InvestigationReviewPanel result={result({ investigation_review: review })} />);

    expect(screen.queryByRole("button", { name: "Yes" })).toBeNull();
    expect(screen.getByText("No change: the review stays as it was.")).toBeTruthy();
  });
});

describe("AgronomySources", () => {
  it("renders cards with publisher, region and a safe external link", () => {
    renderWithI18n(<AgronomySources result={result()} />);

    const link = screen.getByRole("link", { name: /Open source/ });
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    expect(screen.getByText("India")).toBeTruthy();
    expect(screen.getByText(/Finding a page does not prove/)).toBeTruthy();
  });

  it("explains why there are no sources", () => {
    const steps = [
      { step: "agronomy_research" as const, provider: "Tavily", model: null, status: "no_results" as const, duration_ms: 900, detail: null, usage: null },
    ];
    renderWithI18n(<AgronomySources result={result({ agronomy_sources: [], integration_status: steps })} />);

    expect(screen.getByText("No relevant official guidance was found for this case.")).toBeTruthy();
  });
});

describe("EvidenceProvenance", () => {
  it("lists each step's provider, model and real status", () => {
    renderWithI18n(<EvidenceProvenance steps={result().integration_status ?? []} />);

    const list = screen.getByRole("list");
    expect(within(list).getByText("Evidence review")).toBeTruthy();
    expect(within(list).getByText(/nemotron-3-super/)).toBeTruthy();
    expect(within(list).getByText("Done")).toBeTruthy();
    expect(within(list).getByText("Not requested")).toBeTruthy();
    expect(within(list).getByText("8.4 s")).toBeTruthy();
  });
});

describe("TriageResult tabs", () => {
  it("adds Review and Sources tabs only when a review exists", () => {
    const { unmount } = renderWithI18n(<TriageResult result={result()} />);
    expect(screen.getByRole("tab", { name: /Review/ })).toBeTruthy();
    expect(screen.getByRole("tab", { name: /Sources/ })).toBeTruthy();
    unmount();

    renderWithI18n(
      <TriageResult
        result={result({ investigation_review: undefined, agronomy_sources: undefined, integration_status: undefined })}
      />,
    );
    expect(screen.getAllByRole("tab")).toHaveLength(2);
    expect(screen.queryByText("How this result was checked")).toBeNull();
  });
});
