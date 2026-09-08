"use client";

import { useEffect } from "react";

import type { SkillStat, TrendPoint } from "@/lib/types";
import { cn } from "@/lib/utils";
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

  if (!p || p.totalAttempts === 0) {
    return (
      <div className="mx-auto w-full max-w-3xl px-5 py-8">
        <h1 className="text-xl font-semibold tracking-tight text-content-primary">Progress</h1>
        <div className="mt-6 rounded-xl border border-dashed border-line px-4 py-12 text-center">
          <ChartLineUp className="mx-auto h-7 w-7 text-content-muted" />
          <p className="mt-2 text-sm font-medium text-content-secondary">Nothing to chart yet</p>
          <p className="mt-1 text-2xs text-content-muted">
            Answer a practice set and your scores, streak and weak topics show up here.
          </p>
          <button onClick={() => generate({ topic: "a topic you choose" })} className="btn btn-accent mt-4 h-8 px-4 text-xs">
            <Exam className="h-3.5 w-3.5" /> Make a practice set
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-5 py-8">
      <h1 className="text-xl font-semibold tracking-tight text-content-primary">Progress</h1>

      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Tile icon={Target} label="Overall" value={pct(p.overallAccuracy)} sub={`${p.totalAttempts} answered`} />
        <Tile icon={ClockCounterClockwise} label="Streak" value={`${p.currentStreak}d`} sub={`best ${p.longestStreak}d`} />
        <Tile icon={Exam} label="Sets" value={String(p.practiceSets)} />
        <Tile icon={Books} label="Materials" value={String(p.documents)} sub={`${p.notes} notes`} />
      </div>

      {p.trend.length > 1 && (
        <section className="card mt-5 p-4">
          <p className="label mb-3">Accuracy over time</p>
          <Sparkline points={p.trend} />
        </section>
      )}

      {Object.keys(p.byTier).length > 0 && (
        <section className="card mt-5 space-y-2 p-4">
          <p className="label mb-1">By difficulty</p>
          {["easy", "medium", "hard", "brutal"].map((t) =>
            p.byTier[t] != null ? (
              <ScoreBar key={t} label={t === "brutal" ? "very hard" : t} score={p.byTier[t]} />
            ) : null,
          )}
        </section>
      )}

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <SkillList
          title="Work on these"
          skills={p.weakSkills}
          tone="text-caution"
          onPractice={(s) => generate({ topic: s.skill, category: s.category })}
        />
        <SkillList title="Solid" skills={p.strongSkills} tone="text-positive" />
      </div>

      {p.byCategory.length > 0 && (
        <section className="card mt-5 space-y-2.5 p-4">
          <p className="label mb-1">Subjects</p>
          {p.byCategory.map((c) => (
            <div key={c.category}>
              <div className="flex items-center justify-between text-xs">
                <span className="font-medium text-content-primary">{c.label}</span>
                <span className="text-2xs text-content-muted">
                  {c.attempts} answered · {c.docCount} materials
                </span>
              </div>
              <ScoreBar
                label="ready"
                score={c.readiness}
                sublabel={c.attempts ? pct(c.readiness) : "—"}
              />
            </div>
          ))}
        </section>
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

function Sparkline({ points }: { points: TrendPoint[] }) {
  const w = 100;
  const h = 34;
  const xs = points.map((_, i) => (i / (points.length - 1)) * w);
  const ys = points.map((p) => h - p.accuracy * h);
  const d = xs.map((x, i) => `${i ? "L" : "M"}${x.toFixed(1)} ${ys[i].toFixed(1)}`).join(" ");
  return (
    <div>
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="h-16 w-full">
        <path
          d={`${d} L${w} ${h} L0 ${h} Z`}
          fill="rgb(var(--accent) / 0.12)"
          stroke="none"
        />
        <path d={d} fill="none" stroke="rgb(var(--accent))" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="mt-1 flex justify-between text-[0.58rem] text-content-muted">
        <span>{points[0].date.slice(5)}</span>
        <span>{points[points.length - 1].date.slice(5)}</span>
      </div>
    </div>
  );
}

function SkillList({
  title,
  skills,
  tone,
  onPractice,
}: {
  title: string;
  skills: SkillStat[];
  tone: string;
  onPractice?: (s: SkillStat) => void;
}) {
  return (
    <section className="card p-4">
      <p className="label mb-2">{title}</p>
      {skills.length === 0 ? (
        <p className="text-2xs text-content-muted">Not enough data yet.</p>
      ) : (
        <ul className="space-y-1.5">
          {skills.map((s) => (
            <li key={`${s.skill}-${s.category}`} className="flex items-center gap-2 text-xs">
              <span className={cn("font-medium", tone)}>{pct(s.accuracy)}</span>
              <span className="min-w-0 flex-1 truncate text-content-secondary">{s.skill}</span>
              {onPractice && (
                <button
                  onClick={() => onPractice(s)}
                  className="shrink-0 text-2xs text-accent hover:underline"
                >
                  practice
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
