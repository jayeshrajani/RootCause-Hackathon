"use client";

import { useState } from "react";
import { CircleHelp, LoaderCircle } from "lucide-react";

import { ApiError, answerFollowUp } from "@/lib/api/client";
import { useI18n, type TranslationKey } from "@/lib/i18n";
import { replaceLatestTriage } from "@/lib/triage-storage";
import { cn } from "@/lib/utils";
import type { FollowUpAnswer, FollowUpQuestion, TriageResponse } from "@/types/triage";

const ANSWER_KEYS: Record<FollowUpAnswer, TranslationKey> = {
  yes: "followUpYes",
  no: "followUpNo",
  not_sure: "followUpNotSure",
};

type SendState = "idle" | "sending" | "failed" | "expired";

/** Nemotron's one question that best separates the leading causes. */
export function FollowUpQuestionCard({
  result,
  question,
}: {
  result: TriageResponse;
  question: FollowUpQuestion;
}) {
  const { t } = useI18n();
  const [state, setState] = useState<SendState>("idle");
  const answered = question.answer;

  const send = async (answer: FollowUpAnswer) => {
    setState("sending");
    try {
      replaceLatestTriage(await answerFollowUp(result.report_id, question.id, answer));
      setState("idle");
    } catch (error) {
      const status = error instanceof ApiError ? error.status : undefined;
      setState(status === 410 || status === 409 ? "expired" : "failed");
    }
  };

  return (
    <section
      aria-labelledby={`follow-up-${question.id}`}
      className="rounded-2xl border border-clay-400/40 bg-clay-400/[0.07] p-4 sm:p-5"
    >
      <p className="label-caps flex items-center gap-1.5 text-clay-600">
        <CircleHelp className="size-3.5" aria-hidden />
        {t("followUpTitle")}
      </p>
      <h3 id={`follow-up-${question.id}`} className="mt-2 text-lg leading-snug font-medium">
        {question.text}
      </h3>
      {question.why ? <p className="mt-1 text-sm text-muted-foreground">{question.why}</p> : null}

      {answered ? (
        <div className="mt-3 space-y-1 text-sm">
          <p>
            <span className="text-muted-foreground">{t("followUpAnswered")}</span>{" "}
            <span className="font-medium">{t(ANSWER_KEYS[answered])}</span>
          </p>
          {answered === "not_sure" ? <p className="text-muted-foreground">{t("followUpNotSureNote")}</p> : null}
        </div>
      ) : (
        <>
          <div className="mt-4 flex flex-wrap gap-2" role="group" aria-label={question.text}>
            {question.options.map((option) => (
              <button
                key={option}
                type="button"
                disabled={state === "sending" || state === "expired" || result.analysis_mode !== "ai"}
                onClick={() => void send(option)}
                className={cn(
                  "inline-flex min-h-10 items-center rounded-full px-4 text-sm font-medium transition",
                  "focus-visible:ring-2 focus-visible:ring-forest-900 focus-visible:ring-offset-2 focus-visible:outline-none",
                  "disabled:cursor-not-allowed disabled:opacity-50",
                  option === "not_sure"
                    ? "bg-forest-900/[0.06] text-forest-900 hover:bg-forest-900/10"
                    : "bg-forest-900 text-mint-100 hover:bg-forest-800",
                )}
              >
                {t(ANSWER_KEYS[option])}
              </button>
            ))}
          </div>
          <p className="mt-3 text-xs text-muted-foreground" role="status" aria-live="polite">
            {state === "sending" ? (
              <span className="inline-flex items-center gap-1.5">
                <LoaderCircle className="size-3.5 animate-spin" aria-hidden />
                {t("followUpUpdating")}
              </span>
            ) : state === "failed" ? (
              <span className="text-destructive">{t("followUpFailed")}</span>
            ) : state === "expired" ? (
              <span className="text-destructive">{t("followUpExpired")}</span>
            ) : (
              t("followUpScoresNote")
            )}
          </p>
        </>
      )}
    </section>
  );
}
