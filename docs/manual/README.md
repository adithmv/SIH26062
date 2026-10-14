# Visual quick guide

Final PDF: `../../output/pdf/Polar-Expedition-Manager-Quick-Guide.pdf`.

`build_manual.py` rebuilds the eight-page guide using ReportLab and Pillow. The PNG files are unchanged screenshots; arrows, circles and labels are PDF vectors. Install `reportlab pillow` in a documentation environment, then run `python docs/manual/build_manual.py` from the repository root.

`capture.cjs` records screenshots against a disposable development server at port 5180, proxying a disposable API at port 8010. It uploads a manual-only text file and creates an encrypted copy in that isolated database. Never point it at a live deployment. Base sign-in and inventory screens use a clearly labeled illustrative browser session. The inventory example is not saved. No live records, credentials or personal data appear in the guide.

To recapture: create a fresh disposable database, run migrations with DATABASE_URL pointing to it, set FILE_STORAGE_ROOT to a disposable folder, start the API on 8010 and Vite on 5180 with API_PROXY_TARGET=http://127.0.0.1:8010, then run `node docs/manual/capture.cjs`. Requires frontend dependencies and Playwright Chromium. Stop both disposable servers afterward. Screens are examples, not evidence of a production deployment.

All eight PDF pages were rendered and visually checked. The guide distinguishes health checks, authenticated delivery APIs and the unimplemented remote file browser.
