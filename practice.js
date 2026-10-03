/* Optional evening notes. No network requests; notes stay in this browser. */
(() => {
  "use strict";
  const prefix = "daily-discipline.evening.v1.";
  const entries = Array.from(document.querySelectorAll("[data-note-date]"));
  const panels = [];

  for (const entry of entries) {
    const date = entry.dataset.noteDate;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) continue;
    const controls = entry.querySelector(".private-note");
    const input = entry.querySelector("textarea");
    const status = entry.querySelector(".note-status");
    const save = entry.querySelector("[data-note-save]");
    const clear = entry.querySelector("[data-note-clear]");
    if (!controls || !input || !status || !save || !clear) continue;
    controls.hidden = false;
    const panel = { date, input, status, saved: "" };
    panels.push(panel);
    try {
      const stored = localStorage.getItem(prefix + date);
      if (stored !== null) {
        const record = JSON.parse(stored);
        if (record?.version === 1 && typeof record.note === "string") {
          panel.saved = record.note.slice(0, 4000);
          input.value = panel.saved;
          status.textContent = "Saved on this device.";
        } else {
          status.textContent = "This saved note could not be read. It has been left untouched.";
        }
      }
    } catch {
      status.textContent = "Browser storage is unavailable or this saved note could not be read. You can still reflect here.";
    }

    input.addEventListener("input", () => {
      status.textContent = input.value === panel.saved ? "No unsaved changes." : "Unsaved — choose Save on this device to keep this note.";
    });

    function synchronize(note) {
      for (const other of panels) {
        if (other.date !== date) continue;
        // Preserve an unsaved draft in another view of the same date.
        if (other !== panel && other.input.value !== other.saved) {
          other.status.textContent = "Another view saved this date. Your unsaved draft remains here.";
          continue;
        }
        other.saved = note;
        other.input.value = note;
        other.status.textContent = note ? "Saved on this device." : "No saved note for this day.";
      }
    }

    save.addEventListener("click", () => {
      const note = input.value.slice(0, 4000);
      try {
        if (note.trim()) {
          localStorage.setItem(prefix + date, JSON.stringify({ version: 1, note }));
        } else {
          localStorage.removeItem(prefix + date);
        }
        synchronize(note.trim() ? note : "");
      } catch {
        status.textContent = "Could not save in this browser. Your words remain here; copy them before leaving.";
      }
    });

    clear.addEventListener("click", () => {
      try {
        localStorage.removeItem(prefix + date);
        synchronize("");
      } catch {
        status.textContent = "Could not clear the saved note. It has been left untouched.";
      }
    });
  }
})();
