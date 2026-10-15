# 🌐 v3 setup: Where's My Money? as one website

Two parts:

- **Part 1 (now): try v3 on your PC** at `127.0.0.1:5001`, next to v2. Your v2 and its data are not touched.
- **Part 2 (move-in day, later): put v3 on PythonAnywhere.** Only when you're happy with Part 1.

---

## Part 1: try v3 on your PC (about 5 minutes)

### 1. Get the v3 code (a new folder, not your v2 folder)

1. Open **https://github.com/DF-AI-Lab/financial-tracker/archive/refs/heads/v3.zip** (it downloads)
2. Extract it inside **Financial Tracker Project**, next to your v2 code folder:

```
📁 Financial Tracker Project
   📁 stoic-archimedes...        (v2, keep using it as normal)
   📁 financial-tracker-v3       (the new one)
   📁 statements
   📄 tracker.db                 (your real data, v2)
```

### 2. Start it

Double-click **`v3.bat`** in **financial-tracker-v3**.

- A black window opens and **stays open** (that's v3 running).
- The first time it makes a **copy** of your data in a new folder **v3data**. Your real `tracker.db` is never changed.
- Your browser opens **http://127.0.0.1:5001**.

### 3. Put your email in (first time only)

1. Open the folder **Financial Tracker Project → v3data** → open **`v3_settings.json`** with Notepad
2. Put your email between the quotes on the `"email"` line, like this:

```
  "email": "you@example.com",
```

3. **Save**, close the black window, double-click **`v3.bat`** again

### 4. Sign in

1. Type your email → **Send code**
2. On the PC the code shows **in the black window** (no email needed for testing)
3. Type the code → you're in ✅

### 5. Try things

Drop a PDF, change your pay, add a spend, ⋯ on a bill, ⚙ Settings → Fix an item, Download backup.

Anything odd: screenshot it and send it to Claude.

---

## Part 2: move-in day on PythonAnywhere (later, Claude walks you through it)

Draft of the steps, so nothing is a surprise:

1. **Gmail app password** (so the site can email you the sign-in code):
   Google Account → **Security** → turn on **2-Step Verification** → search **App passwords** → make one called
   *Wheres My Money* → copy the 16 letters.
2. **PythonAnywhere → Consoles → Bash**, paste:

```
git clone -b v3 https://github.com/DF-AI-Lab/financial-tracker.git ~/whereismymoney
python3.13 -m venv ~/wmm-venv && ~/wmm-venv/bin/pip install flask pdfplumber webauthn
mkdir -p ~/wmm-data
```

3. **Files** tab → open **wmm-data** → **Upload a file** → your `tracker.db` (after the privacy check).
4. **Web** tab → your site → **Virtualenv**: `/home/USERNAME/wmm-venv` → **WSGI configuration file**: replace everything with:

```
import sys
sys.path.insert(0, "/home/USERNAME/whereismymoney")
from v3app import make_app
application = make_app("/home/USERNAME/wmm-data")
```

5. **Reload**. Then in **wmm-data** edit `v3_settings.json`: your `email`, `smtp_user` (your Gmail),
   `smtp_password` (the 16 letters), `"update": "git"`, `"wsgi_file"` (the WSGI file path shown on the Web tab).
   **Reload** again.
6. Open `https://USERNAME.pythonanywhere.com` on your phone and PC → sign in with the emailed code →
   ⚙ Settings → **New backup codes** → keep them in your phone's notes.
7. ⏰ Once a month: PythonAnywhere → **Web** → **Run until 1 month from today**.

🛟 v2 stays on your PC as a backup the whole time.

## 👆 Fingerprint (v3.61)
Unlock with your fingerprint instead of the passcode. The server needs one extra part, once.

On PythonAnywhere, open a **Bash console** and paste:
```
~/wmm-venv/bin/pip install webauthn
```
Then **Web** tab → **Reload**. On your phone: ⚙ Settings → **👆 Fingerprint** → **Turn on fingerprint**.

On the PC test copy (optional, Windows Hello):
```
C:\ftvenv\Scripts\python.exe -m pip install webauthn
```
Fingerprint only works at `http://localhost:5001` (not `127.0.0.1`).
