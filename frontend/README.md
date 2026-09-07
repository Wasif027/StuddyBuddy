# Frontend — Enterprise AI Knowledge & Decision Platform

Next.js 14 (App Router) · React 18 · TypeScript (strict) · Tailwind · Zustand.

Sign in (username + password), then a three-pane decision workspace:

| Pane | Contents |
| ---- | -------- |
| **Left** (auto-hide, resizable) | your chats (new / rename / delete, one per topic) + knowledge base — file-kind icons, category scope, compare-mode checkboxes, per-doc ✦ Summarise / ▮▮ Analyse buttons, add-document dialog (PDF / Word / Excel / PowerPoint, or paste) |
| **Center** | conversation — streamed answers with clickable `[n]` citations, confidence badge, mode chip (compare / full-document read / broad scan / computed answer), follow-up chips, copy-as-Markdown; a message flashes when you deep-link to it from the suggestions history |
| **Right** (hideable, resizable) | grounding — confidence gauge · **analysis card** (result table + chart + collapsible SQL) · source passages with `[n]` markers, highlighted quotes, `Slide N` badges and a data-rich meter · **next steps** — accept / reject / mark-done each suggestion; reject spawns an alternative |

Plus a full-screen **Suggestions history** (top bar / ⌘K) that lists every
suggestion ever with a status filter and deep-links back to the originating chat
message ("conversation deleted" if the chat is gone), a ⌘K command palette, a
persisted light/dark theme, toasts, and `/` to focus the composer.

## Run

```bash
npm install
npm run dev        # http://localhost:3000
```

Requests go to `/api/v1/*` and are proxied to the backend by
`next.config.mjs` (`API_PROXY_TARGET`, default `http://localhost:8000`) — one
origin, clean SSE, no CORS. The JWT bearer token is kept in `localStorage`
(`ekdp-token`) and attached to every request; a `401` clears it and returns to
the sign-in screen.

## Scripts

| Command | What |
| ------- | ---- |
| `npm run dev` | dev server |
| `npm run build` | production build (`output: standalone`) |
| `npm run lint` | ESLint (`next/core-web-vitals` + `next/typescript`, no `any`) |
| `npm run typecheck` | `tsc --noEmit` |

## Layout

```
src/
  lib/
    types.ts    wire types — mirror backend/app/models/schemas.py
    api.ts      typed fetch client (bearer token + 401 handling, + SSE)
    auth.ts     token storage + unauthorized handler
    stream.ts   SSE frame parser
    utils.ts    cn(), formatters, clipboard
  store/
    useAuthStore.ts  zustand — bootstrap / login / register / logout
    useAppStore.ts   zustand — meta, chats, compare mode, streaming, suggestion decisions,
                     message deep-link highlight, add-document
    useUIStore.ts    zustand (persisted) — panel widths, pin / open state
    useToast.ts      toast queue
  components/
    auth/        AuthGate · AuthScreen
    layout/      AppShell · TopBar · CommandPalette · LeftDock (auto-hide) · ResizeHandle
    sidebar/     ConversationList · KnowledgeBase · IngestDialog
    chat/        ConversationView (message flash) · AnswerCard · AnswerText · Composer · EmptyState
    grounding/   RightPanel · PassageCard (marker + quote, slide badges) ·
                 AnalysisCard · DataTable · ResultChart (SVG bar/line)
    suggestions/ SuggestionCard (accept / reject / done + note)
    history/     SuggestionsHistory (full-screen, filtered, deep-links to chat)
    ui/          ConfidenceGauge · ScoreBar · Modal · ToastViewport
    providers/   ThemeProvider · Providers
```

The wire contract is camelCase and coupled to the backend — change a field in
one place and the other.
