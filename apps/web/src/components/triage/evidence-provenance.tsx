"use client";

import { STEP_DISPLAY, STEP_STATUS_DISPLAY } from "@/components/triage/display";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { IntegrationStep } from "@/types/triage";

/** Which providers actually ran for this report, with their real outcome. */
export function EvidenceProvenance({ steps: allSteps }: { steps: IntegrationStep[] }) {
  const { t } = useI18n();
  // Results stored before this change may still carry an unused reference-photos step.
  const steps = allSteps.filter((step) => step.step !== "reference_photos" || step.status === "success");
  if (!steps.length) return null;

  return (
    <section
      aria-labelledby="provenance-title"
      className="mt-8 rounded-[24px] border border-forest-900/10 bg-card p-5 sm:p-6"
    >
      <h2 id="provenance-title" className="text-lg font-medium">
        {t("provenanceTitle")}
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">{t("provenanceNote")}</p>
      <ol className="mt-4 divide-y divide-forest-900/10">
        {steps.map((step) => {
          const display = STEP_DISPLAY[step.step];
          const status = STEP_STATUS_DISPLAY[step.status];
          const Icon = display.icon;
          return (
            <li key={step.step} className="grid grid-cols-[2rem_1fr_auto] items-start gap-3 py-3">
              <span className="flex size-8 items-center justify-center rounded-full bg-mint-100 text-forest-700">
                <Icon className="size-4" aria-hidden />
              </span>
              <div className="min-w-0">
                <p className="text-sm font-medium">{t(display.key)}</p>
                <p className="truncate text-xs text-muted-foreground">
                  {step.provider}
                  {step.model ? <span className="font-mono"> · {step.model}</span> : null}
                </p>
                {step.detail ? <p className="mt-1 text-xs text-forest-900/70">{step.detail}</p> : null}
              </div>
              <div className="flex flex-col items-end gap-1 text-xs">
                <span className="flex items-center gap-1.5 whitespace-nowrap">
                  <span className={cn("size-1.5 rounded-full", status.dot)} aria-hidden />
                  {t(status.key)}
                </span>
                {step.duration_ms !== null ? (
                  <span className="font-mono text-muted-foreground">
                    {(step.duration_ms / 1000).toFixed(1)} s
                  </span>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
