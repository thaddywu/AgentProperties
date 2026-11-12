const $ = (s) => document.querySelector(s);
const main = $("#main");
let workspace, reviewId, selected = 0, filename = "policy.txt", busy = false;
let flushReview = async () => true;
const labels = {
  permission: "Capability / access control",
  information_flow: "Information flow",
  lifecycle: "State / lifecycle",
  other: "Other",
  uncertain: "Not sure",
};
const categoryDescriptions = {
  permission: "Who is allowed to perform an action. For example, “Only Professor may approve a job.”",
  information_flow: "What information may be shared with whom. For example, “Master must not receive PhD’s private information.”",
  lifecycle: "What must already be true or have happened before an action. For example, “A job must be approved before it can start.”",
};
const make = (tag, text, cls) => {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (cls) e.className = cls;
  return e;
};
function button(text, action, cls = "") {
  const b = make("button", text, cls);
  b.type = "button";
  b.onclick = action;
  return b;
}
function message(text = "", error = false) {
  $("#message").textContent = text;
  $("#message").className = error ? "error" : "";
}
async function request(path, data) {
  const response = await fetch(path, data === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Study-Token": workspace.token },
    body: JSON.stringify(data),
  });
  const value = await response.json();
  if (!response.ok) throw Error(value.error || "Request failed.");
  return value;
}
async function load() {
  workspace = await request("/api/study");
  reviewId ??= workspace.study.reviews.at(-1).id;
  render();
}
async function work(action) {
  if (busy) return;
  busy = true;
  main.setAttribute("aria-busy", "true");
  message("Working…");
  const buttons = [...document.querySelectorAll("button")].map((b) => [b, b.disabled]);
  buttons.forEach(([b]) => (b.disabled = true));
  try { await action(); message(); }
  catch (e) { message(e.message, true); }
  finally {
    busy = false;
    main.setAttribute("aria-busy", "false");
    buttons.forEach(([b, disabled]) => { if (b.isConnected) b.disabled = disabled; });
    $("#translate-submit").disabled = !workspace?.modelAvailable;
  }
}
function move(action) {
  return work(async () => { if (await flushReview()) await action(); });
}
function review() {
  return workspace.study.reviews.find((r) => r.id === reviewId) || workspace.study.reviews.at(-1);
}
function units() { return workspace.study.reviewUnits[review().id].units; }
let fieldId = 0;
function field(label, control) {
  const e = make("div", undefined, "field"), caption = make("label", label);
  control.id = `field-${++fieldId}`;
  caption.htmlFor = control.id;
  e.append(caption, control);
  return e;
}
function select(options, value = "") {
  const e = make("select");
  for (const [v, t] of options) { const o = make("option", t); o.value = v; e.append(o); }
  e.value = value;
  return e;
}
function choices(title, name, options, value, multiple = false, descriptions = {}) {
  const e = make("fieldset");
  e.append(make("legend", title));
  for (const [v, t] of options) {
    const label = make("label", undefined, "choice"), input = make("input");
    input.type = multiple ? "checkbox" : "radio";
    input.name = name; input.value = v;
    input.checked = multiple ? value.includes(v) : value === v;
    label.append(input, make("span", t));
    if (descriptions[v]) {
      const wrapper = make("div", undefined, "choice-help");
      const tooltip = make("span", descriptions[v], "category-description");
      tooltip.id = `category-help-${++fieldId}`;
      tooltip.setAttribute("role", "tooltip");
      input.setAttribute("aria-describedby", tooltip.id);
      wrapper.append(label, tooltip);
      wrapper.onpointerenter = wrapper.onfocusin = () => wrapper.classList.remove("tooltip-dismissed");
      wrapper.onkeydown = (event) => {
        if (event.key === "Escape") wrapper.classList.add("tooltip-dismissed");
      };
      e.append(wrapper);
    } else {
      e.append(label);
    }
  }
  return e;
}
function toolbar() {
  const row = make("div", undefined, "row toolbar"), r = review();
  if (workspace.study.reviews.length > 1) {
    const version = select(workspace.study.reviews.map((v, i) => [v.id, `Version ${i + 1}`]), r.id);
    version.setAttribute("aria-label", "Review version");
    version.onchange = () => {
      const target = version.value; version.value = r.id;
      move(() => { reviewId = target; selected = 0; render(); });
    };
    row.append(version);
  }
  if (workspace.repositoryJob) {
    const job = workspace.repositoryJob;
    const translate = button("Translate", () => move(() => portJob("translate")), "push");
    translate.disabled = !job.canTranslate || job.status === "running";
    const back = button("Back-translate", () => move(() => portJob("backtranslate")));
    back.disabled = !job.canBacktranslate || job.status === "running";
    row.append(translate, back);
    if (job.status === "running") row.append(button("View progress", () => move(() => watchPortJob())));
  }
  if (workspace.modelAvailable) row.append(button("Open policy", () => move(openEditor), "push"));
  return row;
}
async function watchPortJob() {
  let job;
  do {
    job = await request("/api/port-job");
    if (job.status === "running") await new Promise((resolve) => setTimeout(resolve, 1500));
  } while (job.status === "running");
  workspace = await request("/api/study");
  reviewId = workspace.study.reviews.at(-1).id;
  selected = 0;
  render();
  if (job.status !== "completed") throw Error("Translation stopped. See the saved run log.");
}
async function portJob(stage) {
  await request("/api/port-job", { stage });
  await watchPortJob();
}
function openEditor() {
  $("#source").value = review().source.text;
  filename = review().source.name;
  $("#model-status").textContent = workspace.modelAvailable ? "" : "Model not connected";
  $("#translate-submit").disabled = !workspace.modelAvailable;
  $("#editor").showModal();
}
function original(r, current) {
  const article = make("article", undefined, "card source");
  article.setAttribute("aria-label", "Original policy");
  const chars = Array.from(r.source.text);
  let position = 0;
  for (const [i, unit] of units().entries()) {
    article.append(document.createTextNode(chars.slice(position, unit.start).join("")));
    const b = button(unit.quote, () => move(() => { selected = i; render(); }));
    b.setAttribute("aria-pressed", String(unit.id === current.id));
    article.append(b); position = unit.end;
  }
  article.append(document.createTextNode(chars.slice(position).join("")));
  requestAnimationFrame(() => {
    const active = article.querySelector('[aria-pressed="true"]');
    if (active) article.scrollTop += active.getBoundingClientRect().top - article.getBoundingClientRect().top - article.clientHeight / 3;
  });
  return article;
}
function readingCard(reading) {
  const card = make("div", undefined, "execution-card");
  card.append(make("p", reading.summary, "execution-title"));
  const steps = make("ol", undefined, "execution-fallback");
  for (const text of reading.conditions || []) steps.append(make("li", text));
  card.append(steps);
  return card;
}
function executionCard(procedure) {
  const card = make("section", undefined, "execution-card");
  card.setAttribute("aria-label", procedure.title);
  // Highlight operation names present in the quoted request rules.
  const toolNames = new Set((procedure.evidence || []).flatMap(({ quote }) =>
    [...quote.matchAll(/\bRequest\(\s*[^,()]+,\s*[^,()]+,\s*"([A-Za-z_][A-Za-z_0-9]*)"\s*\)/g)].map((match) => match[1])
  ));
  const lines = make("div", undefined, "execution-lines");
  const stages = [
    ["A", "Recorded information"],
    ["B", "Decision rules"],
    ["C", "Before execution"],
  ];
  const appendStep = (parent, step) => {
    const line = make("div", undefined, `execution-line indent-${step.indent}`);
    for (const token of step.text.split(/([A-Za-z_][A-Za-z_0-9]*)/)) {
      line.append(toolNames.has(token) ? make("code", token) : document.createTextNode(token));
    }
    parent.append(line);
  };
  if (procedure.steps.length && procedure.steps.every((step) => stages.some(([kind]) => kind === step.kind))) {
    for (const [kind, label] of stages) {
      const steps = procedure.steps.filter((step) => step.kind === kind);
      if (!steps.length) continue;
      const section = make("section", undefined, "execution-section");
      section.setAttribute("aria-label", label);
      section.append(make("p", label, "execution-caption"));
      steps.forEach((step) => appendStep(section, step));
      lines.append(section);
    }
  } else {
    procedure.steps.forEach((step) => appendStep(lines, step));
  }
  card.append(lines);
  return card;
}
function renderReview() {
  const r = review(), rows = units();
  const controls = toolbar();
  if (controls.childElementCount) main.append(controls);
  if (!rows.length) { main.append(make("p", "No policy statements to review.", "empty")); return; }
  selected = Math.max(0, Math.min(selected, rows.length - 1));
  const item = rows[selected];
  let saved = workspace.study.judgments[r.id]?.[item.id]?.at(-1) || {};
  const navigation = make("div", undefined, "row sentence-nav");
  const jump = select(rows.map((u, i) => [String(i), `${i + 1} / ${rows.length} · ${u.quote.slice(0, 80)}`]), String(selected));
  jump.setAttribute("aria-label", "Policy sentence");
  jump.onchange = () => {
    const target = Number(jump.value); jump.value = String(selected);
    move(() => { selected = target; render(); });
  };
  const previous = button("Previous", () => move(() => { selected--; render(); }));
  previous.disabled = selected === 0;
  const last = selected === rows.length - 1;
  const next = button("Next", () => move(() => { selected++; render(); }), "primary");
  next.disabled = last;
  navigation.append(previous, jump, next); main.append(navigation);
  const form = make("form", undefined, "columns review-columns");
  const source = make("section", undefined, "policy-column"), panel = make("section", undefined, "review");
  source.append(make("p", r.source.name, "column-caption"), original(r, item));
  panel.append(make("p", "Implemented checks", "column-caption"));
  form.append(source, panel); main.append(form);
  const behaviors = make("div", undefined, "behaviors");
  if (r.execution) {
    const procedures = r.execution.procedures.filter((p) => item.procedureIds.includes(p.id));
    procedures.forEach((p) => behaviors.append(executionCard(p)));
    if (!procedures.length) behaviors.append(make("p", "No corresponding checks found.", "muted"));
  } else {
    const readings = r.behaviors.filter((b) => item.behaviorIds.includes(b.id));
    readings.forEach((reading) => behaviors.append(readingCard(reading)));
    if (!readings.length) behaviors.append(make("p", "No corresponding checks found.", "muted"));
  }
  panel.append(behaviors);
  const assessments = make("div", undefined, "policy-assessments");
  const categories = make("div");
  const judgment = make("div", undefined, "judgment");
  assessments.append(categories, judgment); source.append(assessments);
  judgment.append(choices("Do the programmable checks described on the right match the highlighted policy on the left?", "rating", [
    ["fully_correct", "Fully matches"], ["partially_correct", "Partly matches"],
    ["not_covered", "Does not match / not implemented"], ["not_policy", "Not a policy"], ["unsure", "Not sure"],
  ], saved.rating === "needs_improvement" ? "partially_correct" : saved.rating || ""));
  const note = make("textarea"); note.name = "note"; note.rows = 2; note.maxLength = 4000; note.value = saved.note || "";
  const noteField = field("Comment", note);
  source.append(noteField);
  const extraNote = button("Add a note", () => { noteField.hidden = false; extraNote.hidden = true; note.focus(); }, "quiet");
  source.append(extraNote);
  const categoryChoices = choices("Category", "categories", Object.entries(labels), saved.categories || [], true, categoryDescriptions);
  categories.append(categoryChoices);
  const other = make("input"); other.name = "otherCategory"; other.maxLength = 200; other.value = saved.otherCategory || "";
  const otherField = field("Your category", other); categories.append(otherField);
  const status = make("span", "", "muted"); status.setAttribute("role", "status"); status.id = "save-status";
  const save = make("button", "Save"); save.type = "submit";
  const saveRow = make("div", undefined, "row"); saveRow.append(save, status); source.append(saveRow);
  let timer, chain = Promise.resolve();
  const value = () => {
    const data = new FormData(form);
    return { rating: String(data.get("rating") || ""), categories: data.getAll("categories"),
      note: note.value, otherCategory: data.getAll("categories").includes("other") ? other.value : "" };
  };
  const visibility = () => {
    const v = value(), needsComment = ["partially_correct", "not_covered", "unsure"].includes(v.rating);
    categoryChoices.disabled = v.rating === "not_policy";
    noteField.querySelector("label").textContent = ["partially_correct", "not_covered"].includes(v.rating) ? "What is missing or different?" : "Comment";
    noteField.hidden = !needsComment && !note.value.trim(); extraNote.hidden = !noteField.hidden;
    otherField.hidden = !v.categories.includes("other");
  };
  const persist = async (report = true) => {
    clearTimeout(timer);
    const v = value();
    if (["partially_correct", "not_covered"].includes(v.rating) && !v.note.trim()) {
      if (report) { status.textContent = "Describe the difference before continuing."; note.focus(); }
      return false;
    }
    if (v.categories.includes("other") && !v.otherCategory.trim()) {
      if (report) { status.textContent = "Name your category before continuing."; other.focus(); }
      return false;
    }
    const canonical = (j) => JSON.stringify({ rating: j.rating || "", categories: j.categories || [], note: j.note || "", otherCategory: j.otherCategory || "" });
    const operation = chain.then(async () => {
      if (canonical(v) === canonical(saved)) return;
      status.textContent = "Saving…";
      await request("/api/judgment", { reviewId: r.id, requirementId: item.id, judgment: v });
      saved = v;
      const histories = workspace.study.judgments[r.id] ??= {};
      (histories[item.id] ??= []).push(v);
      status.textContent = "Saved";
    });
    chain = operation.catch(() => {});
    try { await operation; return true; }
    catch (e) { status.textContent = "Not saved. Try again."; message(e.message, true); return false; }
  };
  form.addEventListener("input", () => {
    status.textContent = "Unsaved";
    clearTimeout(timer); timer = setTimeout(() => persist(false), 600);
  });
  form.addEventListener("change", (e) => {
    if (e.target.name === "rating" && e.target.value === "not_policy")
      form.querySelectorAll('[name="categories"]').forEach((input) => { input.checked = false; });
    if (e.target.name === "categories" && e.target.checked) {
      form.querySelectorAll('[name="categories"]').forEach((input) => {
        if (input !== e.target && (e.target.value === "uncertain" || input.value === "uncertain")) input.checked = false;
      });
    }
    visibility(); persist(false);
  });
  form.onsubmit = (e) => { e.preventDefault(); persist(); };
  flushReview = persist;
  visibility();
}
function render() {
  flushReview = async () => true;
  main.replaceChildren();
  const download = document.querySelector('header a[download]');
  download.href = workspace.studentReview ? '/api/review' : '/api/export';
  download.download = workspace.studentReview ? 'review.json' : 'policy-study.json';
  main.setAttribute("aria-busy", "false");
  renderReview();
}
$("#close-editor").onclick = () => $("#editor").close();
$("#document-file").onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  if (file.size > 100000) {
    message("Choose a text document under 100 KB.", true);
    return;
  }
  filename = file.name;
  $("#source").value = await file.text();
};
$("#translate-form").onsubmit = (e) => {
  e.preventDefault();
  work(async () => {
    const result = await request("/api/translate", { text: $("#source").value, name: filename });
    reviewId = result.id;
    selected = 0;
    $("#editor").close();
    await load();
  });
};
load().catch((e) => {
  main.setAttribute("aria-busy", "false");
  message(e.message, true);
});
