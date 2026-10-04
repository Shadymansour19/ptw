# Risk Assessment Builder

A fully local, standalone web app for building, printing and archiving Risk
Assessments. No server, no backend, no internet connection needed — every
library it uses is vendored under `vendor/` and every font under
`vendor/fonts/`.

## Running it

Just open `index.html` in a browser (double-click it, or `File > Open`).
There is nothing to install and nothing to build.

Tip: to get a desktop-app-like shortcut (its own icon, its own window, no
address bar, pinnable to the taskbar), use Chrome/Edge's "Create Shortcut…
→ Open as window" (under the three-dot menu while the page is open) — no
server or installation step needed, it works directly from the file. See
"Desktop shortcut" below for the full steps.

Dates are entered and displayed as `dd/mm/yyyy` throughout (details form and
exports).

Your in-progress assessment is kept in the browser's local storage, so
closing and reopening the page keeps your work. Use **Project → Save Project
(.json)** to export a portable backup/snapshot you can reload later or move
to another computer (**Project → Load Project**).

## Desktop shortcut (pinnable to the Windows taskbar)

Chrome and Edge can turn this page into its own app-like window with its own
icon, separate from your regular browser windows - no install step, no
server, works straight from `index.html`:

1. Open `index.html` in Chrome or Edge.
2. Click the three-dot menu (top-right) → **Cast, save, and share** (Chrome)
   or just look for **Apps** (Edge) → **Create shortcut…**.
3. Check **"Open as window"**, then click **Create**.
4. A shortcut appears on your Desktop (or Start Menu, depending on the
   browser/Windows version) - it already uses this page's own icon (the
   Rashpetco logo) and its title ("Specific Risk Assessment Builder") as its
   name, so nothing else to rename.
5. Right-click that shortcut (or find it in the Start Menu) → **Pin to
   taskbar**.

A plain Windows shortcut to the `.html` file (right-click → **Create
shortcut**) will also open the page, but Windows generally won't let you pin
a document shortcut like that to the taskbar - only the browser's "Open as
window" shortcut above is reliably pinnable, since it technically launches
the browser itself with this page as its app.

## Adding risk items

Three ways, from the toolbar:

- **+ Add Item** — a manual entry form with an English and an Arabic box for
  every text field.
- **Add from General RA Library** — pick from the built-in library of common
  risk assessments (working at height, hot work, confined space, etc).
- **Import from Excel** — upload an `.xlsx`/`.csv` file. Use **Download Excel
  Template** first to get a file with the exact expected column headers (they
  are matched case-insensitively, so minor header formatting differences are
  fine). Rows that fail validation (missing required text, severity outside
  1–5, likelihood outside A–E) are skipped and listed after import; valid
  rows are still added.

## Risk item fields (matches the PTW Qt app's risk item model)

Each risk item has exactly the same fields as a PTW risk item: **Hazard**,
**Effect**, **Free Analysis** (Severity+Likelihood before control, e.g.
"4C"), **Control**, **Controlled Analysis** (Severity+Likelihood after
control, e.g. "2A"), **Evaluation**.

The one difference from the Qt app: **Evaluation is auto-computed** from the
Controlled Analysis via the risk matrix below, instead of being typed in manually.

## The risk matrix

`js/matrix.js` is the single file that decides the risk level (Low / Low Medium /
High Medium / High) for every Severity+Likelihood combination (e.g. "4C").

## The general RA library

`js/globalRisks.js` is a plain, editable JavaScript array grouped by
category. Add, remove or edit entries directly — copy an existing item object
to add a new one, or copy a `{ category, items: [...] }` block to add a new
category.

## Exporting

**Export → Export as PDF / Export as Word** asks for a language: English
only, Arabic only, or Both. In "Both" mode, every item shows its English
content first and its Arabic content directly below it, within the same
row/cell, as requested.

- PDF export renders the real HTML report and rasterizes it page by page
  (html2canvas → jsPDF), so Arabic text is shaped and positioned exactly as
  the browser renders it — no font-shaping hacks needed. Table rows are never
  split across a page break.
- Word export builds a native `.docx` (via docx.js) with real, editable
  Arabic/English text and correct right-to-left paragraph direction — it is
  not a picture, so it is fully editable afterwards in Word.

## Printing

**Print** asks for a language: English only, Arabic only, or Both.
In "Both" mode, every item shows its English content first and its
Arabic content directly below it, within the same row/cell, as requested.
The file is redirected to print directly without local download. 

## Relationship to the PTW (Qt) app

This is a deliberately separate, independent project from
the QT PTW app (different stack: static HTML/JS vs. Python/Qt+server).
It does not share code or a database with the PTW app.

## Project structure

```
index.html             app shell
css/style.css          all styling, incl. @font-face for offline Arabic/Latin fonts
js/matrix.js            <-- edit this for the real risk matrix
js/globalRisks.js       <-- edit this to manage the general RA library
js/store.js             state + localStorage persistence
js/excelImport.js       Excel template + import/validation
js/exportPdf.js         PDF generation (html2canvas + jsPDF)
js/exportWord.js        Word generation (docx.js)
js/app.js               UI wiring
vendor/                 vendored libraries + fonts (fully offline)
```
