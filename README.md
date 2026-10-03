# Polar Expedition Manager

A basic app for managing polar expeditions and storing expedition files. You can upload files, set their importance, and create compressed or password-encrypted copies.

## Install and run on Windows

Use **PowerShell** for the commands below. Run each command one at a time.

### 1. Install these tools

- [Git](https://git-scm.com/downloads/win) — downloads the project.
- [Python 3.12](https://www.python.org/downloads/windows/) — runs the backend. Enable **Add Python to PATH** during installation.
- [Node.js 22 (22.12 or newer)](https://nodejs.org/en/download) — runs the frontend. Keep npm selected during installation.

Close and reopen PowerShell after installing them. Check that they work:

```powershell
git --version
py -3.12 --version
node --version
npm.cmd --version
```

Each command should show a version number. No separate database installation is needed.

### 2. Download the project

```powershell
New-Item -ItemType Directory -Force C:\dev
cd C:\dev
git clone --branch pmce-backend https://github.com/adithmv/SIH26062.git
```

The project will be in `C:\dev\SIH26062`. If you already have it there, skip this step.

### 3. Set up and start the backend

In PowerShell, run:

```powershell
cd C:\dev\SIH26062\backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Wait until you see **Application startup complete**. Leave this window open.

### 4. Set up and start the frontend

Open a **second PowerShell window** and run:

```powershell
cd C:\dev\SIH26062\frontend
npm.cmd ci
npm.cmd run dev -- --port 5173 --strictPort
```

Leave this window open too.

### 5. Open the app

Open **http://127.0.0.1:5173/** in your browser.

Choose **Data Management** to upload your own files. A fresh installation has no sample data.

## Start it again later

You only need these commands after the first setup.

**First PowerShell window:**

```powershell
cd C:\dev\SIH26062\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Second PowerShell window:**

```powershell
cd C:\dev\SIH26062\frontend
npm.cmd run dev -- --port 5173 --strictPort
```

Open **http://127.0.0.1:5173/**. To stop the app, press **Ctrl+C** in both windows.

## Where your data is stored

- Database: `backend/operations.sqlite3`
- Uploaded files and prepared copies: `backend/data/files/`

Files stay on the backend computer; file transfer to base is not connected yet. Encryption protects the prepared copy. The original stays unencrypted. Keep this prototype on your own computer; user sign-in and permissions are not implemented.

## If something does not work

- **Command not found:** install the tool from step 1, then reopen PowerShell.
- **Port 8000 or 5173 already in use:** an app may already be running. Stop its terminal with Ctrl+C before starting another instance.
- **App cannot reach the backend:** check that the first PowerShell window is still running. Open http://127.0.0.1:8000/api/health; it should show `"status":"ok"`.

More details: [File management](docs/DATA_MANAGEMENT.md) · [Backend and PMCE](backend/README.md).
