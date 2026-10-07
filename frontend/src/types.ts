export type DiagramKind =
  | 'sequence'
  | 'component'
  | 'class'
  | 'object'
  | 'composite_structure'
  | 'deployment'
  | 'package'
  | 'profile'
  | 'use_case'
  | 'activity'
  | 'state_machine'
  | 'communication'
  | 'interaction_overview'
  | 'timing';
export interface CatalogEntry {
  id: DiagramKind;
  label: string;
  category: string;
  description: string;
}
export interface Session {
  mode: 'sample' | 'live';
  storage: 'sqlite' | 'postgres';
  model: string | null;
  sample_prompt: string;
  sample_updates: string[];
  diagram_types: CatalogEntry[];
}
export interface Component {
  id: string;
  name: string;
  kind: string;
  package: string;
  responsibility: string;
}
export interface Architecture {
  title: string;
  summary: string;
  requirements: string[];
  assumptions: string[];
  components: Component[];
  connections: { source: string; target: string; label: string; kind: string }[];
  entities: {
    id: string;
    name: string;
    attributes: { name: string; type: string }[];
    operations: string[];
  }[];
  actors: { name: string; goals: string[] }[];
  steps: {
    action: string;
    owner: string;
    guard: string | null;
    alternative: string | null;
    parallel_actions: string[];
  }[];
  states: string[];
  transitions: { source: string; target: string; event: string; guard: string | null }[];
  nodes: { name: string; kind: string; components: string[] }[];
  [key: string]: unknown;
}
export interface Diagram {
  type: DiagramKind;
  source: string;
  svg: string;
  validated: boolean;
  cache_hit: boolean;
}
export interface Revision {
  id: string;
  conversation_id: string;
  number: number;
  request_id: string;
  prompt: string;
  architecture: Architecture;
  diagrams: Diagram[];
  mode: string;
  model: string | null;
  created_at: string;
  timings: { design_ms: number; render_ms: number; total_ms: number };
  quality?: {
    status: 'reviewed' | 'revised' | 'needs_review' | 'unavailable';
    summary: string;
    covered_requirements: string[];
    missing_requirements: string[];
    critical_issues: string[];
    suggestions: string[];
    structural_issues: string[];
  };
}
export interface ConversationSummary {
  id: string;
  title: string;
  latest: number;
  updated_at: string;
  archived: boolean;
}
export interface Allowance {
  remaining: number;
  limit: number;
}
export interface Conversation extends ConversationSummary {
  revisions: Revision[];
}
export interface Feedback {
  id: string;
  revision_id: string;
  rating: number;
  comment: string;
  diagram_type: DiagramKind | null;
  training_status: string;
  created_at: string;
}
