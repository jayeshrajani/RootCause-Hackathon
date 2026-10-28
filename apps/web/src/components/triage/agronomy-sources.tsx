"use client";

import { ExternalLink, Globe2, Library } from "lucide-react";

import { safeHref } from "@/components/triage/display";
import { useI18n, type TranslationKey } from "@/lib/i18n";
import type { IntegrationStatus, TriageResponse } from "@/types/triage";

const EMPTY_KEYS: Partial<Record<IntegrationStatus, TranslationKey>> = {
  no_results: "sourcesNone",
  unavailable: "sourcesUnavailable",
  failed: "sourcesUnavailable",
  timeout: "sourcesUnavailable",
  not_configured: "sourcesNotConfigured",
  disabled: "sourcesNotConfigured",
  skipped: "sourcesSkipped",
};

/** Validated pages from approved publishers. Retrieval is not verification. */
export function AgronomySources({ result }: { result: TriageResponse }) {
  const { language, t } = useI18n();
  const sources = result.agronomy_sources ?? [];
  const step = result.integration_status?.find((item) => item.step === "agronomy_research");
  const dateFormat = new Intl.DateTimeFormat(language, { dateStyle: "medium" });

  if (!sources.length) {
    return (
      <div className="flex items-start gap-3 rounded-2xl bg-forest-900/[0.05] px-4 py-4 text-sm">
        <Library className="mt-0.5 size-4 shrink-0 text-forest-700" aria-hidden />
        <p>{t((step && EMPTY_KEYS[step.status]) ?? "sourcesNone")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h3 className="text-lg font-medium">{t("sourcesTitle")}</h3>
        <p className="text-sm text-muted-foreground">{t("sourcesIntro")}</p>
      </header>

      <ol className="space-y-3">
        {sources.map((source) => {
          const href = safeHref(source.url);
          return (
            <li key={source.id} className="space-y-2.5 rounded-2xl border border-forest-900/10 bg-card p-4 sm:p-5">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
                <span className="rounded-full bg-forest-900 px-2 py-0.5 font-mono text-mint-100">{source.id}</span>
                <span className="label-caps text-forest-700">{source.publisher}</span>
                <span className="inline-flex items-center gap-1 rounded-full bg-forest-900/[0.06] px-2 py-0.5 text-forest-800">
                  <Globe2 className="size-3" aria-hidden />
                  {source.region}
                </span>
                {source.published_at ? (
                  <span className="text-muted-foreground">
                    {t("sourcesPublished")} {dateFormat.format(new Date(`${source.published_at}T00:00:00`))}
                  </span>
                ) : null}
              </div>
              <p className="leading-snug font-medium">{source.title}</p>
              <blockquote className="border-l-2 border-mint-300 pl-3 text-sm leading-relaxed text-forest-900/80">
                {source.excerpt}
              </blockquote>
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <span className="truncate font-mono text-muted-foreground">{source.domain}</span>
                {href ? (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex min-h-9 items-center gap-1.5 rounded-full bg-forest-900 px-3.5 font-medium text-mint-100 transition hover:bg-forest-800 focus-visible:ring-2 focus-visible:ring-forest-900 focus-visible:ring-offset-2 focus-visible:outline-none"
                  >
                    {t("sourcesOpen")}
                    <ExternalLink className="size-3.5" aria-hidden />
                  </a>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>

      <div className="space-y-1 text-xs text-muted-foreground">
        <p>{t("sourcesRegionNote")}</p>
        {result.response_language !== "en" ? <p>{t("sourcesOriginalLanguage")}</p> : null}
      </div>
    </div>
  );
}
