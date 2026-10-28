// Mirrors apps/api/app/schemas/triage.py. Keep both in sync (see docs/api-contract.md).

export const CROPS = [
  "rice",
  "wheat",
  "maize",
  "cotton",
  "sugarcane",
  "soybean",
  "groundnut",
  "chickpea",
  "tomato",
  "potato",
  "onion",
  "chilli",
  "other",
] as const;
export type Crop = (typeof CROPS)[number];

export const SYMPTOM_DURATIONS = [
  "less_than_3_days",
  "3_to_7_days",
  "1_to_2_weeks",
  "more_than_2_weeks",
  "not_sure",
] as const;
export type SymptomDuration = (typeof SYMPTOM_DURATIONS)[number];

export type AnalysisMode = "mock" | "ai";
export type ResponseLanguage = "en" | "hi" | "pa" | "es" | "fr";
export type TriageStatus = "completed" | "insufficient_information";
export type UrgencyLevel = "low" | "moderate" | "high" | "critical";
export type ConfidenceLevel = "low" | "medium" | "high";
export type SourceKind =
  | "farmer_report"
  | "photo"
  | "weather"
  | "satellite"
  | "knowledge_base"
  | "analysis_engine"
  | "reference_photos"
  | "investigation_review";
export type EvidenceAvailability = "available" | "unavailable" | "not_integrated";
export type DataSourceStatus =
  | "used"
  | "received_not_analysed"
  | "unavailable"
  | "not_integrated";
export type ActionPriority = "immediate" | "within_days" | "monitor";

export interface Evidence {
  id: string;
  source: SourceKind;
  availability: EvidenceAvailability;
  observation: string;
  observed_at: string | null;
}

export interface PossibleCause {
  name: string;
  condition_key?: string | null;
  explanation: string;
  supporting_evidence: string[];
  contradictory_evidence: string[];
  confidence: ConfidenceLevel;
  uncertainty_note: string;
  analysis_score: number | null;
  weather_score: number | null;
  reference_score?: number | null;
  satellite_score?: number | null;
  evidence_fit_score: number | null;
  evidence_ledger?: EvidenceContribution[];
}

export type EvidenceEffect = "supports" | "weighs_against" | "neutral";

/** Rule-based weather/satellite adjustment to a cause's evidence fit. */
export interface EvidenceContribution {
  signal: "weather" | "satellite";
  effect: EvidenceEffect;
  points: number;
  reason: string;
}

export type WeatherPattern = "wet" | "hot_dry" | "cold" | "humid" | "dry" | "mild";

export interface WeatherFacts {
  days: number;
  start: string;
  end: string;
  temp_min_c: number;
  temp_max_c: number;
  temp_mean_c: number;
  rain_total_mm: number;
  wet_days: number;
  humid_days: number;
  hot_days: number;
  cold_nights: number;
  pattern: WeatherPattern;
}

export interface CropIdentification {
  crop: Crop | null;
  confidence: ConfidenceLevel;
  needs_confirmation: boolean;
  candidates: Crop[];
  image_quality: string;
  reference_agreement: "agrees" | "disagrees" | "not_covered" | "unavailable";
  analysis_mode: AnalysisMode;
}

export type SatelliteStatus =
  | "available"
  | "insufficient_data"
  | "unavailable"
  | "not_configured"
  | "not_requested";
export type VegetationTrend = "improving" | "stable" | "declining" | "unknown";
export type SatelliteLimitation =
  | "approximate_area"
  | "approximate_location"
  | "no_baseline"
  | "single_observation"
  | "partial_coverage"
  | "stale_observation"
  | "low_vegetation";

export interface SatelliteWindow {
  start: string;
  end: string;
  clear_observations: number;
  ndvi_median: number | null;
  ndmi_median: number | null;
}

/** Sentinel-2 vegetation evidence (Google Earth Engine). Supporting evidence, never a diagnosis. */
export interface SatelliteAnalysis {
  status: SatelliteStatus;
  source: string;
  dataset: string;
  analysis_date: string | null;
  sampling_method: "buffer" | "field_boundary" | null;
  buffer_m: number | null;
  sampling_area_ha: number | null;
  ndvi: number | null;
  ndmi: number | null;
  ndvi_change: number | null;
  ndmi_change: number | null;
  trend: VegetationTrend;
  ndmi_trend: VegetationTrend;
  observation_date: string | null;
  observation_age_days: number | null;
  valid_pixel_coverage: number | null;
  recent_window: SatelliteWindow | null;
  baseline_window: SatelliteWindow | null;
  interpretable: boolean;
  limitations: SatelliteLimitation[];
  reason: string | null;
  message: string | null;
  retrieved_at: string | null;
}

export interface MissingInformation {
  item: string;
  reason: string;
}

export interface RecommendedAction {
  action: string;
  rationale: string;
  priority: ActionPriority;
  requires_expert_verification: boolean;
  addresses: string | null;
  analysis_score: number | null;
  weather_score: number | null;
  evidence_fit_score: number | null;
}

export interface DataSource {
  id: string;
  name: string;
  kind: SourceKind;
  status: DataSourceStatus;
  description: string;
  retrieved_at: string | null;
}

export interface TriageResponse {
  report_id: string;
  status: TriageStatus;
  analysis_mode: AnalysisMode;
  response_language: ResponseLanguage;
  crop: Crop | null;
  detected_crop: string | null;
  location_label: string | null;
  approximate_location: string | null;
  weather_summary: string | null;
  weather_facts?: WeatherFacts | null;
  satellite?: SatelliteAnalysis | null;
  reference_weight?: number | null;
  summary: string;
  urgency: UrgencyLevel;
  urgency_reason: string;
  possible_causes: PossibleCause[];
  evidence: Evidence[];
  missing_information: MissingInformation[];
  recommended_actions: RecommendedAction[];
  requires_expert_review: boolean;
  generated_at: string;
  data_sources: DataSource[];
  disclaimer: string;
  /** NVIDIA Nemotron review of the evidence ledger. Absent on older results. */
  investigation_review?: InvestigationReview | null;
  /** Validated pages from approved agricultural publishers (Tavily search). */
  agronomy_sources?: AgronomySource[];
  /** What each provider actually did for this report. */
  integration_status?: IntegrationStep[];
}

export type IntegrationStepName =
  | "image_analysis"
  | "weather"
  | "satellite"
  | "reference_photos"
  | "deterministic_scoring"
  | "agronomy_research"
  | "nemotron_review"
  | "translation";
export type IntegrationStatus =
  | "success"
  | "no_results"
  | "unavailable"
  | "failed"
  | "timeout"
  | "skipped"
  | "not_requested"
  | "not_configured"
  | "disabled";

export interface UsageInfo {
  prompt_tokens: number | null;
  completion_tokens: number | null;
  credits: number | null;
}

export interface IntegrationStep {
  step: IntegrationStepName;
  provider: string;
  model: string | null;
  status: IntegrationStatus;
  duration_ms: number | null;
  detail: string | null;
  usage: UsageInfo | null;
}

/** A validated page from an approved publisher. Retrieval alone does not verify its advice. */
export interface AgronomySource {
  id: string;
  title: string;
  url: string;
  publisher: string;
  domain: string;
  region: string;
  retrieved_at: string;
  published_at: string | null;
  excerpt: string;
  crop_relevance: boolean;
  condition_relevance: boolean;
  condition_keys: string[];
  validation_status: "validated";
}

export type ReviewStatus = "completed" | "unavailable" | "not_configured" | "disabled" | "skipped";
export type EvidenceConsistency = "consistent" | "mixed" | "inconsistent" | "insufficient";
export type SupportStatus = "source_backed" | "unverified" | "model_suggestion" | "safety_referral";
export type FollowUpAnswer = "yes" | "no" | "not_sure";
export type FollowUpCategory =
  | "symptom_distribution"
  | "visible_pattern"
  | "duration"
  | "field_conditions"
  | "plant_part";

export interface ReviewedObservation {
  text: string;
  evidence_ids: string[];
  condition_key: string | null;
}

export interface KnowledgeFinding {
  claim: string;
  source_ids: string[];
  applicability: string;
  support_status: SupportStatus;
  verified: boolean;
}

export interface SafeNextStep {
  action: string;
  rationale: string;
  priority: ActionPriority;
  source_ids: string[];
  requires_expert_review: boolean;
  support_status: SupportStatus;
}

export interface FollowUpQuestion {
  id: string;
  text: string;
  category: FollowUpCategory;
  discriminates: string[];
  why: string;
  options: FollowUpAnswer[];
  answer: FollowUpAnswer | null;
}

/** Second-stage review. It never changes scores, ranking or urgency. */
export interface InvestigationReview {
  status: ReviewStatus;
  provider: string;
  model: string;
  detail: string | null;
  generated_at: string | null;
  duration_ms: number | null;
  usage: UsageInfo | null;
  language: string;
  round: number;
  grounding: "sources_and_evidence" | "internal_evidence_only" | null;
  leading_condition_key: string | null;
  reasoning_summary: string;
  evidence_consistent: EvidenceConsistency | null;
  supporting_observations: ReviewedObservation[];
  contradictions: ReviewedObservation[];
  unresolved_questions: string[];
  follow_up_question: FollowUpQuestion | null;
  knowledge_findings: KnowledgeFinding[];
  safe_next_steps: SafeNextStep[];
  limitations: string[];
  source_ids: string[];
  guardrail_notes: string[];
  previous_summary: string | null;
  what_changed: string[];
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: { field: string | null; message: string }[];
  };
}
