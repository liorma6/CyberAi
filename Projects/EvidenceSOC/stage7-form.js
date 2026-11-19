"use strict";
const byId = id => document.getElementById(id);
const make = (tag, text) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  return node;
};
const storageKey = "EvidenceSOC:study:" + packet.study + ":" + packet.role;
let answers = {}, index = 0, saved = true;
try {
  const previous = JSON.parse(localStorage.getItem(storageKey) || "{}");
  answers = previous.answers || {};
  if (Number.isInteger(previous.index) && packet.cases[previous.index]) index = previous.index;
} catch { saved = false; }
function persist() {
  try {
    localStorage.setItem(storageKey, JSON.stringify({index, answers}));
    saved = true;
  } catch { saved = false; }
}
function populated(row) {
  return row && ["0","1","2"].includes(row.missing_information)
    && ["1","2","3","4","5"].includes(row.usefulness);
}
function progress() {
  let complete = 0;
  packet.cases.forEach((item, i) => {
    const n = ["A","B"].filter(side => populated(answers[item.code + side])).length;
    byId("case").options[i].textContent = item.code + (n === 2 ? " ✓" : "");
    complete += n;
  });
  byId("count").textContent = "דורגו " + complete + " מתוך 40 תדריכים";
  byId("download").disabled = complete !== 40;
  byId("status").textContent = saved ? (complete === 40 ? "הטופס מלא ומוכן להורדה." : "הטיוטה נשמרת בדפדפן הזה. אפשר לחזור לאותו טופס ולהמשיך.") :
    "הדפדפן אינו שומר טיוטות כאן. השאירו את הטופס פתוח עד להורדת הקובץ.";
}
function refs(list, item) {
  const wrap = make("div");
  wrap.className = "refs";
  for (const ref of list) {
    const detail = make("details");
    detail.append(make("summary", ref));
    detail.addEventListener("toggle", () => {
      if (detail.open && detail.children.length === 1) detail.append(make("pre", JSON.stringify(item.sources[ref], null, 2)));
    });
    wrap.append(detail);
  }
  return wrap;
}
function renderSide(item, side) {
  const key = item.code + side;
  const row = answers[key] ??= {missing_information:"", usefulness:"", comment:""};
  const card = make("section");
  card.className = "brief";
  card.append(make("h2", "תדריך " + side));
  const text = make("div");
  text.dir = "ltr";
  for (const line of item.sides[side].split("\n").filter(Boolean)) {
    if (line.startsWith("Sources: ")) {
      const locations = line.slice(9).split(", ");
      const more = make("details");
      more.append(make("summary", "Source records (" + locations.length + ")"), refs(locations, item));
      text.append(more);
    } else text.append(make("p", line));
  }
  const ratings = make("div");
  ratings.className = "ratings";
  for (const [field, title, range] of [["missing_information","מידע חסר",["0","1","2"]],
                                       ["usefulness","שימושיות",["1","2","3","4","5"]]]) {
    const label = make("label", title + " · " + side);
    const select = make("select");
    select.add(new Option("בחירת ציון", ""));
    for (const value of range) select.add(new Option(value, value));
    select.value = row[field] || "";
    select.addEventListener("change", () => {row[field] = select.value; persist(); progress();});
    label.append(select); ratings.append(label);
  }
  const note = make("label", "הערה · " + side);
  note.className = "note";
  const area = make("textarea");
  area.dir = "auto";
  area.rows = 2;
  area.value = row.comment;
  area.addEventListener("input", () => {row.comment = area.value; persist(); progress();});
  note.append(area); card.append(text, ratings, note);
  return card;
}
function display(newIndex) {
  index = newIndex;
  const item = packet.cases[index];
  byId("file").textContent = item.code;
  byId("context").textContent = item.context;
  byId("timeline").replaceChildren(refs(item.timeline, item));
  byId("sides").replaceChildren(renderSide(item, "A"), renderSide(item, "B"));
  byId("case").value = String(index);
  byId("prev").disabled = !index;
  byId("next").disabled = index === packet.cases.length - 1;
  persist(); progress();
}
byId("role").textContent = "הטופס שלך: " + packet.role + ". יש 20 תיקים. לכל אחד שני תדריכים, A ו־B.";
packet.cases.forEach((item, i) => byId("case").add(new Option(item.code, String(i))));
byId("case").onchange = e => display(Number(e.target.value));
byId("prev").onclick = () => display(index - 1);
byId("next").onclick = () => display(index + 1);
byId("download").onclick = () => {
  const csv = [packet.fields];
  for (const item of packet.cases) for (const side of ["A", "B"]) {
    const answer = answers[item.code + side];
    if (!populated(answer)) return;
    const safeNote = /^\s*[=+@-]/.test(answer.comment) ? "'" + answer.comment : answer.comment;
    const row = {study:packet.study, reviewer:packet.role, file:item.code, side, ...answer, comment:safeNote};
    csv.push(packet.fields.map(field => row[field]));
  }
  const line = cells => cells.map(cell => '"' + String(cell).replaceAll('"', '""') + '"').join(",");
  const url = URL.createObjectURL(new Blob(["\ufeff", csv.map(line).join("\r\n"), "\r\n"], {type:"text/csv;charset=utf-8"}));
  const link = make("a"); link.href = url; link.download = packet.role + "-ratings.csv";
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 3000);
  byId("status").textContent = "קובץ " + link.download + " מוכן. החזירו אותו לרכז הקבוצה.";
};
display(index);
