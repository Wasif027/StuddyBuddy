/**
 * Wire types — mirror the FastAPI backend's camelCase JSON exactly
 * (backend/app/models/schemas.py is the source of truth).
 */

export type SuggestionDecision = "pending" | "accepted" | "rejected" | "done";
export type SuggestionPriority = "high" | "medium" | "low";

export type ConfidenceLabel = "high" | "medium" | "low" | "insufficient";

export type RetrievalMode = "pinpoint" | "document" | "overview" | "analysis" | "meta";

export type ChunkKind = "text" | "page" | "slide" | "sheet";

export interface SlideMeta {
  kind: "slide";
  slide: number;
  title?: string | null;
  dataScore?: number;
  hasChart?: boolean;
  hasTable?: boolean;
}

export interface ChartSpec {
  type: "bar" | "line";
  x: string;
  series: string[];
}

export interface AnalysisBlock {
  ok: boolean;
  sql: string;
  dialect: string;
  columns: string[];
  rows: Array<Array<string | number | boolean | null>>;
  rowCount: number;
  truncated: boolean;
  tablesUsed: string[];
  assumptions: string;
  error: string | null;
  chart: ChartSpec | null;
}

export type DocStatus = "ready" | "processing" | "failed" | "empty" | "indexing";

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

export type SuggestionKind = "explore" | "external";

export interface Suggestion {
  id: string;
  text: string;
  rationale: string | null;
  priority: SuggestionPriority;
  kind: SuggestionKind;
  decision: SuggestionDecision;
  note: string | null;
  rejectDepth: number;
  createdAt: string | null;
  decidedAt: string | null;
  // history context
  question: string | null;
  conversationId: string | null;
  messageId: string | null;
  conversationTitle: string | null;
  conversationDeleted: boolean;
}

export interface TokenUsage {
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
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
  compareMode: boolean;
  retrievalMode: RetrievalMode;
  retrievalNote: string;
  analysis: AnalysisBlock | null;
  citations: Citation[];
  sourceChunks: SourceChunk[];
  suggestions: Suggestion[];
  followUps: string[];
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
  intent?: "auto" | "summary" | "analysis";
  compareDocumentIds?: string[] | null;
  suggest?: boolean;
  stream?: boolean;
  bypassCache?: boolean;
}

export interface SuggestionDecisionResponse {
  suggestion: Suggestion;
  alternative: Suggestion | null;
  message: string;
}

/* -------------------------------------------------------------------- auth */
export interface User {
  id: string;
  username: string;
  displayName: string | null;
  createdAt: string;
}

export interface AuthResponse {
  token: string;
  user: User;
}

/* ------------------------------------------------------------ conversations */
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

export interface ConversationDetail extends Conversation {
  messages: ConversationMessage[];
}

export interface DocumentCategory {
  id: string;
  label: string;
  docCount: number;
  chunkCount: number;
  status: DocStatus;
}

export interface DocumentRead {
  id: string;
  title: string;
  category: string | null;
  sourceType: string;
  status: string;
  error: string | null;
  chunkCount: number;
  charCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface IngestionResponse {
  documentId: string;
  documentTitle: string;
  status: string;
  chunksCreated: number;
  charCount: number;
  elapsedMs: number;
  deduplicated: boolean;
}

export interface HealthResponse {
  status: "healthy" | "degraded" | "unhealthy";
  version: string;
  env: string;
  services: { postgres: string; redis: string; api: string };
  llmProvider: string;
  llmModel: string;
  llmActive: boolean;
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
  | { type: "analysis"; payload: AnalysisBlock }
  | { type: "suggestions"; payload: { suggestions: Suggestion[] } }
  | { type: "final"; payload: AnswerResponse }
  | { type: "error"; payload: { message: string } };

/* ---------------------------------------------------------------- chat UI */
export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  answer?: AnswerResponse;
  pending?: boolean;
  error?: string;
  timestamp: string;
}
