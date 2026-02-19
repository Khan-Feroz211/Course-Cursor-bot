# 🎓 Course Search Bot
### Your AI-Powered Document Search Tool
**Version 2.0  |  Windows & Mac**

---

## What Does This App Do?

Course Search Bot lets you **search through all your course PDFs instantly** using plain English — just like Google, but for your own documents.

Type a question like *"what is photosynthesis"* and the app will find every relevant paragraph across hundreds of PDFs in seconds.

---

## 📦 What's In This Folder

```
CourseSearchBot/
│
├── course_docs/         ← PUT YOUR PDFs HERE
│
├── Setup_Windows.bat    ← Run this FIRST on Windows
├── Launch_Windows.bat   ← Run this to open the app (Windows)
│
├── Setup_Mac.sh         ← Run this FIRST on Mac
├── Launch_Mac.sh        ← Run this to open the app (Mac)
│
└── data/                ← App saves its index here (do not delete)
```

---

## 🚀 Getting Started — Step by Step

### Step 1 — Install Python (one-time only)

> **Already have Python 3.11 or newer? Skip this step.**

1. Go to: **https://www.python.org/downloads/**
2. Click the big yellow **"Download Python"** button
3. Run the installer
4. ✅ **IMPORTANT:** Check the box that says **"Add Python to PATH"** before clicking Install

---

### Step 2 — Add Your PDF Files

1. Open the `CourseSearchBot` folder
2. Open the `course_docs` folder inside it
3. **Copy or move your PDF files** into `course_docs`

> 💡 You can add subfolders too — the app will scan everything inside.

---

### Step 3 — Run Setup (one-time only)

**On Windows:**
- Double-click **`Setup_Windows.bat`**
- A black window will appear and install everything automatically
- Wait until it says **"Setup complete!"**
- Press any key to close it

**On Mac:**
- Open **Terminal** (press `Cmd + Space`, type "Terminal", press Enter)
- Drag the file **`Setup_Mac.sh`** into the Terminal window
- Press **Enter**
- Wait until it says **"Setup complete!"**

---

### Step 4 — Launch the App

**On Windows:**
- Double-click **`Launch_Windows.bat`**

**On Mac:**
- Open Terminal again
- Drag **`Launch_Mac.sh`** into Terminal
- Press Enter

The **Course Search Bot** window will open! 🎉

---

## 🖥️ How to Use the App

### 1. Select Your Documents Folder
- The app automatically points to the `course_docs` folder
- If your PDFs are somewhere else, click **Browse…** and select that folder

### 2. Build the Index
- Click **"⚙ Build / Load Index"**
- The first time you do this, it may take **1–5 minutes** depending on how many PDFs you have
- You'll see a progress bar — just wait
- When done, you'll see a green message like **"✅ Index ready — 1,400 chunks loaded"**

> 💡 After the first time, it loads in seconds unless you add new PDFs.

### 3. Search!
- Click in the search box
- Type any question or topic in plain English
- Press **Enter** or click **Search**
- Results appear instantly with the matching text **highlighted in yellow**

### 4. Export Results
- Click **"Export CSV"** to save results as a spreadsheet (Excel)
- Click **"Export PDF"** to save results as a printable PDF

---

## 💡 Search Tips

| Instead of...         | Try...                              |
|-----------------------|-------------------------------------|
| `ch3`                 | `cell membrane structure`           |
| `q4 lecture`          | `how does photosynthesis work`      |
| `def`                 | `definition of osmosis`             |

The app understands **meaning**, not just exact words. So searching *"how blood carries oxygen"* will find text about hemoglobin even if those exact words aren't there.

---

## ❓ Frequently Asked Questions

**Q: How many PDFs can it handle?**
A: Hundreds. It's been tested with 300+ page documents and handles them well.

**Q: I added new PDFs — do I need to do anything?**
A: Just click **"Build / Load Index"** again. The app detects new files automatically and only re-processes what changed.

**Q: The search returns nothing. Why?**
A: Make sure you clicked "Build / Load Index" first. If you did, try rephrasing your query in simpler words.

**Q: Can it read scanned PDFs (images)?**
A: Basic scanned PDFs are supported. For best results, use PDFs with actual selectable text.

**Q: Where are my results saved?**
A: Results only save when you click "Export CSV" or "Export PDF". Nothing is saved automatically.

**Q: Is my data sent to the internet?**
A: No. Everything runs 100% on your computer. No internet connection is needed after setup.

---

## 🔧 Troubleshooting

| Problem | Solution |
|---------|----------|
| "Python not found" error | Re-install Python and check "Add to PATH" |
| App won't open after Setup | Run Setup again; check antivirus isn't blocking it |
| No results found | Rebuild index; check PDFs are in the `course_docs` folder |
| Slow first index build | Normal — AI models load once; subsequent runs are fast |
| Black screen flashes and closes | Run `Launch_Windows.bat` as Administrator |

---

## 📞 Support

If you run into any issues not covered here, please reach out with:
1. A screenshot of the error message
2. What step you were on
3. Your operating system (Windows 10/11 or Mac version)

---

*Course Search Bot v2.0 — Built with ❤️ using AI/ML technology*
*Powered by: SentenceTransformers · FAISS · pdfplumber*
