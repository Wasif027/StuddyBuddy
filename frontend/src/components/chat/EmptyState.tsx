"use client";

import { useAppStore } from "@/store/useAppStore";
import { useAuthStore } from "@/store/useAuthStore";
import { useStudyStore } from "@/store/useStudyStore";
import { useUIStore } from "@/store/useUIStore";
import { ArrowRight, Exam, Plus, Quotes, Sparkle, UploadSimple } from "@/components/ui/icons";

export function EmptyState() {
  const documents = useAppStore((s) => s.documents);
  const ask = useAppStore((s) => s.ask);
  const loadingMeta = useAppStore((s) => s.loadingMeta);
  const user = useAuthStore((s) => s.user);
  const setIngestOpen = useUIStore((s) => s.setIngestOpen);
  const generate = useStudyStore((s) => s.generatePracticeSet);

  const hasDocs = documents.length > 0;
  const name = user?.displayName?.split(" ")[0] || user?.username;

  const starters = hasDocs
    ? [
        `Summarise "${documents[0]?.title}".`,
        "Explain the hardest idea in my materials, simply.",
        documents.length >= 2 ? "How do my two most recent materials connect?" : null,
      ]
    : [
        "Explain photosynthesis to me.",
        "What's the difference between mitosis and meiosis?",
        "Walk me through solving a quadratic equation.",
      ];

  return (
    <div className="mx-auto w-full max-w-[42rem] px-5 py-14">
      <div className="stagger">
        <h1 className="text-[2rem] font-semibold leading-[1.1] tracking-[-0.03em] text-content-primary">
          {name ? `Hi ${name}.` : "Hi."}
          <br />
          What are we studying?
        </h1>

        <p className="mt-4 max-w-[48ch] text-[0.95rem] leading-relaxed text-content-secondary">
          Ask me to explain any topic up to undergraduate level — I&apos;ll pitch it to your level and
          go <em>simpler</em>, <em>deeper</em> or <em>exam-style</em> on request.
          {hasDocs
            ? ` I'll ground it in your ${documents.length} uploaded material${documents.length === 1 ? "" : "s"} and cite the pages.`
            : " Upload your notes or slides and I'll cite them."}
        </p>

        <div className="mt-8 flex flex-col divide-y divide-line border-y border-line">
          {starters
            .filter((q): q is string => Boolean(q))
            .map((q) => (
              <button
                key={q}
                onClick={() => ask(q)}
                className="group flex items-center gap-4 py-3.5 text-left transition-colors hover:bg-surface-sunken/60"
              >
                <Quotes className="h-4 w-4 shrink-0 text-content-muted transition-colors group-hover:text-accent" />
                <span className="flex-1 text-[0.9rem] leading-snug text-content-secondary transition-colors group-hover:text-content-primary">
                  {q}
                </span>
                <ArrowRight className="h-3.5 w-3.5 shrink-0 -translate-x-1 text-content-muted opacity-0 transition-all group-hover:translate-x-0 group-hover:opacity-100" />
              </button>
            ))}
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          {!loadingMeta && !hasDocs && (
            <button onClick={() => setIngestOpen(true)} className="btn btn-accent px-3.5 py-2 text-xs">
              <UploadSimple className="h-3.5 w-3.5" /> Upload your first material
            </button>
          )}
          <button
            onClick={() => generate({ topic: hasDocs ? documents[0]?.title : "a topic you choose" })}
            className="btn px-3.5 py-2 text-xs"
          >
            <Exam className="h-3.5 w-3.5" /> Make practice questions
          </button>
          {hasDocs && (
            <button onClick={() => setIngestOpen(true)} className="btn px-3.5 py-2 text-xs">
              <Plus className="h-3.5 w-3.5" /> Add more
            </button>
          )}
        </div>

        <p className="mt-6 inline-flex items-center gap-1.5 text-2xs text-content-muted">
          <Sparkle className="h-3 w-3" /> Try: <em>&ldquo;give me 11 practice questions on the French
          Revolution&rdquo;</em>
        </p>
      </div>
    </div>
  );
}
