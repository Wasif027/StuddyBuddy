/**
 * Wire types — mirror the FastAPI backend's camelCase JSON exactly
 * (backend/app/models/schemas.py is the source of truth).
 */

export type ConfidenceLabel = "high" | "medium" | "low" | "insufficient";
export type RetrievalMode = "pinpoint" | "document" | "overview" | "meta" | "general";
export type ExplainLevel = "simple" | "standard" | "deep" | "exam";
export type QuestionTier = "easy" | "medium" | "hard" | "brutal";
export type QuestionType = "mcq" | "short" | "numeric" | "true_false" | "explain";
export type NoteKind = "note" | "log" | "routine" | "saved";
export type DocStatus = "ready" | "processing" | "failed" | "pending";

export const STUDY_LEVELS = [
  "year-8",
  "gcse",
  "high-school",
  "a-level",
  "ib",
  "undergraduate",
] as const;
export type StudyLevel = (typeof STUDY_LEVELS)[number];

export const EXPLAIN_LEVELS: { id: ExplainLevel; label: string; blurb: string }[] = [
  { id: "simple", label: "Simple", blurb: "Plain language, one idea at a time" },
  { id: "standard", label: "Standard", blurb: "Clear, with a worked example" },
  { id: "deep", label: "In depth", blurb: "Mechanism, edge cases, connections" },
  { id: "exam", label: "Exam", blurb: "Mark-scheme phrasing and structure" },
];

/* --------------------------------------------------------------- answers */
export interface Citation {
  marker: number;
  chunkId: string;
  documentId: string;
  title: string;
  category: string | null;
  page: number | null;
  quote: string;
  score: number;
}

export interface SourceChunk {
  chunkId: string;
  documentId: string;
  title: string;
  heading: string | null;
  chunkIndex: number;
  text: string;
  category: string | null;
  score: number;
  vectorScore: number;
  keywordScore: number;
  rerankScore: number | null;
  metadata: Record<string, unknown>;
}

export interface TokenUsage {
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
}

export interface ChartPoint {
  x: number;
  y: number;
}

export interface ChartSeries {
  name: string;
  points: ChartPoint[];
}

export interface ChartSpec {
  type: "line" | "bar" | "scatter";
  title: string;
  xLabel: string;
  yLabel: string;
  series: ChartSeries[];
}

export interface AnswerResponse {
  id: string;
  conversationId: string | null;
  messageId: string | null;
  question: string;
  answer: string;
  confidence: number;
  confidenceLabel: ConfidenceLabel;
  insufficientEvidence: boolean;
  grounded: boolean;
  corrected: boolean;
  compareMode: boolean;
  retrievalMode: RetrievalMode;
  retrievalNote: string;
  explainLevel: ExplainLevel;
  citations: Citation[];
  sourceChunks: SourceChunk[];
  followUps: string[];
  chart: ChartSpec | null;
  model: string;
  provider: string;
  latencyMs: number;
  usage: TokenUsage;
  cached: boolean;
  createdAt: string;
}

export interface QueryRequest {
  question: string;
  conversationId?: string | null;
  topK?: number;
  categoryId?: string | null;
  documentId?: string | null;
  intent?: "auto" | "summary";
  explainLevel?: ExplainLevel | null;
  compareDocumentIds?: string[] | null;
  stream?: boolean;
  bypassCache?: boolean;
}

/* -------------------------------------------------------------------- auth */
export interface User {
  id: string;
  username: string;
  displayName: string | null;
  studyLevel: string;
  hasCustomKey: boolean;
  createdAt: string;
}

export interface AuthResponse {
  token: string;
  user: User;
}

/* ------------------------------------------------------------ conversations */
export type ChatRole = "user" | "assistant";

export interface Conversation {
  id: string;
  title: string;
  messageCount: number;
  lastMessageAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ConversationMessage {
  id: string;
  role: ChatRole;
  content: string;
  answer: AnswerResponse | null;
  createdAt: string;
}

export interface ChatContext {
  summary: string;
  topics: string[];
  established: { fact?: string; source?: string; verified?: boolean }[];
  studentClaims: { claim?: string; issue?: string }[];
  corrections: { was?: string; now?: string }[];
  misconceptions: string[];
  observedLevel: string | null;
}

export interface ConversationDetail extends Conversation {
  messages: ConversationMessage[];
  context: ChatContext;
  attachedDocuments: string[];
}

/* ------------------------------------------------------------- categories */
export interface Category {
  id: string;
  slug: string;
  label: string;
  level: string | null;
  color: string | null;
  isDefault: boolean;
  docCount: number;
  noteCount: number;
  createdAt: string | null;
}

/* -------------------------------------------------------------- materials */
export interface SlidePreview {
  index: number;
  title: string | null;
  bullets: string[];
  notes: string | null;
  hasChart: boolean;
  hasTable: boolean;
  importance: number;
}

export interface DocumentRead {
  id: string;
  title: string;
  category: string | null;
  sourceType: string;
  status: DocStatus;
  error: string | null;
  chunkCount: number;
  slideCount: number;
  charCount: number;
  imageKind: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface DocumentDetail extends DocumentRead {
  metadata: Record<string, unknown>;
  chunks: { chunkIndex: number; heading: string | null; text: string; tokenCount: number }[];
  slides: SlidePreview[];
}

export interface IngestionResponse {
  documentId: string;
  documentTitle: string;
  status: string;
  chunksCreated: number;
  charCount: number;
  elapsedMs: number;
  deduplicated: boolean;
  noteId: string | null;
  detectedKind: string | null;
}

/* ------------------------------------------------------- study guide */
export type StudyGuideKind =
  | "guide"
  | "glossary"
  | "cheatsheet"
  | "concept_map"
  | "flashcards"
  | "key_slides";

export interface Flashcard {
  front: string;
  back: string;
  hint: string | null;
}

export interface ConceptNode {
  id: string;
  label: string;
  parent: string | null;
  note: string | null;
}

export interface StudyGuideResponse {
  documentId: string;
  kind: StudyGuideKind;
  title: string;
  markdown: string;
  flashcards: Flashcard[];
  concepts: ConceptNode[];
  keySlides: SlidePreview[];
  model: string;
}

/* --------------------------------------------------------------- practice */
export interface AttemptRead {
  id: string;
  questionId: string | null;
  userAnswer: string;
  correct: boolean;
  score: number;
  feedback: string;
  tier: string;
  transcription: string | null;
  createdAt: string | null;
}

export type AnswerMode = "text" | "text_or_upload";

export interface QuestionRead {
  id: string;
  index: number;
  tier: QuestionTier;
  qtype: QuestionType;
  prompt: string;
  options: string[];
  skill: string | null;
  answerMode: AnswerMode;
  answer: string | null;
  rubric: string | null;
  attempt: AttemptRead | null;
}

export interface PracticeSetRead {
  id: string;
  topic: string;
  category: string | null;
  studyLevel: string;
  source: string;
  documentId: string | null;
  conversationId: string | null;
  model: string;
  createdAt: string;
  questions: QuestionRead[];
  answered: number;
  correct: number;
}

export interface PracticeSetSummary {
  id: string;
  topic: string;
  category: string | null;
  studyLevel: string;
  source: string;
  createdAt: string;
  questionCount: number;
  answered: number;
  correct: number;
}

export interface GradeResponse {
  attempt: AttemptRead;
  answer: string;
  rubric: string;
  model: string;
}

/* ----------------------------------------------------------------- notes */
export interface NoteRead {
  id: string;
  category: string | null;
  kind: NoteKind;
  title: string;
  bodyMd: string;
  structured: Record<string, unknown>;
  source: string;
  sourceRef: string | null;
  pinned: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface RoutineDay {
  day: string;
  entries: { time?: string; label?: string; location?: string }[];
}

/* -------------------------------------------------------------- progress */
/** One practice set's result, chronological. Unanswered questions count as
 * incorrect — an untouched set is a real 0/N point, not a gap. */
export interface SetTrendPoint {
  setId: string;
  createdAt: string;
  correct: number;
  total: number;
  accuracy: number;
}

export interface CategoryProgress {
  category: string;
  label: string;
  totalSets: number;
  solvedSets: number;
  docCount: number;
  byTier: Record<string, number>;
  trend: SetTrendPoint[];
}

export interface ProgressResponse {
  totalQuestions: number;
  totalCorrect: number;
  currentStreak: number;
  longestStreak: number;
  totalSets: number;
  incompleteSets: number;
  byTier: Record<string, number>;
  byCategory: CategoryProgress[];
  documents: number;
  notes: number;
}

/* ----------------------------------------------------------------- meta */
export interface HealthResponse {
  status: "healthy" | "degraded" | "unhealthy";
  version: string;
  env: string;
  services: { postgres: string; redis: string; api: string };
  llmProvider: string;
  llmModel: string;
  llmActive: boolean;
  visionEnabled: boolean;
  embeddingProvider: string;
  embeddingDim: number;
}

/* ------------------------------------------------------------------ stream */
export type StreamEvent =
  | { type: "start"; payload: { question: string; conversationId: string } }
  | {
      type: "grounding";
      payload: { sourceChunks: SourceChunk[]; retrievalMode?: RetrievalMode; retrievalNote?: string };
    }
  | { type: "token"; payload: { text: string } }
  | { type: "final"; payload: AnswerResponse }
  | { type: "error"; payload: { message: string } };

/* ---------------------------------------------------------------- chat UI */
export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  answer?: AnswerResponse;
  pending?: boolean;
  error?: string;
  timestamp: string;
}
