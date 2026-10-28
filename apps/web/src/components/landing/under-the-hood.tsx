"use client";

import { motion } from "motion/react";
import {
  CloudSun,
  Languages,
  Library,
  MessageCircleQuestion,
  Mic,
  Satellite,
  ScanSearch,
  Scale,
  ShieldCheck,
  Sprout,
  type LucideIcon,
} from "lucide-react";

import { Reveal, Stagger, StaggerItem } from "@/components/motion/reveal";
import { useI18n, type TranslationKey } from "@/lib/i18n";

const EASE = [0.16, 1, 0.3, 1] as const;

/** Every stage here runs in the API for a real report; the copy must stay true to the code. */
const STAGES: { icon: LucideIcon; key: string }[] = [
  { icon: Sprout, key: "Vision" },
  { icon: ScanSearch, key: "Lesions" },
  { icon: Mic, key: "Voice" },
  { icon: CloudSun, key: "Weather" },
  { icon: Satellite, key: "Satellite" },
  { icon: Scale, key: "Scoring" },
  { icon: ShieldCheck, key: "Guardrails" },
  { icon: Languages, key: "Reach" },
];

const RAIL = ["photo", "crop", "lesions", "voice", "weather", "satellite", "score", "plan", "sources", "review"];

/** Second stage, after scoring: guidance search, then the Nemotron cross-examination. */
const INVESTIGATION: { icon: LucideIcon; key: string; provider: string }[] = [
  { icon: Library, key: "Sources", provider: "Tavily" },
  { icon: MessageCircleQuestion, key: "Review", provider: "NVIDIA Nemotron · Nebius" },
];

function k(stage: string, part: "Tag" | "Title" | "Body" | "Metric"): TranslationKey {
  return `hood${stage}${part}` as TranslationKey;
}

export function UnderTheHood() {
  const { t } = useI18n();
  return (
    <section id="under-the-hood" className="relative scroll-mt-2">
      <div className="relative px-3 py-16 text-mint-100 sm:px-8 sm:py-24">
        <div className="relative mx-auto max-w-6xl">
          <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr] lg:items-end">
            <Reveal onView>
              <p className="label-caps text-mint-300/80">{t("hoodLabel")}</p>
              <h2 className="mt-4 text-4xl leading-[1.02] font-medium tracking-[-0.03em] text-balance sm:text-5xl">
                {t("hoodTitle")}
              </h2>
            </Reveal>
            <Reveal onView delay={0.1}>
              <p className="max-w-md text-mint-200/70 lg:justify-self-end">{t("hoodLead")}</p>
            </Reveal>
          </div>

          {/* The pipeline, left to right, with a pulse travelling along it. */}
          <Reveal onView delay={0.15} className="mt-12">
            <div className="relative overflow-x-auto pb-2 [scrollbar-width:none]">
              <div className="relative flex min-w-max items-center gap-2 font-mono text-[11px] tracking-wider text-mint-200/70 uppercase">
                {RAIL.map((step, i) => (
                  <span key={step} className="flex items-center gap-2">
                    <span className="rounded-full border border-mint-300/20 bg-white/[0.04] px-3 py-1.5">{step}</span>
                    {i < RAIL.length - 1 ? <span className="h-px w-5 bg-mint-300/25 sm:w-8" aria-hidden /> : null}
                  </span>
                ))}
                <motion.span
                  aria-hidden
                  className="pointer-events-none absolute top-1/2 size-2 -translate-y-1/2 rounded-full bg-clay-400 shadow-[0_0_12px_3px_rgba(227,163,95,0.6)]"
                  initial={{ left: "0%" }}
                  animate={{ left: ["0%", "100%"] }}
                  transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}
                />
              </div>
            </div>
          </Reveal>

          <Stagger className="mt-8 grid gap-px overflow-hidden rounded-3xl border border-mint-300/10 bg-mint-300/10 sm:grid-cols-2 lg:grid-cols-4">
            {STAGES.map(({ icon: Icon, key }, index) => (
              <StaggerItem key={key} className="group bg-forest-900 p-6 transition-colors duration-500 hover:bg-forest-800">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[11px] tracking-wider text-mint-300/70 uppercase">
                    {String(index + 1).padStart(2, "0")} · {t(k(key, "Tag"))}
                  </span>
                  <motion.span
                    className="flex size-9 items-center justify-center rounded-full bg-mint-300/10 text-mint-300"
                    whileHover={{ rotate: -8, scale: 1.08 }}
                    transition={{ duration: 0.4, ease: EASE }}
                  >
                    <Icon className="size-4" aria-hidden />
                  </motion.span>
                </div>
                <h3 className="mt-8 text-lg leading-snug font-medium">{t(k(key, "Title"))}</h3>
                <p className="mt-2 text-sm leading-relaxed text-mint-200/65">{t(k(key, "Body"))}</p>
                <p className="mt-5 flex items-center gap-2 font-mono text-[11px] text-clay-400">
                  <span className="size-1.5 rounded-full bg-clay-400" aria-hidden />
                  {t(k(key, "Metric"))}
                </p>
              </StaggerItem>
            ))}
          </Stagger>

          <Reveal onView delay={0.1} className="mt-12 flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
            <p className="label-caps flex items-center gap-2 text-nvidia">
              <span className="size-1.5 rounded-full bg-nvidia" aria-hidden />
              {t("hoodStage2Label")}
            </p>
            <p className="max-w-md text-sm text-mint-200/65">{t("hoodStage2Lead")}</p>
          </Reveal>

          <Stagger className="mt-5 grid gap-px overflow-hidden rounded-3xl border border-nvidia/25 bg-nvidia/20 lg:grid-cols-2">
            {INVESTIGATION.map(({ icon: Icon, key, provider }, index) => (
              <StaggerItem key={key} className="bg-forest-950 p-6 transition-colors duration-500 hover:bg-forest-900 sm:p-8">
                <div className="flex items-center justify-between gap-4">
                  <span className="font-mono text-[11px] tracking-wider text-nvidia uppercase">
                    {String(STAGES.length + index + 1).padStart(2, "0")} · {provider}
                  </span>
                  <motion.span
                    className="flex size-9 shrink-0 items-center justify-center rounded-full bg-nvidia/15 text-nvidia"
                    whileHover={{ rotate: -8, scale: 1.08 }}
                    transition={{ duration: 0.4, ease: EASE }}
                  >
                    <Icon className="size-4" aria-hidden />
                  </motion.span>
                </div>
                <h3 className="mt-8 text-xl leading-snug font-medium text-balance">{t(k(key, "Title"))}</h3>
                <p className="mt-2 max-w-prose text-sm leading-relaxed text-mint-200/65">{t(k(key, "Body"))}</p>
                <p className="mt-5 flex items-center gap-2 font-mono text-[11px] text-nvidia">
                  <span className="size-1.5 rounded-full bg-nvidia" aria-hidden />
                  {t(k(key, "Metric"))}
                </p>
              </StaggerItem>
            ))}
          </Stagger>
        </div>
      </div>
    </section>
  );
}
