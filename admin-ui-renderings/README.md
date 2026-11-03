# Admin UI renderings

Static HTML mock-ups of the admin dashboard, for showing executives what it will look like. Sample data only. Nothing here talks to AWS.

Open `index.html` in a browser, or serve the folder: `python3 -m http.server`.

| Page | Shows |
| --- | --- |
| `index.html` | Dashboard: registered students, graded tries against the caps, pass rate, funnel by level, latest activity |
| `students.html` | Students table with assignment, level progress, status, tries today, last result; search and filter |
| `student.html?id=maya` | One student: letter history, tutor note, raw email and reply sent |
| `assignments.html` | Assignments in order, their levels, live version, drafts |
| `upload.html` | Upload flow: drag-drop bundle, bundle layout, validation checks, version |
| `emails.html` | Email templates: editor, live preview, send test |
| `history.html` | Version history and revert for prompts, stories and rubrics |

`style.css` and `app.js` are shared (sidebar, theme, sample data). Light and dark mode follow the system; the sidebar button toggles it.
