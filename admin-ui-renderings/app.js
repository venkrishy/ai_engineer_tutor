/* Shared by every rendering: sidebar, theme toggle, toast, and the sample data. Sample data only. */
const LOGO = `<svg viewBox="0 0 40 40" aria-hidden="true"><rect width="40" height="40" rx="10" fill="#0f766e"/><path d="M8 15 20 9l12 6-12 6z" fill="#fff"/><path d="M13 20v6c0 2 3.5 4 7 4s7-2 7-4v-6l-7 3.5z" fill="#99e6dc"/><path d="M32 16v8" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg>`;
const ICONS = {
  dash: '<path d="M3 12 12 4l9 8"/><path d="M5 10v10h14V10"/>',
  students: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.5 3-6 6.5-6s6.5 2.5 6.5 6"/><path d="M16 5a3.5 3.5 0 0 1 0 6.5M18 14c2.2.6 3.5 2.6 3.5 5"/>',
  assignments: '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 13h7M9 17h7"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v4h16v-4"/>',
  emails: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
  history: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 8v5l3 2"/>',
};
const NAV = [
  ["index.html", "dash", "Dashboard"],
  ["students.html", "students", "Students"],
  ["assignments.html", "assignments", "Assignments"],
  ["upload.html", "upload", "Upload assignment"],
  ["emails.html", "emails", "Email templates"],
  ["history.html", "history", "Version history"],
];
function mountShell(active) {
  const links = NAV.map(([href, ic, label]) =>
    `<a href="${href}" class="${href === active ? "on" : ""}"><svg viewBox="0 0 24 24">${ICONS[ic]}</svg>${label}</a>`).join("");
  document.getElementById("side").innerHTML =
    `<a class="brand" href="index.html">${LOGO}<span>Tutor Desk<small>Admin</small></span></a>
     <nav class="nav">${links}</nav>
     <button class="theme" id="theme" type="button">Toggle dark mode</button>
     <div class="foot">Rendering with sample data.<br>Nothing here is connected.</div>`;
  document.getElementById("theme").onclick = () => {
    const dark = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim() === "#0b1220";
    document.documentElement.dataset.theme = dark ? "light" : "dark";
  };
}
function toast(text) {
  let t = document.querySelector(".toast");
  if (!t) { t = document.createElement("div"); t.className = "toast"; document.body.append(t); }
  t.textContent = text; t.classList.add("on");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("on"), 2400);
}
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* Triage tickets has 3 levels: Classify, Route, Reply. */
const LEVELS = ["Classify", "Route", "Reply"];
const STUDENTS = [
  { id: "maya", name: "Maya Okafor", email: "maya.okafor@example.com", level: 3, cleared: 2, status: "Active", tries: 2, last: "Today 09:12", result: "Fail", joined: "Nov 2" },
  { id: "daniel", name: "Daniel Reyes", email: "daniel.reyes@example.com", level: 2, cleared: 1, status: "Active", tries: 1, last: "Today 08:40", result: "Pass", joined: "Nov 2" },
  { id: "priya", name: "Priya Nair", email: "priya.nair@example.com", level: 3, cleared: 3, status: "Finished", tries: 0, last: "Yesterday 17:05", result: "Pass", joined: "Nov 1" },
  { id: "tomas", name: "Tomas Berg", email: "tomas.berg@example.com", level: 1, cleared: 0, status: "Active", tries: 4, last: "Today 10:31", result: "Fail", joined: "Nov 3" },
  { id: "aisha", name: "Aisha Rahman", email: "aisha.rahman@example.com", level: 1, cleared: 0, status: "Welcomed", tries: 0, last: "Today 07:55", result: "None", joined: "Nov 3" },
  { id: "lars", name: "Lars Nilsson", email: "lars.nilsson@example.com", level: 2, cleared: 1, status: "Cap hit", tries: 5, last: "Today 10:02", result: "Cap hit", joined: "Nov 2" },
  { id: "chen", name: "Chen Wei", email: "chen.wei@example.com", level: 1, cleared: 0, status: "Welcomed", tries: 0, last: "Yesterday 21:18", result: "None", joined: "Nov 2" },
  { id: "sofia", name: "Sofia Marin", email: "sofia.marin@example.com", level: 2, cleared: 1, status: "Active", tries: 3, last: "Today 06:47", result: "Fail", joined: "Nov 1" },
];
const pillFor = r => ({ Pass: "good", Fail: "bad", "Cap hit": "warn", Finished: "good", Active: "brand", Welcomed: "", None: "" }[r] ?? "");
