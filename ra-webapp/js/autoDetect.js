/* Auto-detect: scans the project Title field for keywords and automatically
   adds the matching General RA Library categories' items to the project -
   same items a user would get by checking that category in the "Add from
   General RA Library" dialog. The user can then freely edit/delete/append
   on top, exactly as with any manually-added item.

   - Toggle: the "Auto-detect Risks from Title" checkbox in the toolbar
     (persisted per-browser in localStorage, not per-project - on by default).
   - Rules: edit AUTO_DETECT_RULES below to add/adjust keyword -> category
     mappings. `keywords` are plain lowercase substrings checked against the
     lowercased title (any one match fires the rule); `category` must match
     a category's English name in js/globalRisks.js exactly. Nothing else
     needs to change when editing this array.
   - Dismissal: if the user deletes an item that auto-detect added, it is
     remembered (by Hazard+Effect+Control, same key used for de-duplication)
     as dismissed for this project, so it won't be silently re-added if the
     title still contains/regains a matching keyword. */

const AUTO_DETECT_STORAGE_KEY = 'ra_webapp_autodetect_enabled_v1';

// Always auto-added once there's any title at all - generic muster/
// housekeeping precautions apply to every job regardless of what it is,
// so it's not keyword-gated like the rest of AUTO_DETECT_RULES below.
const GENERAL_CATEGORY_NAME = 'General Site Precautions (Emergency Muster & Housekeeping)';

const AUTO_DETECT_RULES = [
  { category: 'Use of Electrical Power Hand Tools', keywords: ['electric tool', 'electrical tool', 'heat gun', 'electrical power tool', 'electric drill', 'electric grinder'] },
  { category: 'Use of Pneumatic Power Tools', keywords: ['pneumatic tool', 'pneumatic power tool', 'impact', 'air tool', 'air-powered tool'] },
  { category: 'Use of Hand Tools', keywords: ['hand tool', 'dismantle', 'install', 'secure', 'tighten', 'tight', 'bolt', 'fasten', 'fitting', 'wrench', 'spanner'] },
  { category: 'Use of Hand Tools at Height', keywords: ['hand tools at height', 'hand tool at height'] },
  { category: 'Working at Heights', keywords: ['working at height', 'work at height', 'scaffold', 'scaffolding', 'scissor lift', 'elevated platform', 'rooftop work'] },
  { category: 'Entry into Turbine Enclosure', keywords: ['turbine enclosure', 'entry to enclosure', 'entry into enclosure'] },
  { category: 'Use of Non-IS Test Equipment', keywords: ['non-is', 'non is', 'non-ex', 'non ex'] },
  { category: 'Confined Space Entry Operation', keywords: ['confined space', 'vessel entry', 'tank entry'] },
  { category: 'Digital Camera, Video Camera, Thermal Camera + Laser & Laptop Usage on Site', keywords: ['camera', 'laptop'] },
  { category: 'Scissor Lift Operations', keywords: ['scissor lift', 'mobile elevated work platform'] },
  { category: 'Water Wash for Gas-Turbine MC', keywords: ['water wash', 'turbine water wash', 'gas turbine wash'] },
  { category: 'Borescope Operation inside Turbine Enclosure', keywords: ['borescope', 'BSI'] },
  { category: 'Wash Cleaning by Using Diesel Fuel', keywords: ['diesel wash', 'diesel cleaning', 'diesel fuel wash'] },
  { category: 'Crane Operations', keywords: ['crane', 'lifting operation', 'lifting plan', 'heavy lift'] },
  { category: 'Fork Lift Truck Operations', keywords: ['forklift', 'fork lift'] },
  { category: 'Diving Operations (Splash Zone / Underwater Inspection)', keywords: ['diving', 'underwater inspection', 'splash zone'] },
  { category: 'Use of Temporary Portable Equipment', keywords: ['portable equipment', 'temporary equipment'] },
  { category: 'Chain Block Operations', keywords: ['chain block'] },
  { category: 'Confined Space Entry for Inspection of Feed Water Tank TK-9180 at M-9000 (20" manhole)', keywords: ['tk-9180', 'tk 9180'] },
  { category: 'Erection & Dismantle Scaffolding', keywords: ['install scaffold', 'install scaffolding', 'dismantle scaffold', 'dismantle scaffolding'] },
  { category: 'Excavations Confined Space Entry', keywords: ['excavation'] },
  { category: 'Garnet Blasting Operations', keywords: ['garnet blasting', 'sandblasting', 'abrasive blasting'] },
  { category: 'Hand Painting Pipework / Steel Structures & Equipment', keywords: ['hand painting', 'manual painting'] },
  { category: 'Leak-Testing Operations', keywords: ['leak test', 'leak testing', 'pressure test'] },
  { category: 'Loading and Unloading Operation', keywords: ['loading', 'unloading'] },
  { category: 'Pre-heating, Welding & Grinding Operations', keywords: ['welding', 'weld', 'grinding', 'grinder', 'pre-heat', 'preheat', 'hot work'] },
  { category: 'Pressure Safety Valve Removal & Reinstallation', keywords: ['psv', 'pressure safety valve'] },
  { category: 'Radiography Operations', keywords: ['radiography', 'x-ray', 'gamma ray'] },
  { category: 'Spray Painting Operations', keywords: ['spray paint', 'spray painting'] },
];

function isAutoDetectEnabled() {
  try {
    const v = localStorage.getItem(AUTO_DETECT_STORAGE_KEY);
    return v === null ? true : v === '1';
  } catch (e) {
    return true;
  }
}

function setAutoDetectEnabled(on) {
  try { localStorage.setItem(AUTO_DETECT_STORAGE_KEY, on ? '1' : '0'); } catch (e) { /* ignore */ }
}

function findLibraryCategoryByName(name) {
  const target = name.toLowerCase();
  return GLOBAL_RA_LIBRARY.find((c) => c.category.en.toLowerCase() === target);
}

// Library categories whose keywords match the given title text.
function matchAutoDetectCategories(titleText) {
  const t = String(titleText || '').toLowerCase();
  if (!t.trim()) return [];
  const matched = [];
  const generalCat = findLibraryCategoryByName(GENERAL_CATEGORY_NAME);
  if (generalCat) matched.push(generalCat);
  AUTO_DETECT_RULES.forEach((rule) => {
    if (rule.keywords.some((kw) => t.includes(kw))) {
      const cat = findLibraryCategoryByName(rule.category);
      if (cat) matched.push(cat);
    }
  });
  return matched;
}

// Run on title change (debounced by the caller). Adds any newly-matched RA's
// items that aren't already present and weren't previously dismissed.
function runAutoDetect(titleText) {
  if (!isAutoDetectEnabled()) return;
  const cats = matchAutoDetectCategories(titleText);
  if (!cats.length) return;

  const dismissed = new Set(Store.project.autoDismissed || []);
  const newItems = cats
    .flatMap((cat) => cat.items.map((source) => ({ ...blankItem(), ...JSON.parse(JSON.stringify(source)), autoAdded: true })))
    .filter((item) => !dismissed.has(riskItemKey(item)));
  if (!newItems.length) return;

  const added = Store.addItems(newItems);
  if (added.length) {
    renderItemsTable();
    toast(`Auto-detect added ${added.length} item(s) based on the title.`);
  }
}

function wireAutoDetectToggle() {
  const chk = $('#chk-auto-detect');
  chk.checked = isAutoDetectEnabled();
  chk.addEventListener('change', () => setAutoDetectEnabled(chk.checked));
}
