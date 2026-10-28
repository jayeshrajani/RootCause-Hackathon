import {
  Camera,
  CloudSun,
  Cpu,
  FileText,
  Images,
  Languages,
  Library,
  Satellite,
  Scale,
  ScanSearch,
  type LucideIcon,
} from "lucide-react";

import type { TranslationKey } from "@/lib/i18n";
import type {
  ActionPriority,
  ConfidenceLevel,
  DataSourceStatus,
  EvidenceAvailability,
  IntegrationStatus,
  IntegrationStepName,
  SourceKind,
  UrgencyLevel,
} from "@/types/triage";

export const URGENCY_DISPLAY: Record<
  UrgencyLevel,
  { label: string; level: number; advice: string; bar: string; text: string }
> = {
  low: { label: "Low", level: 1, advice: "Keep monitoring.", bar: "bg-mint-300", text: "text-mint-300" },
  moderate: {
    label: "Moderate",
    level: 2,
    advice: "Act within the next few days.",
    bar: "bg-clay-400",
    text: "text-clay-400",
  },
  high: { label: "High", level: 3, advice: "Act as soon as possible.", bar: "bg-clay-500", text: "text-clay-400" },
  critical: { label: "Critical", level: 4, advice: "Seek expert help today.", bar: "bg-red-400", text: "text-red-300" },
};

export const CONFIDENCE_DISPLAY: Record<ConfidenceLevel, { label: string; level: number }> = {
  low: { label: "Low confidence", level: 1 },
  medium: { label: "Medium confidence", level: 2 },
  high: { label: "High confidence", level: 3 },
};

export const PRIORITY_DISPLAY: Record<ActionPriority, { label: string; order: number; dot: string }> = {
  immediate: { label: "Now", order: 0, dot: "bg-clay-500" },
  within_days: { label: "Next few days", order: 1, dot: "bg-clay-400" },
  monitor: { label: "Keep watching", order: 2, dot: "bg-forest-500" },
};

export const SOURCE_DISPLAY: Record<SourceKind, { label: string; icon: LucideIcon }> = {
  farmer_report: { label: "Your report", icon: FileText },
  photo: { label: "Photos", icon: Camera },
  weather: { label: "Weather", icon: CloudSun },
  satellite: { label: "Satellite", icon: Satellite },
  knowledge_base: { label: "Agricultural guidance", icon: Library },
  analysis_engine: { label: "Analysis engine", icon: Cpu },
  reference_photos: { label: "Reference photos", icon: Images },
  investigation_review: { label: "Evidence review", icon: ScanSearch },
};

export const SOURCE_LABEL_KEYS: Record<SourceKind, TranslationKey> = {
  farmer_report: "sourceYourReport",
  photo: "sourcePhotos",
  weather: "sourceWeather",
  satellite: "sourceSatellite",
  knowledge_base: "sourceGuidance",
  analysis_engine: "sourceEngine",
  reference_photos: "sourceReferences",
  investigation_review: "sourceReview",
};

export const STEP_DISPLAY: Record<IntegrationStepName, { key: TranslationKey; icon: LucideIcon }> = {
  image_analysis: { key: "stepImage", icon: Camera },
  weather: { key: "stepWeather", icon: CloudSun },
  satellite: { key: "stepSatellite", icon: Satellite },
  reference_photos: { key: "stepReferences", icon: Images },
  deterministic_scoring: { key: "stepScoring", icon: Scale },
  agronomy_research: { key: "stepResearch", icon: Library },
  nemotron_review: { key: "stepReview", icon: ScanSearch },
  translation: { key: "stepTranslation", icon: Languages },
};

export const STEP_STATUS_DISPLAY: Record<IntegrationStatus, { key: TranslationKey; dot: string }> = {
  success: { key: "statusSuccess", dot: "bg-forest-600" },
  no_results: { key: "statusNoResults", dot: "bg-clay-400" },
  unavailable: { key: "statusUnavailable", dot: "bg-destructive" },
  failed: { key: "statusFailed", dot: "bg-destructive" },
  timeout: { key: "statusTimeout", dot: "bg-destructive" },
  skipped: { key: "statusSkipped", dot: "bg-forest-900/20" },
  not_requested: { key: "statusNotRequested", dot: "bg-forest-900/20" },
  not_configured: { key: "statusNotConfigured", dot: "bg-forest-900/20" },
  disabled: { key: "statusDisabled", dot: "bg-forest-900/20" },
};

/** External links only for HTTPS URLs (the API already validates them; this is defence in depth). */
export function safeHref(url: string): string | null {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && !parsed.username && !parsed.password ? parsed.href : null;
  } catch {
    return null;
  }
}

export const AVAILABILITY_DISPLAY: Record<EvidenceAvailability, { label: string; className: string }> = {
  available: { label: "Observed", className: "bg-forest-900 text-mint-100" },
  unavailable: { label: "Unavailable", className: "bg-destructive/10 text-destructive" },
  not_integrated: { label: "Not connected yet", className: "bg-forest-900/[0.06] text-forest-900/60" },
};

export const DATA_SOURCE_STATUS_DISPLAY: Record<DataSourceStatus, { label: string; dot: string }> = {
  used: { label: "Used", dot: "bg-forest-600" },
  received_not_analysed: { label: "Received, not analysed", dot: "bg-clay-400" },
  unavailable: { label: "Unavailable", dot: "bg-destructive" },
  not_integrated: { label: "Not connected yet", dot: "bg-forest-900/20" },
};

export function formatTimestamp(iso: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(iso),
  );
}
