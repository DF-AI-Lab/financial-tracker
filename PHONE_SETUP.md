# 📱 Phone copy: setup (once, about 15 minutes)

---

## Part 1: make the free website (PythonAnywhere)

1. Go to **pythonanywhere.com** → **Pricing & signup** → **Create a Beginner account** (free).
   Your username becomes your address: `https://USERNAME.pythonanywhere.com`
2. Click **Web** (top right) → **Add a new web app** → **Next**
3. Click **Flask** → click **Python 3.13** → keep the path it offers → **Next**
4. Next to **Source code** click **Go to directory** → click **flask_app.py**
5. **Ctrl+A**, **Delete**. On your PC open `cloud\flask_app.py` (in the code folder) with Notepad,
   **Ctrl+A**, **Ctrl+C**, back in the browser **Ctrl+V** → **Save**
6. Click **Web** (top right) → the big green **Reload** button
7. Open `https://USERNAME.pythonanywhere.com` → it says **"Waiting for your PC to send a copy"** ✅

⏰ Free sites sleep after 3 months: log in and press **"Run until 3 months from today"** on the Web tab.

🔁 When a new version changes `cloud\flask_app.py`, do steps 4 to 6 again.

---

## Part 2: connect your PC

Your folders must look like this (the `statements` folder can be empty):

```
📁 Financial Tracker Project
   📁 financial-tracker-main     (the code)
   📁 statements
   📄 tracker.db                 (your real data)
```

In the code folder: right-click on empty space → **Open in Terminal**, then paste one at a time:

```
C:\ftvenv\Scripts\python.exe run.py phone https://USERNAME.pythonanywhere.com
C:\ftvenv\Scripts\python.exe run.py pin 4821
```

(use your own PIN, 4 to 8 numbers). Both say **"Sent a fresh copy to your phone."**

Then double-click **`setup.bat`** once: the PC part now starts by itself, hidden, when Windows starts.

---

## Part 3: your phone

1. Open `https://USERNAME.pythonanywhere.com` → type your PIN
2. Browser menu → **Add to Home Screen** 📲

---

## Every day

- 📱 Change spends, pay, left-over, bills or answer questions on the website: they count straight away.
  ⏳ shows until your PC has them (it checks every 5 minutes while it is on).
- 📥 Download your HSBC statement PDF: your PC moves it out of **Downloads** and reads it in by itself.
- 🖥️ The PC page (`127.0.0.1:5000`) is still there for moving cards and renaming.
