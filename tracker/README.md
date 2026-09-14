# Squish Therapy — Flask Project Tracker

A browser-based Flask tracker for the Squish Therapy / FlexSense capstone project. The app uses the team's current saved task/timesheet data, a subtle blue interface with white outlined task cards, and local JSON persistence.

## Included functionality

- Full 40-task baseline plan
- Status, owner, revised-end date, and dated/categorized task notes
- Overdue / due-soon / upcoming / complete filters and sorting
- Overall progress and remaining-work / minimum-pace calculations
- CSV and GanttProject `.gan` exports
- Weekly `.xlsx` timesheet import and cumulative labor table
- Weekly PowerPoint export using the supplied `pptx_export.py`
- Slide-note selection by teammate and date range
- **Editable Bill of Materials (BOM) tab** seeded from `Parts List.xlsx`
- BOM add/edit/delete, editable project budget, cost summary, and CSV export

## Important Slides fix in this build

The previous web build loaded the shared JavaScript before the Slides page flag was defined. Because of that, the click handlers for **Load Candidate Notes** and **Export PPTX** were never registered. This build fixes the script ordering and also detects the Slides page directly from the DOM. Candidate notes now load automatically when the Slides tab opens, and the export button shows a generating state and surfaces any server error.

## Run it on Windows

1. Extract the ZIP to a normal folder.
2. Double-click `setup_and_run.bat` the first time.
3. Wait for the dependencies to install and for Flask to say it is running.
4. Open `http://127.0.0.1:5000` in your browser.
5. Keep the Command Prompt window open while using the tracker.

After the first setup, you can normally launch it with `start_tracker.bat`.

Manual setup is also supported:

```bash
pip install -r requirements.txt
python app.py
```

## Data files

The app stores persistent local data inside `data/`:

- `tracker_state.json` — task statuses, owners, revised dates, and notes
- `timesheet_state.json` — loaded timesheet history
- `tracker_meta.json` — demo date and other tracker metadata
- `bom_state.json` — editable Bill of Materials and project budget

Edits are written to these files automatically. Backing up the `data` folder backs up the tracker state.

## BOM

The initial BOM in this package was imported from the uploaded `Parts List.xlsx`. The spreadsheet's category groups are carried forward to each BOM row for easier web editing. The source workbook had an unlabeled seventh column containing values such as `0.3lbs` and dimensions; the tracker labels that field **Weight / Extra** without changing the source workbook.

The **Known numeric cost** total includes entries that can be parsed as numbers. `FREE`, blank entries, and URL-only entries are excluded from that total. The budget defaults to $800 and can be edited directly on the BOM tab.

## PowerPoint export

The web app continues to call the supplied `pptx_export.generate_pptx(...)` function, preserving the existing black-background deck format, Labor Status table, and individual accomplishment/challenge/goal sections.

## Local-network access (optional)

By default Flask listens only on your own computer. If your team later wants to use the same running copy from other devices on the same trusted network, the server can be configured to listen on the LAN. Do not expose Flask's debug server directly to the public internet.

## BOM improvements in this build
- Separate editable **Price** and **Part Link** fields.
- Existing hyperlinks from the supplied Parts List workbook are preloaded where available.
- A large synchronized horizontal scrollbar is provided above the BOM table.
- BOM rows can be sorted by original order, category, vendor, part, description/part number, or price.
- The Add BOM Item helper text and placeholders are intentionally short.

## CAD Model tab

The CAD Model tab adds a small version-controlled STEP library to the tracker.

- Upload `.step` or `.stp` files up to 100 MB.
- Create multiple named designs (for example, `FlexSense Assembly` and `Handle Subassembly`).
- Upload a new version to an existing design without overwriting any previous file.
- Each revision stores a version number, label, upload date, one-line change summary, and detailed notes.
- Click any previous version in Version History to reopen that exact saved model.
- Download the original STEP file for any version.
- The 3D viewer supports mouse rotation, wheel zoom, right-drag panning, Fit Model, and Wireframe/Solid view.

CAD metadata is stored in `data/cad_state.json`. Original CAD files are stored under `data/cad_models/<design-id>/`.

The interactive STEP viewer uses Three.js and `occt-import-js` (OpenCascade WebAssembly) from jsDelivr when the CAD tab is opened, so the browser needs internet access to load the viewer libraries. The uploaded STEP files themselves remain on your Flask tracker computer/server; the browser fetches the selected file from your own Flask app for display.

### CAD workflow example

1. Open **CAD Model**.
2. Choose **+ New design**, name it `FlexSense Assembly`, add a short change summary, and upload your STEP file.
3. Later, choose `FlexSense Assembly` from the Design dropdown and upload the next STEP file. It becomes Version 2 automatically while Version 1 stays available in the history.
4. Open any version and edit its **What changed?** and **Detailed notes** fields for documentation.
