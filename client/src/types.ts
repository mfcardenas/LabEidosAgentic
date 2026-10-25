// Contratos que consume el cliente. En la iteración 1.2 se generan desde contracts/*.schema.json.

export type Path = { path: string };
export type Template = { template: string };
export type Value = string | number | boolean | Path | Template;
export type Condition = Path | { not: Path };
export type Navigate = { function: "navigate"; args: { view: string; params?: Record<string, Value> } };
export type CommandAction = { command: string; input?: Record<string, Value> };
export type Action = Navigate | CommandAction;
export type Format = "text" | "person" | "badge" | "status" | "date" | "datetime" | "email" | "number";

export interface Component {
  id: string;
  component: string;
  visible?: Condition;
  children?: string[];
  actions?: string[];
  [prop: string]: unknown;
}

export interface ScreenDocument {
  contract: "eidos-ui/1";
  view: string;
  root: string;
  components: Component[];
}

export interface FieldSpec {
  tipo: "texto" | "email" | "enum" | "booleano" | "fecha" | "fechahora" | "numero" | "referencia";
  etiqueta: string;
  requerido: boolean;
  soloLectura: boolean;
  auto: string | null;
  valores: { valor: string; etiqueta: string; tono: string }[];
  si: string | null;
  no: string | null;
  max: number | null;
  min: number | null;
}

export interface EntitySpec {
  entidad: string;
  etiqueta: string;
  plural: string;
  campoTitulo: string;
  campos: Record<string, FieldSpec>;
}

export interface Manifest {
  app: { id: string; nombre: string; proposito: string; inicio: string; sugerencias: { etiqueta: string; vista?: string; params?: Record<string, unknown>; texto?: string }[] };
  version: string;
  published: boolean;
  views: Record<string, { titulo: string; patron: string; entidad: string; parametros: { id: boolean; filtro: boolean; prefill: boolean } }>;
  entities: Record<string, EntitySpec>;
  commands: Record<string, { tipo: string; entidad: string; etiqueta: string | null }>;
}

export interface ViewResponse {
  view: string;
  params: Record<string, unknown>;
  document: ScreenDocument;
  data: Record<string, unknown>;
  source: "published" | "provisional" | "on_demand" | "fallback";
  artifact: string | null;
  trace?: { step: string; text: string; risk?: string; route?: string; findings?: Record<string, number>; profile?: string }[];
}

export interface CommandResult {
  ok: boolean;
  record?: Record<string, unknown>;
  errors?: Record<string, string>;
  next?: { view: string; params: Record<string, unknown> };
}
