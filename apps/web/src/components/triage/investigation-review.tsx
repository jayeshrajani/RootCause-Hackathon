"use client";

import type { ReactNode } from "react";
import {
  CircleHelp,
  History,
  Info,
  ListChecks,
  ScanSearch,
  ShieldAlert,
  ShieldCheck,
  ThumbsDown,
  ThumbsUp,
  type LucideIcon,
} from "lucide-react";

import { safeHref, SOURCE_DISPLAY, SOURCE_LABEL_KEYS } from "@/components/triage/display";
import { FollowUpQuestionCard } from "@/components/triage/follow-up-question";
import { useI18n, type TranslationKey } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type {
  AgronomySource,
  EvidenceConsistency,
  InvestigationReview,
  ReviewedObservation,
  ReviewStatus,
  SourceKind,
  SupportStatus,
  TriageResponse,
} from "@/types/triage";

const CONSISTENCY_KEYS: Record<EvidenceConsistency, TranslationKey> = {
  consistent: "reviewConsistent",
  mixed: "reviewMixed",
  inconsistent: "reviewInconsistent",
  insufficient: "reviewInsufficient",
};

const NOT_RUN_KEYS: Record<Exclude<ReviewStatus, "completed">, TranslationKey> = {
  unavailable: "reviewUnavailableTitle",
  not_configured: "reviewNotConfiguredTitle",
  skipped: "reviewSkippedTitle",
  disabled: "reviewDisabledTitle",
};

export const SUPPORT_DISPLAY: Record<SupportStatus, { key: TranslationKey; className: string }> = {
  source_backed: { key: "supportSourceBacked", className: "bg-forest-900 text-mint-100" },
  unverified: { key: "supportUnverified", className: "bg-clay-400/15 text-clay-600" },
  model_suggestion: { key: "supportModel", className: "bg-forest-900/[0.06] text-forest-800" },
  safety_referral: { key: "supportReferral", className: "bg-clay-400/15 text-clay-600" },
};

function Block({ icon: Icon, title, children }: { icon: LucideIcon; title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="label-caps flex items-center gap-1.5 text-forest-700">
        <Icon className="size-3.5" aria-hidden />
        {title}
      </h3>
      {children}
    </section>
  );
}

function SupportBadge({ status }: { status: SupportStatus }) {
  const { t } = useI18n();
  const display = SUPPORT_DISPLAY[status];
  return <span className={cn("rounded-full px-2.5 py-1 text-xs", display.className)}>{t(display.key)}</span>;
}

export function SourceChip({ source }: { source: AgronomySource }) {
  const href = safeHref(source.url);
  const label = `${source.id} · ${source.publisher}`;
  const className = "inline-flex max-w-full items-center rounded-full bg-mint-100 px-2.5 py-1 text-xs text-forest-700";
  return href ? (
    <a href={href} target="_blank" rel="noopener noreferrer" className={cn(className, "underline-offset-2 hover:underline")}>
      <span className="truncate">{label}</span>
      <span aria-hidden>&nbsp;↗</span>
    </a>
  ) : (
    <span className={className}>{label}</span>
  );
}

function ObservationList({
  items,
  kinds,
  tone,
}: {
  items: ReviewedObservation[];
  kinds: Map<string, SourceKind>;
  tone: "supports" | "against";
}) {
  const { t } = useI18n();
  return (
    <ul className="space-y-2">
      {items.map((item) => {
        const sources = [...new Set(item.evidence_ids.map((id) => kinds.get(id)).filter((k) => k !== undefined))];
        return (
          <li key={item.text} className="flex gap-2.5 text-sm leading-snug">
            <span
              className={cn("mt-[7px] size-1.5 shrink-0 rounded-full", tone === "supports" ? "bg-forest-600" : "bg-clay-500")}
              aria-hidden
            />
            <span className="min-w-0 space-y-1">
              <span className="block">{item.text}</span>
              {sources.length ? (
                <span className="flex flex-wrap gap-1">
                  {sources.map((kind) => {
                    const Icon = SOURCE_DISPLAY[kind].icon;
                    return (
                      <span key={kind} className="inline-flex items-center gap-1 rounded-full bg-forest-900/[0.06] px-2 py-0.5 text-[11px] text-forest-800">
                        <Icon className="size-3" aria-hidden />
                        {t(SOURCE_LABEL_KEYS[kind])}
                      </span>
                    );
                  })}
                </span>
              ) : null}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function NotRun({ review }: { review: InvestigationReview }) {
  const { t } = useI18n();
  const failed = review.status === "unavailable";
  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-2xl px-4 py-4 text-sm",
        failed ? "border border-clay-400/40 bg-clay-400/10" : "bg-forest-900/[0.05]",
      )}
    >
      <Info className={cn("mt-0.5 size-4 shrink-0", failed ? "text-clay-600" : "text-forest-700")} aria-hidden />
      <div className="space-y-1">
        <p className="font-medium">{t(NOT_RUN_KEYS[review.status as Exclude<ReviewStatus, "completed">])}</p>
        {review.detail ? <p className="text-muted-foreground">{review.detail}</p> : null}
        <p className="text-muted-foreground">{t("reviewTriageUnchanged")}</p>
      </div>
    </div>
  );
}

/** NVIDIA Nemotron's second look at the evidence. Kept apart from the scored triage it reviews. */
export function InvestigationReviewPanel({ result }: { result: TriageResponse }) {
  const { t } = useI18n();
  const review = result.investigation_review;
  if (!review) return null;
  if (review.status !== "completed") return <NotRun review={review} />;

  const sources = new Map((result.agronomy_sources ?? []).map((source) => [source.id, source]));
  const kinds = new Map(result.evidence.map((item) => [item.id, item.source]));
  const grounded = review.grounding === "sources_and_evidence";
  const shownInEnglish = review.language === "en" && result.response_language !== "en";

  return (
    <div className="space-y-6">
      <header className="space-y-3 rounded-2xl border border-forest-900/10 bg-card p-4 sm:p-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 text-sm font-medium text-forest-800">
            <ScanSearch className="size-4" aria-hidden />
            {t("reviewBy")}
          </span>
          {review.evidence_consistent ? (
            <span className="rounded-full bg-forest-900/[0.06] px-2.5 py-1 text-xs text-forest-800">
              {t(CONSISTENCY_KEYS[review.evidence_consistent])}
            </span>
          ) : null}
        </div>
        <p
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs",
            grounded ? "bg-mint-100 text-forest-700" : "bg-clay-400/15 text-clay-600",
          )}
        >
          {grounded ? <ShieldCheck className="size-3.5" aria-hidden /> : <ShieldAlert className="size-3.5" aria-hidden />}
          {t(grounded ? "reviewGroundedSources" : "reviewGroundedInternal")}
        </p>
        <p className="leading-relaxed">{review.reasoning_summary}</p>
        {shownInEnglish ? <p className="text-xs text-muted-foreground">{t("reviewInEnglish")}</p> : null}
      </header>

      {review.round > 1 && review.what_changed.length ? (
        <Block icon={History} title={t("reviewChanged")}>
          <ul className="space-y-1.5 text-sm">
            {review.what_changed.map((line) => (
              <li key={line} className="flex gap-2.5">
                <span className="mt-[7px] size-1.5 shrink-0 rounded-full bg-mint-300" aria-hidden />
                {line}
              </li>
            ))}
          </ul>
          {review.previous_summary ? (
            <details className="text-sm text-muted-foreground">
              <summary className="cursor-pointer">{t("reviewEarlier")}</summary>
              <p className="mt-1">{review.previous_summary}</p>
            </details>
          ) : null}
        </Block>
      ) : null}

      {review.supporting_observations.length ? (
        <Block icon={ThumbsUp} title={t("reviewSupports")}>
          <ObservationList items={review.supporting_observations} kinds={kinds} tone="supports" />
        </Block>
      ) : null}

      {review.contradictions.length ? (
        <Block icon={ThumbsDown} title={t("reviewContradicts")}>
          <ObservationList items={review.contradictions} kinds={kinds} tone="against" />
        </Block>
      ) : null}

      {review.follow_up_question ? (
        <FollowUpQuestionCard result={result} question={review.follow_up_question} />
      ) : null}

      {review.unresolved_questions.length || review.limitations.length ? (
        <Block icon={CircleHelp} title={t("reviewUnclear")}>
          <ul className="space-y-1.5 text-sm text-muted-foreground">
            {[...review.unresolved_questions, ...review.limitations].map((line) => (
              <li key={line} className="flex gap-2.5">
                <span className="mt-[7px] size-1 shrink-0 rounded-full bg-forest-900/30" aria-hidden />
                {line}
              </li>
            ))}
          </ul>
        </Block>
      ) : null}

      {review.safe_next_steps.length ? (
        <Block icon={ListChecks} title={t("reviewNextSteps")}>
          <ol className="space-y-2.5">
            {review.safe_next_steps.map((step) => (
              <li key={step.action} className="space-y-1.5 rounded-2xl border border-forest-900/10 bg-card p-4">
                <p className="leading-snug font-medium">{step.action}</p>
                <p className="text-sm text-muted-foreground">{step.rationale}</p>
                <div className="flex flex-wrap gap-1.5 pt-1">
                  <SupportBadge status={step.support_status} />
                  {step.source_ids.map((id) => {
                    const source = sources.get(id);
                    return source ? <SourceChip key={id} source={source} /> : null;
                  })}
                  {step.requires_expert_review ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-clay-400/15 px-2.5 py-1 text-xs text-clay-600">
                      <ShieldAlert className="size-3" aria-hidden />
                      {t("expertCheck")}
                    </span>
                  ) : null}
                </div>
              </li>
            ))}
          </ol>
        </Block>
      ) : null}

      {review.knowledge_findings.length ? (
        <Block icon={ShieldCheck} title={t("reviewGuidance")}>
          <ul className="space-y-2.5">
            {review.knowledge_findings.map((finding) => (
              <li key={finding.claim} className="space-y-1.5 rounded-2xl bg-mint-100/50 p-4 text-sm">
                <p className="leading-snug">{finding.claim}</p>
                {finding.applicability ? <p className="text-muted-foreground">{finding.applicability}</p> : null}
                <div className="flex flex-wrap gap-1.5 pt-1">
                  <SupportBadge status={finding.support_status} />
                  {finding.source_ids.map((id) => {
                    const source = sources.get(id);
                    return source ? <SourceChip key={id} source={source} /> : null;
                  })}
                </div>
              </li>
            ))}
          </ul>
        </Block>
      ) : null}

      {review.guardrail_notes.length ? (
        <details className="rounded-2xl bg-forest-900/[0.04] px-4 py-3 text-sm">
          <summary className="cursor-pointer font-medium">
            {t("reviewSafetyRemoved")} ({review.guardrail_notes.length})
          </summary>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-muted-foreground">
            {review.guardrail_notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </details>
      ) : null}

      <p className="border-t border-forest-900/10 pt-3 text-xs text-muted-foreground">
        {t("reviewCannotChange")}{" "}
        <span className="font-mono">
          {review.model}
          {review.duration_ms !== null ? ` · ${(review.duration_ms / 1000).toFixed(1)} s` : ""}
        </span>
      </p>
    </div>
  );
}
