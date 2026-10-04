# 📱 Phone copy: setup (once, about 15 minutes)

Do Part 1 + 2 with **fake** data first. Part 3 switches to your real data.

---

## Part 1: make the free website (PythonAnywhere)

1. Go to **pythonanywhere.com** → **Pricing & signup** → **Create a Beginner account** (free).
   Your username becomes your address: `https://USERNAME.pythonanywhere.com`
2. Click **Web** (top right) → **Add a new web app** → **Next**
3. Pick **Flask** → pick the newest **Python 3** → keep the path it offers
   (`/home/USERNAME/mysite/flask_app.py`) → **Next**
4. Click **Files** (top right) → open the **mysite** folder → click **flask_app.py**
5. Delete everything in it. On your PC open `cloud\flask_app.py` (in the code folder) with Notepad,
   copy all of it, paste it in → **Save**
6. Click **Web** again → the big green **Reload** button
7. Open `https://USERNAME.pythonanywhere.com` → it should say **"Waiting for your PC to send a copy"** ✅

⏰ Free sites sleep after 3 months: log in and press **"Run until 3 months from today"** on the Web tab.

---

## Part 2: try it with FAKE data 🧪

PowerShell, in the code folder:

```
Copy-Item tests\data\statement_2024_*.pdf statements\
C:\ftvenv\Scripts\python.exe run.py test
C:\ftvenv\Scripts\python.exe run.py phone https://USERNAME.pythonanywhere.com test
C:\ftvenv\Scripts\python.exe run.py pin 1234 test
```

(`run.py test`: just press Enter at the questions.)

On your phone:
1. Open `https://USERNAME.pythonanywhere.com` → type **1234**
2. Add a spend → watch the big number drop → tap **📤 Send to PC**
3. Back on the PC: `C:\ftvenv\Scripts\python.exe run.py test` → it lists your phone spend → **Enter**

---

## Part 3: switch to REAL data 💷

```
C:\ftvenv\Scripts\python.exe run.py phone https://USERNAME.pythonanywhere.com
C:\ftvenv\Scripts\python.exe run.py pin 4821
```

(use your own PIN, 4 to 8 numbers). Done: your real page replaces the fake one.

📲 On the phone: browser menu → **Add to Home Screen**.

---

## Every day

- 🖥️ `run.py` or `start.bat` sends a fresh copy up by itself (and after every spend you add on the PC)
- 📱 Phone spends → **Send to PC** → next time the PC starts it asks you (Enter = do them all)
- 🏠 Home page on the PC shows a **From your phone** box instead: untick any you don't want → **Do the ticked ones**
