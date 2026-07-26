/** Shared frontend types mirroring the backend Pydantic schemas
 * (core/resume/schema.py) and API response shapes.
 *
 * NOTE: these are declared with `type` (not `interface`) on purpose —
 * object type aliases get an implicit index signature, which keeps them
 * assignable to `Record<string, unknown>` props used by legacy components.
 */

// ── Resume schema (backend: core/resume/schema.py) ─────────

export type PersonalInfo = {
  full_name: string;
  email: string;
  phone: string;
  location: string;
  linkedin: string;
  github: string;
  website: string;
  summary: string;
};

export type EducationEntry = {
  id: string;
  entry_type: "education";
  school: string;
  degree: string;
  major: string;
  level: "high_school" | "associate" | "bachelor" | "master" | "phd" | "other";
  start_date: string | null;
  end_date: string | null;
  dates_approximate: boolean;
  gpa: string;
  description: string;
  confidence: number;
};

export type WorkExperienceEntry = {
  id: string;
  entry_type: "work";
  company: string;
  position: string;
  start_date: string | null;
  end_date: string | null;
  dates_approximate: boolean;
  is_current: boolean;
  location: string;
  bullets: string[];
  description: string;
  confidence: number;
};

export type ProjectExperienceEntry = {
  id: string;
  entry_type: "project";
  name: string;
  role: string;
  url: string;
  start_date: string | null;
  end_date: string | null;
  dates_approximate: boolean;
  technologies: string[];
  bullets: string[];
  description: string;
  is_planned: boolean;
  confidence: number;
};

export type SkillEntry = {
  id: string;
  name: string;
  category: string;
  level: string;
  years: number;
  confidence: number;
};

export type Resume = {
  id: string;
  version: number;
  created_at: string;
  updated_at: string;
  personal_info: PersonalInfo;
  education: EducationEntry[];
  work_experience: WorkExperienceEntry[];
  project_experience: ProjectExperienceEntry[];
  skills: SkillEntry[];
  target_position: string;
  target_industry: string;
  source_filename: string;
};

/** Any entry that lives in a resume section. */
export type ResumeEntry =
  | EducationEntry
  | WorkExperienceEntry
  | ProjectExperienceEntry
  | SkillEntry;

// ── API response shapes ────────────────────────────────────

export type ResumeListItem = {
  id: string;
  version: number;
  updated_at: string;
  filename: string;
  name: string;
};

export type ResumeListResponse = {
  current_resume_id: string;
  resumes: ResumeListItem[];
};

export type UploadMetadata = {
  warnings?: string[];
  text_truncated?: boolean;
  [key: string]: unknown;
};

export type UploadResult = {
  resume_id: string;
  resume: Resume;
  metadata: UploadMetadata;
};

export type SessionSummary = {
  id: string;
  title: string;
  resume_id: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
};

export type SessionListResponse = {
  sessions: SessionSummary[];
};

export type SessionMessage = {
  id: number;
  role: "user" | "agent";
  content: string;
  created_at: string;
};

export type SessionDetail = {
  session_id: string;
  title: string;
  resume_id: string;
  created_at: string;
  messages: SessionMessage[];
};

// ── Chat UI types ──────────────────────────────────────────

/** One reasoning-chain event collected during a streaming turn. */
export type ChatEvent = {
  type: string;
  data: Record<string, unknown>;
};

export type ChatMessage = {
  id: string;
  role: "user" | "agent";
  content: string;
  /** Reasoning-chain events (plan/tool/observe) for agent turns. */
  events?: ChatEvent[];
  /** Epoch seconds. */
  timestamp?: number;
  /** Marks an error bubble so it can be styled distinctly. */
  isError?: boolean;
};
