"use client";

import { useEffect, useState } from "react";

import type { PracticeSetSummary, QuestionRead } from "@/lib/types";
import { cn, formatRelativeTime } from "@/lib/utils";
import { useAppStore } from "@/store/useAppStore";
import { useAuthStore } from "@/store/useAuthStore";
import { useStudyStore } from "@/store/useStudyStore";
import { STUDY_LEVELS } from "@/lib/types";
import {
  ArrowLeft,
  CheckCircle,
  Exam,
  Spinner,
  Trash,
  XCircle,
} from "@/components/ui/icons";

const TIER_META: Record<string, { label: string; tone: string }> = {
  easy: { label: "Easy", tone: "text-positive" },
  medium: { label: "Medium", tone: "text-accent" },
  hard: { label: "Hard", tone: "text-caution" },
  brutal: { label: "Very hard", tone: "text-danger" },
};

export function PracticeView() {
  const sets = useStudyStore((s) => s.practiceSets);
  const activeSet = useStudyStore((s) => s.activeSet);
  const loadingSets = useStudyStore((s) => s.loadingSets);
  const loadPracticeSets = useStudyStore((s) => s.loadPracticeSets);
  const openSet = useStudyStore((s) => s.openPracticeSet);
  const deleteSet = useStudyStore((s) => s.deletePracticeSet);
  const setActive = () => useStudyStore.setState({ activeSet: null });

  useEffect(() => {
    if (!sets.length && !loadingSets) loadPracticeSets();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (activeSet) {
    return (
      <div className="mx-auto w-full max-w-3xl px-5 py-8">
        <button onClick={setActive} className="btn btn-ghost mb-4 h-8 px-2 text-xs text-content-muted">
          <ArrowLeft className="h-3.5 w-3.5" /> All sets
        </button>
        <PracticeRunner />
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-5 py-8">
      <h1 className="text-xl font-semibold tracking-tight text-content-primary">Practice</h1>
      <p className="mt-1 text-sm text-content-secondary">
        Every set is 4 easy, 4 medium, 2 hard and 1 very hard question — pitched at your level and
        marked with feedback.
      </p>

      <GenerateForm />

      <h2 className="label mb-2 mt-9">Your sets</h2>
      {loadingSets ? (
        <div className="space-y-2">
          <div className="skeleton h-16" />
          <div className="skeleton h-16" />
        </div>
      ) : sets.length === 0 ? (
        <p className="rounded-lg border border-dashed border-line px-4 py-6 text-center text-sm text-content-muted">
          No practice sets yet — make one above.
        </p>
      ) : (
        <div className="space-y-2">
          {sets.map((s) => (
            <SetRow key={s.id} set={s} onOpen={() => openSet(s.id)} onDelete={() => deleteSet(s.id)} />
          ))}
        </div>
      )}
    </div>
  );
}

function GenerateForm() {
  const categories = useAppStore((s) => s.categories);
  const documents = useAppStore((s) => s.documents);
  const user = useAuthStore((s) => s.user);
  const generate = useStudyStore((s) => s.generatePracticeSet);
  const generating = useStudyStore((s) => s.generating);

  const [topic, setTopic] = useState("");
  const [category, setCategory] = useState("");
  const [documentId, setDocumentId] = useState("");
  const [level, setLevel] = useState(user?.studyLevel ?? "high-school");

  const submit = () => {
    if (!topic.trim() && !documentId) return;
    generate({
      topic: topic.trim() || undefined,
      documentId: documentId || undefined,
      category: category || null,
      studyLevel: level,
    });
  };

  return (
    <div className="card mt-5 space-y-3 p-4">
      <div>
        <label className="label mb-1 block">Topic</label>
        <input
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="e.g. integration by parts, the causes of WWI, redox reactions"
          className="input"
        />
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <div>
          <label className="label mb-1 block">From a material</label>
          <select value={documentId} onChange={(e) => setDocumentId(e.target.value)} className="input">
            <option value="">— none —</option>
            {documents
              .filter((d) => d.status === "ready")
              .map((d) => (
                <option key={d.id} value={d.id}>
                  {d.title}
                </option>
              ))}
          </select>
        </div>
        <div>
          <label className="label mb-1 block">Subject</label>
          <select value={category} onChange={(e) => setCategory(e.target.value)} className="input">
            <option value="">— none —</option>
            {categories.map((c) => (
              <option key={c.id} value={c.slug}>
                {c.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label mb-1 block">Level</label>
          <select value={level} onChange={(e) => setLevel(e.target.value)} className="input">
            {STUDY_LEVELS.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </div>
      </div>
      <button
        onClick={submit}
        disabled={generating || (!topic.trim() && !documentId)}
        className="btn btn-accent w-full text-xs"
      >
        {generating ? <Spinner className="h-3.5 w-3.5 animate-spin" /> : <Exam className="h-3.5 w-3.5" />}
        {generating ? "Building 11 questions…" : "Make a practice set"}
      </button>
    </div>
  );
}

function SetRow({
  set,
  onOpen,
  onDelete,
}: {
  set: PracticeSetSummary;
  onOpen: () => void;
  onDelete: () => void;
}) {
  const pct = set.answered ? Math.round((set.correct / set.answered) * 100) : 0;
  return (
    <div className="group flex items-center gap-3 rounded-lg border border-line bg-surface-raised p-3.5 transition-colors hover:border-accent/40">
      <button onClick={onOpen} className="min-w-0 flex-1 text-left">
        <p className="truncate text-sm font-medium text-content-primary">{set.topic}</p>
        <p className="mt-0.5 text-2xs text-content-muted">
          {set.studyLevel} · {set.questionCount} questions ·{" "}
          {set.answered ? `${set.answered}/${set.questionCount} done · ${pct}% right` : "not started"}{" "}
          · {formatRelativeTime(set.createdAt)}
        </p>
      </button>
      <button
        onClick={() => confirm("Delete this set?") && onDelete()}
        className="text-content-muted opacity-0 transition-opacity hover:text-danger group-hover:opacity-100"
        aria-label="Delete set"
      >
        <Trash className="h-4 w-4" />
      </button>
    </div>
  );
}

function PracticeRunner() {
  const set = useStudyStore((s) => s.activeSet)!;
  return (
    <>
      <div className="mb-5">
        <h2 className="text-lg font-semibold tracking-tight text-content-primary">{set.topic}</h2>
        <p className="mt-1 text-2xs text-content-muted">
          {set.studyLevel} · {set.answered}/{set.questions.length} answered ·{" "}
          {set.answered ? Math.round((set.correct / set.answered) * 100) : 0}% right · {set.model}
        </p>
        <div className="mt-2 h-1 overflow-hidden rounded-full bg-surface-sunken">
          <div
            className="h-full rounded-full bg-accent transition-[width] duration-500"
            style={{ width: `${(set.answered / set.questions.length) * 100}%` }}
          />
        </div>
      </div>
      <div className="space-y-4">
        {set.questions.map((q) => (
          <QuestionCard key={q.id} q={q} />
        ))}
      </div>
    </>
  );
}

function QuestionCard({ q }: { q: QuestionRead }) {
  const grade = useStudyStore((s) => s.gradeAnswer);
  const [answer, setAnswer] = useState("");
  const [optionIndex, setOptionIndex] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const done = !!q.attempt;
  const tier = TIER_META[q.tier] ?? TIER_META.medium;

  const isChoice = q.qtype === "mcq" || q.qtype === "true_false";

  const submit = async () => {
    if (busy || done) return;
    if (isChoice && optionIndex === null) return;
    if (!isChoice && !answer.trim()) return;
    setBusy(true);
    await grade(q.index, isChoice ? { optionIndex } : { answer });
    setBusy(false);
  };

  return (
    <div className="rounded-xl border border-line bg-surface-raised p-4">
      <div className="mb-2 flex items-center gap-2 text-2xs">
        <span className={cn("font-semibold uppercase tracking-wide", tier.tone)}>{tier.label}</span>
        {q.skill && <span className="text-content-muted">· {q.skill}</span>}
        {done &&
          (q.attempt!.correct ? (
            <span className="ml-auto inline-flex items-center gap-1 font-medium text-positive">
              <CheckCircle className="h-3.5 w-3.5" weight="fill" /> {Math.round(q.attempt!.score * 100)}%
            </span>
          ) : (
            <span className="ml-auto inline-flex items-center gap-1 font-medium text-danger">
              <XCircle className="h-3.5 w-3.5" weight="fill" /> {Math.round(q.attempt!.score * 100)}%
            </span>
          ))}
      </div>

      <p className="whitespace-pre-wrap text-sm leading-relaxed text-content-primary">
        {q.index + 1}. {q.prompt}
      </p>

      {isChoice ? (
        <div className="mt-3 space-y-1.5">
          {q.options.map((opt, i) => {
            const chosen = done ? q.attempt!.userAnswer === opt : optionIndex === i;
            const correct = done && q.answer === opt;
            return (
              <button
                key={i}
                disabled={done}
                onClick={() => setOptionIndex(i)}
                className={cn(
                  "flex w-full items-center gap-2 rounded-md border px-3 py-2 text-left text-xs transition-colors",
                  correct
                    ? "border-positive/50 bg-positive/10 text-content-primary"
                    : chosen && done
                      ? "border-danger/50 bg-danger/10"
                      : chosen
                        ? "border-accent/50 bg-accent-soft text-accent"
                        : "border-line hover:border-accent/40",
                )}
              >
                <span className="font-mono text-2xs text-content-muted">{String.fromCharCode(65 + i)}</span>
                {opt}
              </button>
            );
          })}
        </div>
      ) : (
        <textarea
          value={done ? q.attempt!.userAnswer : answer}
          onChange={(e) => setAnswer(e.target.value)}
          disabled={done}
          rows={q.qtype === "explain" ? 4 : 2}
          placeholder={q.qtype === "numeric" ? "Your answer (with units)" : "Your answer"}
          className="input mt-3 text-sm disabled:opacity-70"
        />
      )}

      {done ? (
        <div className="mt-3 space-y-2 border-t border-line pt-3 text-xs">
          <p className="leading-relaxed text-content-secondary">{q.attempt!.feedback}</p>
          {q.answer && (
            <p className="text-content-muted">
              <span className="font-medium text-content-secondary">Answer:</span> {q.answer}
            </p>
          )}
        </div>
      ) : (
        <button
          onClick={submit}
          disabled={busy || (isChoice ? optionIndex === null : !answer.trim())}
          className="btn btn-accent mt-3 h-8 px-4 text-xs"
        >
          {busy && <Spinner className="h-3.5 w-3.5 animate-spin" />}
          Check answer
        </button>
      )}
    </div>
  );
}
