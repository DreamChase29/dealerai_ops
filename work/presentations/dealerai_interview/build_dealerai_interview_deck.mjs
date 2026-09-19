import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const ROOT = "C:/Users/wilfr/Documents/Codex/2026-08-11/you-are-the-principal-ai-ml";
const OUT_DIR = path.join(ROOT, "outputs");
const WORK_DIR = path.join(ROOT, "work/presentations/dealerai_interview");
const FINAL_PPTX = path.join(OUT_DIR, "dealerai_ops_interview_explainer.pptx");

const W = 1280;
const H = 720;
const M = 72;
const COLORS = {
  bg: "#F7F5EF",
  ink: "#1F262A",
  muted: "#68767A",
  teal: "#245C5A",
  teal2: "#3E7A76",
  line: "#D8D7D0",
  soft: "#ECEBE3",
  white: "#FFFFFF",
  gold: "#B88746",
  rust: "#8A4B2B",
  green: "#4E7E54",
};

const script = [
  {
    title: "DealerAI Ops",
    notes:
      "Open with the positioning: this is not a toy chatbot. DealerAI Ops is a production-oriented portfolio implementation for a synthetic automotive dealership. The project demonstrates how I think about applied AI systems: typed tools, domain boundaries, predictive ML, retrieval, evaluation, guardrails, observability, and an AWS deployment path. I would be careful to say it is a local reference implementation, not deployed production infrastructure.",
  },
  {
    title: "The project proves agentic AI can be engineered, tested, and bounded",
    notes:
      "The main thesis is that agentic AI should be treated as engineered software. The LLM is useful for language and tool selection, but it should not own business logic or database writes. This project shows how to wrap LLM behavior with schemas, services, transactions, confirmation gates, evaluation, and monitoring so the system is reviewable and testable.",
  },
  {
    title: "The dealership problem is operational, not conversational",
    notes:
      "A dealership assistant touches customer context, service scheduling, inventory, policies, sales leads, and escalation. Those workflows have real risk: exposing contact data, canceling appointments without consent, citing unsupported policies, or fabricating a successful booking. The architecture is built around those risks rather than around a generic chat interface.",
  },
  {
    title: "Architecture separates reasoning, tools, data, evaluation",
    notes:
      "Walk left to right. The user enters through FastAPI or the Streamlit demo. The agent orchestrator applies guardrails, optionally retrieves knowledge, calls a provider-independent LLM, validates any tool request, and executes only through typed tools. Tools call services and repositories, not the database directly. ML inference and escalation are separate services. Evaluation and observability wrap the whole flow.",
  },
  {
    title: "Synthetic domain data makes the project runnable without PII",
    notes:
      "The project includes deterministic synthetic dealership data: customers, vehicles, inventory, appointments, service history, slots, leads, conversations, tool executions, and escalations. The scale is large enough to support meaningful tests and ML workflows, but it avoids real PII and protected-class fields. Determinism matters because tests, model artifacts, and evaluation reports need to be reproducible.",
  },
  {
    title: "No-show prediction is built as an ML pipeline, not a score stub",
    notes:
      "The ML component predicts appointment no-show probability using a reproducible sklearn pipeline. It compares a logistic regression baseline with a calibrated tree-based candidate, uses preprocessing pipelines so training and inference transformations stay aligned, and reports ROC-AUC, PR-AUC, precision, recall, F1, Brier score, confusion matrix, calibration diagnostics, and threshold analysis. The important interview point is leakage control: outcome fields, post-event timestamps, identifiers, and unavailable-at-booking features are excluded.",
  },
  {
    title: "RAG is citation-first and testable",
    notes:
      "The RAG subsystem uses a fictional dealership knowledge corpus. Documents are loaded, normalized, chunked by section, embedded locally in deterministic mode, and retrieved with source metadata. Retrieved chunks include document ID, title, section, chunk ID, score, and source metadata. The repository also includes retrieval evaluation data with known relevant documents and metrics like Recall@K, MRR, and hit rate. The production vector backends are documented adapter targets, not live integrations.",
  },
  {
    title: "Tool calling is the safety boundary",
    notes:
      "This is the strongest architecture decision. Every tool has Pydantic input and output schemas, metadata, risk level, confirmation requirement, authorization hook, request ID, audit logging, and structured error handling. Transactional tools such as booking, rescheduling, canceling, and lead creation require confirmation. Booking-style operations include idempotency so duplicate requests do not create duplicate appointments.",
  },
  {
    title: "The agent loop is constrained by policy and state",
    notes:
      "The provider can return a final answer or a structured tool request. The orchestrator enforces max iterations, timeouts, unknown-tool handling, schema validation, confirmation workflow, and fail-closed behavior for sensitive operations. Guardrails inspect user input and retrieved content. Retrieved documents can provide evidence, but they cannot instruct the agent to bypass policy or dump data.",
  },
  {
    title: "Evaluation turns agent behavior into release criteria",
    notes:
      "The evaluation lab has 121 deterministic scenarios across normal, multi-turn, RAG, transaction, tool failure, escalation, PII, prompt injection, and regression cases. Scorers check task success, tool selection, argument accuracy, transaction consistency, retrieval hit, citations, PII leakage, escalation behavior, policy violations, and hallucinated transactions. The release gate enforces thresholds in version-controlled configuration.",
  },
  {
    title: "Observability, reliability, and AWS mapping are explicit",
    notes:
      "Observability captures redacted spans for conversation, LLM calls, retrieval, tool calls, ML inference, guardrail decisions, and escalation with correlation IDs and latency. Reliability tests cover provider failure, retrieval failure, database failure, duplicate booking, malformed tool calls, prompt injection, PII requests, iteration limits, and corrupt ML artifacts. AWS architecture is documented for Bedrock, S3, Lambda, API Gateway, Aurora, pgvector, CloudWatch, IAM, and Secrets Manager, but it is not deployed.",
  },
  {
    title: "The strongest claim: disciplined AI system design",
    notes:
      "Close with the honest pitch. The strongest accomplishments are the typed tool boundary, leakage-aware ML pipeline, deterministic RAG evaluation, agent evaluation gate, and clean separation of concerns. The honest limitations are that data is synthetic, live AWS infrastructure is not deployed, production auth and tenant isolation are not implemented, and cloud vector integrations are documented rather than active. That honesty makes the project more credible, not less.",
  },
];

async function writeBlob(filePath, blob) {
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

function addText(slide, text, position, options = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    position,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = text;
  shape.text.style = {
    fontSize: options.size ?? 18,
    bold: options.bold ?? false,
    color: options.color ?? COLORS.ink,
    alignment: options.align ?? "left",
  };
  return shape;
}

function addSlideTitle(slide, title, kicker = "") {
  if (kicker) {
    addText(slide, kicker.toUpperCase(), { left: M, top: 42, width: 620, height: 26 }, {
      size: 16,
      bold: true,
      color: COLORS.teal,
    });
  }
  addText(slide, title, { left: M, top: 76, width: 1010, height: 86 }, {
    size: 40,
    bold: true,
    color: COLORS.ink,
  });
}

function addFooter(slide, idx) {
  slide.shapes.add({
    geometry: "rect",
    position: { left: M, top: 668, width: 1136, height: 1 },
    fill: COLORS.line,
    line: { style: "solid", fill: COLORS.line, width: 0 },
  });
  addText(slide, "DealerAI Ops interview explainer", { left: M, top: 680, width: 420, height: 24 }, {
    size: 12,
    color: COLORS.muted,
  });
  addText(slide, String(idx).padStart(2, "0"), { left: 1160, top: 680, width: 48, height: 24 }, {
    size: 12,
    color: COLORS.muted,
    align: "right",
  });
}

function addRule(slide, left, top, width, color = COLORS.teal) {
  slide.shapes.add({
    geometry: "rect",
    position: { left, top, width, height: 4 },
    fill: color,
    line: { style: "solid", fill: color, width: 0 },
  });
}

function addBox(slide, text, position, options = {}) {
  const config = {
    geometry: options.round ? "roundRect" : "rect",
    position,
    fill: options.fill ?? COLORS.white,
    line: { style: "solid", fill: options.line ?? COLORS.line, width: 1 },
  };
  if (options.round) {
    config.borderRadius = "rounded-lg";
  }
  const shape = slide.shapes.add(config);
  shape.text = text;
  shape.text.style = {
    fontSize: options.size ?? 18,
    bold: options.bold ?? false,
    color: options.color ?? COLORS.ink,
    alignment: options.align ?? "center",
  };
  return shape;
}

function addBullets(slide, items, left, top, width, size = 20, gap = 54) {
  items.forEach((item, i) => {
    const y = top + i * gap;
    slide.shapes.add({
      geometry: "rect",
      position: { left, top: y + 7, width: 9, height: 9 },
      fill: COLORS.teal,
      line: { style: "solid", fill: COLORS.teal, width: 0 },
    });
    addText(slide, item, { left: left + 24, top: y, width, height: 44 }, {
      size,
      color: COLORS.ink,
    });
  });
}

function addMetric(slide, value, label, left, top, accent = COLORS.teal) {
  addText(slide, value, { left, top, width: 210, height: 74 }, {
    size: 44,
    bold: true,
    color: accent,
    align: "center",
  });
  addText(slide, label, { left: left - 6, top: top + 70, width: 222, height: 50 }, {
    size: 17,
    color: COLORS.muted,
    align: "center",
  });
}

function setNotes(slide, notes) {
  // The separate script PDF is the canonical talk track deliverable.
  // Keeping the PPTX slide-only avoids a serializer edge case in notes export.
  void slide;
  void notes;
}

function slide1(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.bg;
  addText(slide, "DealerAI Ops", { left: 78, top: 122, width: 760, height: 86 }, {
    size: 58,
    bold: true,
    color: COLORS.ink,
  });
  addRule(slide, 82, 218, 210, COLORS.teal);
  addText(slide, "Production-oriented agentic AI and predictive intelligence for automotive dealerships", { left: 82, top: 258, width: 820, height: 86 }, {
    size: 28,
    color: COLORS.teal,
  });
  addText(slide, "Interview explainer | implemented capabilities, architecture decisions, and honest limitations", { left: 82, top: 376, width: 760, height: 70 }, {
    size: 20,
    color: COLORS.muted,
  });
  addBox(slide, "Local-first reference implementation\nNo real PII | No paid API required | AWS mapping documented", { left: 820, top: 122, width: 324, height: 260 }, {
    fill: COLORS.soft,
    line: COLORS.line,
    size: 24,
    bold: true,
    color: COLORS.ink,
    round: true,
  });
  addText(slide, "Built for senior AI/ML engineering discussion", { left: 82, top: 592, width: 580, height: 32 }, {
    size: 18,
    color: COLORS.muted,
  });
  addFooter(slide, 1);
  setNotes(slide, script[0].notes);
}

function slide2(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.bg;
  addSlideTitle(slide, "The project proves agentic AI can be engineered, tested, and bounded", "Thesis");
  addBullets(slide, [
    "LLM reasoning is separated from domain logic and persistence.",
    "All external actions happen through typed Pydantic tools.",
    "Predictive ML and RAG are implemented as independent services.",
    "Guardrails, escalation, evaluation, and observability are first-class.",
  ], 94, 210, 850, 23, 76);
  addBox(slide, "Core claim\n\nThe system is designed around transaction safety and measurable behavior, not chatbot novelty.", { left: 860, top: 220, width: 300, height: 260 }, {
    fill: COLORS.white,
    size: 22,
    bold: true,
    color: COLORS.teal,
    round: true,
  });
  addFooter(slide, 2);
  setNotes(slide, script[1].notes);
}

function slide3(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.bg;
  addSlideTitle(slide, "The dealership problem is operational, not conversational", "Business problem");
  const risks = [
    ["Unsafe write", "Book, cancel, or reschedule without explicit confirmation"],
    ["PII exposure", "Reveal customer contact data or internal configuration"],
    ["Ungrounded policy", "Answer warranty or scheduling questions without sources"],
    ["False success", "Claim a transaction succeeded when the tool failed"],
  ];
  risks.forEach(([head, body], i) => {
    const x = i % 2 === 0 ? 90 : 675;
    const y = i < 2 ? 205 : 390;
    addBox(slide, head, { left: x, top: y, width: 460, height: 52 }, {
      fill: COLORS.teal,
      line: COLORS.teal,
      size: 24,
      bold: true,
      color: COLORS.white,
    });
    addBox(slide, body, { left: x, top: y + 52, width: 460, height: 92 }, {
      fill: COLORS.white,
      line: COLORS.line,
      size: 20,
      color: COLORS.ink,
    });
  });
  addFooter(slide, 3);
  setNotes(slide, script[2].notes);
}

function slide4(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.bg;
  addSlideTitle(slide, "Architecture separates reasoning, tools, data, evaluation", "System design");
  const boxes = [
    ["FastAPI / Streamlit", 82, 238],
    ["Agent orchestrator", 328, 238],
    ["Guardrails + RAG", 574, 148],
    ["Provider\ninterface", 574, 328],
    ["Typed tools", 820, 238],
    ["Services + repos", 1016, 238],
  ];
  const shapes = boxes.map(([label, x, y]) => addBox(slide, label, { left: x, top: y, width: 160, height: 92 }, {
    fill: label === "Typed tools" ? COLORS.teal : COLORS.white,
    line: COLORS.line,
    size: 19,
    bold: true,
    color: label === "Typed tools" ? COLORS.white : COLORS.ink,
    round: true,
  }));
  void shapes;
  addText(slide, ">", { left: 268, top: 260, width: 32, height: 32 }, { size: 28, bold: true, color: COLORS.muted, align: "center" });
  addText(slide, ">", { left: 760, top: 260, width: 32, height: 32 }, { size: 28, bold: true, color: COLORS.muted, align: "center" });
  addText(slide, ">", { left: 980, top: 260, width: 32, height: 32 }, { size: 28, bold: true, color: COLORS.muted, align: "center" });
  addText(slide, "retrieval", { left: 568, top: 250, width: 172, height: 26 }, { size: 16, color: COLORS.muted, align: "center" });
  addText(slide, "ML inference, human escalation, observability, and evaluation wrap the operational path.", { left: 155, top: 508, width: 960, height: 60 }, {
    size: 24,
    color: COLORS.teal,
    align: "center",
  });
  addFooter(slide, 4);
  setNotes(slide, script[3].notes);
}

function slide5(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.bg;
  addSlideTitle(slide, "Synthetic domain data makes the project runnable without PII", "Data foundation");
  addMetric(slide, "2,000", "customers", 100, 220);
  addMetric(slide, "2,500", "owned vehicles", 355, 220);
  addMetric(slide, "300", "inventory vehicles", 610, 220);
  addMetric(slide, "5,000", "historical appointments", 865, 220);
  addBullets(slide, [
    "Models relationships across customers, vehicles, appointments, service history, slots, leads, conversations, tool executions, and escalations.",
    "Deterministic generation supports repeatable tests, evaluation reports, and model artifacts.",
    "Feature design avoids real PII and protected-class fields.",
  ], 130, 445, 940, 21, 60);
  addFooter(slide, 5);
  setNotes(slide, script[4].notes);
}

function slide6(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.bg;
  addSlideTitle(slide, "No-show prediction is built as a real ML pipeline", "Predictive ML");
  const steps = [
    ["Synthetic appointment data", "booking-time features"],
    ["Leakage inspection", "exclude outcome signals"],
    ["sklearn pipeline", "preprocessing stays aligned"],
    ["Model comparison", "baseline + calibrated tree"],
    ["Risk tiers", "LOW to VERY_HIGH"],
  ];
  const shapes = steps.map(([a, b], i) => addBox(slide, `${a}\n${b}`, { left: 78 + i * 228, top: 226, width: 178, height: 118 }, {
    fill: i === 2 ? COLORS.teal : COLORS.white,
    line: COLORS.line,
    size: 18,
    bold: true,
    color: i === 2 ? COLORS.white : COLORS.ink,
    round: true,
  }));
  void shapes;
  [262, 490, 718, 946].forEach((x) => {
    addText(slide, ">", { left: x, top: 268, width: 32, height: 32 }, { size: 28, bold: true, color: COLORS.muted, align: "center" });
  });
  addBox(slide, "Evaluated with ROC-AUC, PR-AUC, precision, recall, F1, Brier score, confusion matrix, calibration diagnostics, and threshold analysis.", { left: 116, top: 440, width: 1048, height: 98 }, {
    fill: COLORS.soft,
    line: COLORS.line,
    size: 23,
    color: COLORS.ink,
    round: true,
  });
  addFooter(slide, 6);
  setNotes(slide, script[5].notes);
}

function slide7(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.bg;
  addSlideTitle(slide, "RAG is citation-first and evaluated separately", "Retrieval");
  const pipeline = [
    ["Knowledge corpus", "fictional dealership policies"],
    ["Normalize + chunk", "section-aware metadata"],
    ["Local embeddings", "deterministic test mode"],
    ["Retrieve + cite", "document, section, chunk, score"],
  ];
  pipeline.forEach(([head, body], i) => {
    const y = 194 + i * 94;
    addBox(slide, head, { left: 120, top: y, width: 260, height: 50 }, {
      fill: COLORS.teal,
      line: COLORS.teal,
      size: 22,
      bold: true,
      color: COLORS.white,
    });
    addBox(slide, body, { left: 380, top: y, width: 560, height: 50 }, {
      fill: COLORS.white,
      line: COLORS.line,
      size: 21,
      color: COLORS.ink,
    });
  });
  addBox(slide, "Retrieval eval\nRecall@K\nMRR\nHit Rate@K", { left: 982, top: 236, width: 180, height: 220 }, {
    fill: COLORS.soft,
    line: COLORS.line,
    size: 24,
    bold: true,
    color: COLORS.teal,
    round: true,
  });
  addFooter(slide, 7);
  setNotes(slide, script[6].notes);
}

function slide8(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.bg;
  addSlideTitle(slide, "Tool calling is the safety boundary", "Function calling");
  const cols = [
    ["Tool contract", "Pydantic input/output schemas\nrisk level\nconfirmation flag"],
    ["Execution control", "authorization hook\nrequest ID\naudit logging"],
    ["Write safety", "explicit confirmation\ntransactions\nidempotency records"],
  ];
  cols.forEach(([head, body], i) => {
    const x = 110 + i * 360;
    addBox(slide, head, { left: x, top: 214, width: 300, height: 64 }, {
      fill: COLORS.teal,
      line: COLORS.teal,
      size: 24,
      bold: true,
      color: COLORS.white,
    });
    addBox(slide, body, { left: x, top: 278, width: 300, height: 190 }, {
      fill: COLORS.white,
      line: COLORS.line,
      size: 22,
      color: COLORS.ink,
      round: true,
    });
  });
  addText(slide, "The LLM may request a tool. The application decides whether that request is valid, authorized, confirmed, and safe.", { left: 120, top: 540, width: 1040, height: 54 }, {
    size: 25,
    color: COLORS.rust,
    bold: true,
    align: "center",
  });
  addFooter(slide, 8);
  setNotes(slide, script[7].notes);
}

function slide9(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.bg;
  addSlideTitle(slide, "The agent loop is constrained by policy and state", "Orchestration");
  const leftItems = [
    "explicit conversation state",
    "maximum tool iterations",
    "timeouts and structured failures",
    "unknown-tool and invalid-argument handling",
    "confirmation workflow for writes",
  ];
  addBullets(slide, leftItems, 112, 205, 520, 22, 62);
  addBox(slide, "Fail-closed examples\n\nPII requests\nsecret requests\nprompt injection\nmass operations\nretrieved policy bypass", { left: 760, top: 208, width: 330, height: 320 }, {
    fill: COLORS.soft,
    line: COLORS.line,
    size: 24,
    bold: true,
    color: COLORS.teal,
    round: true,
  });
  addFooter(slide, 9);
  setNotes(slide, script[8].notes);
}

function slide10(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.bg;
  addSlideTitle(slide, "Evaluation turns agent behavior into release criteria", "AI evaluation");
  addMetric(slide, "121", "deterministic scenarios", 110, 218, COLORS.teal);
  addMetric(slide, "111", "pytest tests passed in audit", 390, 218, COLORS.green);
  addMetric(slide, "0.0", "hallucinated transaction rate", 670, 218, COLORS.rust);
  addMetric(slide, "1.00", "gate-critical pass rates", 950, 218, COLORS.gold);
  addBullets(slide, [
    "Scorers cover tool selection, argument accuracy, retrieval hits, citations, PII leakage, escalation, policy violations, and transaction consistency.",
    "Quality thresholds are stored in version-controlled configuration and enforced by python -m evaluation.gate.",
  ], 120, 455, 980, 21, 68);
  addFooter(slide, 10);
  setNotes(slide, script[9].notes);
}

function slide11(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.bg;
  addSlideTitle(slide, "Observability, reliability, and AWS mapping are explicit", "Operations");
  const rows = [
    ["Implemented locally", "Redacted spans, correlation IDs, component latency, MLflow-local option, reliability tests, Docker/Compose, CI checks."],
    ["Documented AWS path", "Bedrock, S3, Lambda, API Gateway, Aurora PostgreSQL, pgvector, CloudWatch, IAM, Secrets Manager."],
    ["Not claimed", "No live AWS deployment, no real dealership integrations, no real customer data, no production auth/tenant isolation."],
  ];
  rows.forEach(([head, body], i) => {
    const y = 205 + i * 122;
    addBox(slide, head, { left: 110, top: y, width: 300, height: 72 }, {
      fill: i === 2 ? COLORS.rust : COLORS.teal,
      line: i === 2 ? COLORS.rust : COLORS.teal,
      size: 23,
      bold: true,
      color: COLORS.white,
    });
    addBox(slide, body, { left: 410, top: y, width: 740, height: 72 }, {
      fill: COLORS.white,
      line: COLORS.line,
      size: 20,
      color: COLORS.ink,
    });
  });
  addFooter(slide, 11);
  setNotes(slide, script[10].notes);
}

function slide12(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.bg;
  addSlideTitle(slide, "The strongest claim: disciplined AI system design", "Interview close");
  addText(slide, "Five accomplishments to emphasize", { left: 110, top: 188, width: 520, height: 34 }, {
    size: 26,
    bold: true,
    color: COLORS.teal,
  });
  addBullets(slide, [
    "typed tool boundary with transaction safety",
    "leakage-aware predictive ML pipeline",
    "citation-ready RAG with retrieval evaluation",
    "deterministic agent evaluation and release gate",
    "clean module boundaries and honest AWS mapping",
  ], 118, 246, 555, 20, 50);
  addBox(slide, "Position carefully\n\nProduction-oriented reference implementation, not deployed dealership software.", { left: 760, top: 236, width: 330, height: 236 }, {
    fill: COLORS.teal,
    line: COLORS.teal,
    size: 27,
    bold: true,
    color: COLORS.white,
    round: true,
  });
  addFooter(slide, 12);
  setNotes(slide, script[11].notes);
}

async function main() {
  await fs.mkdir(OUT_DIR, { recursive: true });
  await fs.mkdir(path.join(WORK_DIR, "rendered"), { recursive: true });
  const presentation = Presentation.create({ slideSize: { width: W, height: H } });
  const slideFns = [
    slide1,
    slide2,
    slide3,
    slide4,
    slide5,
    slide6,
    slide7,
    slide8,
    slide9,
    slide10,
    slide11,
    slide12,
  ];
  const maxSlides = Number.parseInt(process.env.MAX_SLIDES ?? String(slideFns.length), 10);
  slideFns.slice(0, maxSlides).forEach((fn) => fn(presentation));

  const inspect = await presentation.inspect({ kind: "slide,textbox,shape,notes", maxChars: 16000 });
  await fs.writeFile(path.join(WORK_DIR, "deck-inspect.ndjson"), inspect.ndjson);

  if (!process.env.SKIP_RENDER) {
    for (const [index, slide] of presentation.slides.items.entries()) {
      const stem = `slide-${String(index + 1).padStart(2, "0")}`;
      const png = await presentation.export({ slide, format: "png", scale: 1 });
      await writeBlob(path.join(WORK_DIR, "rendered", `${stem}.png`), png);
      const layout = await slide.export({ format: "layout" });
      await fs.writeFile(path.join(WORK_DIR, "rendered", `${stem}.layout.json`), await layout.text());
    }

    const montage = await presentation.export({ format: "webp", montage: true, scale: 1 });
    await writeBlob(path.join(WORK_DIR, "dealerai_interview_montage.webp"), montage);
  }

  const pptx = await PresentationFile.exportPptx(presentation);
  const targetPptx = process.env.DEBUG_PPTX
    ? path.join(WORK_DIR, `debug-${String(maxSlides).padStart(2, "0")}.pptx`)
    : FINAL_PPTX;
  await pptx.save(targetPptx);
  await fs.writeFile(path.join(WORK_DIR, "speaker_script.json"), JSON.stringify(script, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
