/* Custom calendar dropdown for the Date field - replaces the native
   <input type="date"> popup, which no current browser lets CSS restyle at
   all (no stylable pseudo-elements for the day grid), so it could never be
   made to match the app's own theme. This one is a small hand-built month
   grid, reusing the toolbar's existing .dropdown/.dropdown-menu open/close
   mechanics (see wireDropdowns() in app.js) for free - it just needs
   { btn: '#btn-meta-date-pick', menu: '#date-popover' } added to that
   function's `dropdowns` array. */

const CAL_MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

function calIso(y, m, d) {
  return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

function calTodayIso() {
  const d = new Date();
  return calIso(d.getFullYear(), d.getMonth(), d.getDate());
}

function wireDatePicker() {
  const popover = $('#date-popover');
  const monthLabel = $('#cal-month-label');
  const daysHost = $('#cal-days');
  let viewYear;
  let viewMonth; // 0-based

  const renderGrid = () => {
    monthLabel.textContent = `${CAL_MONTH_NAMES[viewMonth]} ${viewYear}`;
    const selected = Store.project.date || '';
    const today = calTodayIso();
    const startWeekday = new Date(viewYear, viewMonth, 1).getDay(); // 0 = Sunday
    const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
    const daysInPrevMonth = new Date(viewYear, viewMonth, 0).getDate();
    const prevM = viewMonth === 0 ? 11 : viewMonth - 1;
    const prevY = viewMonth === 0 ? viewYear - 1 : viewYear;
    const nextM = viewMonth === 11 ? 0 : viewMonth + 1;
    const nextY = viewMonth === 11 ? viewYear + 1 : viewYear;

    const cells = [];
    for (let i = 0; i < startWeekday; i += 1) {
      const day = daysInPrevMonth - startWeekday + 1 + i;
      cells.push({ day, iso: calIso(prevY, prevM, day), otherMonth: true });
    }
    for (let d = 1; d <= daysInMonth; d += 1) {
      cells.push({ day: d, iso: calIso(viewYear, viewMonth, d), otherMonth: false });
    }
    let nextDay = 1;
    while (cells.length < 42) {
      cells.push({ day: nextDay, iso: calIso(nextY, nextM, nextDay), otherMonth: true });
      nextDay += 1;
    }

    daysHost.innerHTML = cells.map((c) => {
      const classes = ['cal-day'];
      if (c.otherMonth) classes.push('other-month');
      if (c.iso === today) classes.push('today');
      if (c.iso === selected) classes.push('selected');
      return `<button type="button" class="${classes.join(' ')}" data-date="${c.iso}">${c.day}</button>`;
    }).join('');
  };

  const openAt = (isoDate) => {
    const d = isoDate ? new Date(`${isoDate}T00:00:00`) : new Date();
    viewYear = d.getFullYear();
    viewMonth = d.getMonth();
    renderGrid();
  };

  $('#btn-meta-date-pick').addEventListener('click', () => openAt(Store.project.date));

  // The text field isn't one of wireDropdowns()'s registered toggle buttons,
  // so it needs its own open/close - stopPropagation keeps the click from
  // reaching that function's document-level "close every open menu"
  // listener, which would otherwise immediately undo the classList.add below.
  $('#meta-date').addEventListener('click', (e) => {
    e.stopPropagation();
    openAt(Store.project.date);
    const isOpen = popover.classList.contains('open');
    $all('.dropdown-menu').forEach((m) => m.classList.remove('open'));
    if (!isOpen) popover.classList.add('open');
  });

  // Nav/day clicks must not bubble to the document-level "close every open
  // dropdown" listener (wireDropdowns()) - otherwise picking a month or a
  // day would close the popover before (or instead of) doing anything.
  popover.addEventListener('click', (e) => e.stopPropagation());

  $('#cal-prev').addEventListener('click', () => {
    viewMonth -= 1;
    if (viewMonth < 0) { viewMonth = 11; viewYear -= 1; }
    renderGrid();
  });
  $('#cal-next').addEventListener('click', () => {
    viewMonth += 1;
    if (viewMonth > 11) { viewMonth = 0; viewYear += 1; }
    renderGrid();
  });

  daysHost.addEventListener('click', (e) => {
    const btn = e.target.closest('.cal-day');
    if (!btn) return;
    Store.project.date = btn.dataset.date;
    Store.save();
    $('#meta-date').value = formatDDMMYYYY(Store.project.date);
    popover.classList.remove('open');
  });
}
