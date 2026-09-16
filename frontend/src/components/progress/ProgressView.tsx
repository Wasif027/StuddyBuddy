"use client";

import { useEffect } from "react";

import type { CategoryProgress, SetTrendPoint } from "@/lib/types";
import { useStudyStore } from "@/store/useStudyStore";
import { ScoreBar } from "@/components/ui/ScoreBar";
import {
  Books,
  ChartLineUp,
  ClockCounterClockwise,
  Exam,
  Target,
  type Icon,
} from "@/components/ui/icons";

const pct = (n: number) => `${Math.round(n * 100)}%`;
const TIER_ORDER = ["easy", "medium", "hard", "brutal"] as const;
const TIER_LABEL: Record<string, string> = { easy: "easy", medium: "medium", hard: "hard", brutal: "very hard" };

export function ProgressView() {
  const p = useStudyStore((s) => s.progress);
  const loading = useStudyStore((s) => s.loadingProgress);
  const load = useStudyStore((s) => s.loadProgress);
  const generate = useStudyStore((s) => s.generatePracticeSet);

  useEffect(() => {
    load();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading && !p) {
    return (
      <div className="mx-auto w-full max-w-3xl space-y-3 px-5 py-8">
        <div className="skeleton h-24" />
        <div className="skeleton h-40" />
      </div>
    );
  }

  if (!p || p.totalSets === 0) {
    return (
      <div className="mx-auto w-full max-w-3xl px-5 py-8">
        <h1 className="text-xl font-semibold tracking-tight text-content-primary">Progress</h1>
        <div className="mt-6 rounded-xl border border-dashed border-line px-4 py-12 text-center">
          <ChartLineUp className="mx-auto h-7 w-7 text-content-muted" />
          <p className="mt-2 text-sm font-medium text-content-secondary">Nothing to chart yet</p>
          <p className="mt-1 text-2xs text-content-muted">
            Make a practice set and your scores, streak and per-subject trend show up here.
          </p>
          <button onClick={() => generate({ topic: "a topic you choose" })} className="btn btn-accent mt-4 h-8 px-4 text-xs">
            <Exam className="h-3.5 w-3.5" /> Make a practice set
          </button>
        </div>
      </div>
    );
  }

  const overallPct = p.totalQuestions ? p.totalCorrect / p.totalQuestions : 0;

  return (
    <div className="mx-auto w-full max-w-3xl px-5 py-8">
      <h1 className="text-xl font-semibold tracking-tight text-content-primary">Progress</h1>

      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Tile
          icon={Target}
          label="Overall"
          value={`${p.totalCorrect}/${p.totalQuestions}`}
          sub={`${pct(overallPct)} correct`}
        />
        <Tile icon={ClockCounterClockwise} label="Streak" value={`${p.currentStreak}d`} sub={`best ${p.longestStreak}d`} />
        <Tile icon={Exam} label="Sets" value={String(p.totalSets)} sub={`${p.incompleteSets} incomplete`} />
        <Tile icon={Books} label="Materials" value={String(p.documents)} sub={`${p.notes} notes`} />
      </div>

      {Object.keys(p.byTier).length > 0 && (
        <section className="card mt-5 space-y-2 p-4">
          <p className="label mb-1">By difficulty</p>
          {TIER_ORDER.map((t) =>
            p.byTier[t] != null ? <ScoreBar key={t} label={TIER_LABEL[t]} score={p.byTier[t]} /> : null,
          )}
        </section>
      )}

      {p.byCategory.length > 0 && (
        <section className="mt-5 space-y-3">
          <p className="label px-1">Subjects</p>
          {p.byCategory.map((c) => (
            <SubjectCard key={c.category} c={c} />
          ))}
        </section>
      )}
    </div>
  );
}

function SubjectCard({ c }: { c: CategoryProgress }) {
  return (
    <div className="card space-y-2.5 p-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-content-primary">{c.label}</span>
        <span className="text-2xs text-content-muted">
          {c.totalSets} {c.totalSets === 1 ? "set" : "sets"} · {c.solvedSets} solved · {c.docCount}{" "}
          {c.docCount === 1 ? "material" : "materials"}
        </span>
      </div>

      {c.trend.length > 1 && <SetSparkline points={c.trend} />}

      {TIER_ORDER.some((t) => c.byTier[t] != null) && (
        <div className="space-y-1.5 border-t border-line pt-2.5">
          {TIER_ORDER.map((t) =>
            c.byTier[t] != null ? <ScoreBar key={t} label={TIER_LABEL[t]} score={c.byTier[t]} /> : null,
          )}
        </div>
      )}
    </div>
  );
}

function Tile({
  icon: I,
  label,
  value,
  sub,
}: {
  icon: Icon;
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-xl border border-line bg-surface-raised p-3.5">
      <p className="flex items-center gap-1.5 text-2xs font-medium uppercase tracking-wide text-content-muted">
        <I className="h-3 w-3" /> {label}
      </p>
      <p className="mt-1.5 text-xl font-semibold tracking-tight text-content-primary">{value}</p>
      {sub && <p className="text-2xs text-content-muted">{sub}</p>}
    </div>
  );
}

/** One accuracy line per practice set in a subject, chronological. A set
 * with zero answered questions is a real 0% point — it isn't skipped. */
function SetSparkline({ points }: { points: SetTrendPoint[] }) {
  const w = 100;
  const h = 34;
  const xs = points.map((_, i) => (i / (points.length - 1)) * w);
  const ys = points.map((p) => h - p.accuracy * h);
  const d = xs.map((x, i) => `${i ? "L" : "M"}${x.toFixed(1)} ${ys[i].toFixed(1)}`).join(" ");
  return (
    <div>
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="h-14 w-full">
        <path d={`${d} L${w} ${h} L0 ${h} Z`} fill="rgb(var(--accent) / 0.12)" stroke="none" />
        <path d={d} fill="none" stroke="rgb(var(--accent))" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="mt-1 flex justify-between text-[0.58rem] text-content-muted">
        <span>
          set 1 · {points[0].correct}/{points[0].total}
        </span>
        <span>
          set {points.length} · {points[points.length - 1].correct}/{points[points.length - 1].total}
        </span>
      </div>
    </div>
  );
}
