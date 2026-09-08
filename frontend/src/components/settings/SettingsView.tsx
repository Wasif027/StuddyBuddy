"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { STUDY_LEVELS } from "@/lib/types";
import { toast } from "@/store/useToast";
import { useAppStore } from "@/store/useAppStore";
import { useAuthStore } from "@/store/useAuthStore";
import { useTheme } from "@/components/providers/ThemeProvider";
import { Plus, Spinner, Trash } from "@/components/ui/icons";

const LEVEL_LABEL: Record<string, string> = {
  "year-8": "Year 8 / Middle school",
  gcse: "GCSE",
  "high-school": "High school",
  "a-level": "A-level",
  ib: "IB",
  undergraduate: "Undergraduate",
};

export function SettingsView() {
  const user = useAuthStore((s) => s.user);
  const patchUser = useAuthStore((s) => s.patchUser);
  const { theme, toggle } = useTheme();

  const [displayName, setDisplayName] = useState(user?.displayName ?? "");
  const [level, setLevel] = useState(user?.studyLevel ?? "high-school");
  const [savingProfile, setSavingProfile] = useState(false);

  useEffect(() => {
    setDisplayName(user?.displayName ?? "");
    setLevel(user?.studyLevel ?? "high-school");
  }, [user]);

  const saveProfile = async () => {
    setSavingProfile(true);
    try {
      const u = await api.updateMe({ displayName: displayName.trim(), studyLevel: level });
      patchUser(u);
      toast.success("Saved");
    } catch (err) {
      toast.error("Couldn't save", err instanceof Error ? err.message : String(err));
    } finally {
      setSavingProfile(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-2xl px-5 py-8">
      <h1 className="text-xl font-semibold tracking-tight text-content-primary">Settings</h1>

      <section className="card mt-5 space-y-3 p-5">
        <p className="label">Profile</p>
        <label className="block">
          <span className="mb-1 block text-xs text-content-secondary">Display name</span>
          <input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder={user?.username}
            className="input"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-content-secondary">Study level</span>
          <select value={level} onChange={(e) => setLevel(e.target.value)} className="input">
            {STUDY_LEVELS.map((l) => (
              <option key={l} value={l}>
                {LEVEL_LABEL[l] ?? l}
              </option>
            ))}
          </select>
          <span className="mt-1 block text-2xs text-content-muted">
            Default depth for explanations and practice questions. Individual subjects can override
            it below.
          </span>
        </label>
        <button onClick={saveProfile} disabled={savingProfile} className="btn btn-accent h-8 px-4 text-xs">
          {savingProfile && <Spinner className="h-3.5 w-3.5 animate-spin" />}
          Save
        </button>
      </section>

      <CategoryManager />

      <section className="card mt-5 flex items-center justify-between p-5">
        <div>
          <p className="label">Appearance</p>
          <p className="mt-1 text-xs text-content-secondary">Currently {theme} mode.</p>
        </div>
        <button onClick={toggle} className="btn h-8 px-3 text-xs">
          Switch to {theme === "dark" ? "light" : "dark"}
        </button>
      </section>
    </div>
  );
}

function CategoryManager() {
  const categories = useAppStore((s) => s.categories);
  const refreshMeta = useAppStore((s) => s.refreshMeta);
  const [newLabel, setNewLabel] = useState("");
  const [busy, setBusy] = useState(false);

  const add = async () => {
    if (!newLabel.trim()) return;
    setBusy(true);
    try {
      await api.createCategory({ label: newLabel.trim() });
      setNewLabel("");
      await refreshMeta();
    } catch (err) {
      toast.error("Couldn't add", err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const setLevel = async (id: string, lvl: string) => {
    try {
      await api.updateCategory(id, { level: lvl || null });
      await refreshMeta();
    } catch (err) {
      toast.error("Couldn't update", err instanceof Error ? err.message : String(err));
    }
  };

  const remove = async (id: string, label: string) => {
    if (!confirm(`Delete the "${label}" subject? Its materials become uncategorised.`)) return;
    try {
      await api.deleteCategory(id);
      await refreshMeta();
    } catch (err) {
      toast.error("Couldn't delete", err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <section className="card mt-5 p-5">
      <p className="label mb-3">Subjects</p>
      <div className="mb-3 flex gap-2">
        <input
          value={newLabel}
          onChange={(e) => setNewLabel(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          placeholder="Add a subject — e.g. Further Maths"
          className="input py-1.5 text-xs"
        />
        <button onClick={add} disabled={busy || !newLabel.trim()} className="btn btn-accent h-8 px-3 text-xs">
          {busy ? <Spinner className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
        </button>
      </div>
      <div className="space-y-1">
        {categories.map((c) => (
          <div key={c.id} className="flex items-center gap-2 rounded-md px-1 py-1.5 text-xs">
            <span className="min-w-0 flex-1 truncate font-medium text-content-secondary">
              {c.label}
              <span className="ml-1.5 text-2xs font-normal text-content-muted">
                {c.docCount} materials
              </span>
            </span>
            <select
              value={c.level ?? ""}
              onChange={(e) => setLevel(c.id, e.target.value)}
              className="rounded border border-line bg-surface-base px-1.5 py-0.5 text-2xs"
            >
              <option value="">default level</option>
              {STUDY_LEVELS.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
            {!c.isDefault && (
              <button
                onClick={() => remove(c.id, c.label)}
                className="text-content-muted hover:text-danger"
                aria-label="Delete subject"
              >
                <Trash className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
