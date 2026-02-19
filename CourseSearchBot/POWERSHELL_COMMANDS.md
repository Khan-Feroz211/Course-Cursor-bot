# 💻 PowerShell Commands — Complete Guide
# Course Search Bot — Everything you need to copy-paste

=======================================================
  SECTION 1 — FIX THE WINDOWS TRUST WARNING
=======================================================

When Windows shows "Windows protected your PC" blue screen:
This is called "SmartScreen" — it appears on ANY new .bat or .exe
file that hasn't been verified yet. It does NOT mean it's a virus.

HOW TO BYPASS IT (safe — this is YOUR code):

Option A — Right-click method (easiest):
  1. Right-click the file (Setup_Windows.bat or Launch_Windows.bat)
  2. Click "Properties"
  3. At the bottom, check the box "Unblock"
  4. Click Apply → OK
  Done. Run it normally now.

Option B — PowerShell unblock (run this once):

# Unblock all files in the folder at once:
Get-ChildItem -Path "C:\Path\To\CourseSearchBot" -Recurse | Unblock-File

# Replace C:\Path\To\CourseSearchBot with your actual folder path
# Example:
Get-ChildItem -Path "C:\Users\YourName\Desktop\CourseSearchBot" -Recurse | Unblock-File


=======================================================
  SECTION 2 — PUSH CODE TO GITHUB
=======================================================

Step 1 — Open PowerShell and go to your folder:
(Replace the path with wherever you saved the CourseSearchBot folder)

cd "C:\Users\YourName\Desktop\CourseSearchBot"

Step 2 — Set up Git (one-time, if you haven't already):

git config --global user.name "Khan-Feroz211"
git config --global user.email "your@email.com"

Step 3 — Initialize and push:

# Initialize git in the folder
git init

# Connect to your GitHub repo
git remote add origin https://github.com/Khan-Feroz211/Course-Cursor-bot.git

# Add all files
git add .

# First commit
git commit -m "Initial release - Course Search Bot v2.0"

# Push to GitHub
git branch -M main
git push -u origin main

Step 4 — Every time you make changes and want to update GitHub:

git add .
git commit -m "Describe what you changed here"
git push


=======================================================
  SECTION 3 — INSTALL & RUN THE APP (Desktop Mode)
=======================================================

# Go to your project folder
cd "C:\Users\YourName\Desktop\CourseSearchBot"

# Install Python dependencies (first time only)
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Run the desktop app
python main.py

# Next time (venv already exists, just activate and run):
.\venv\Scripts\Activate.ps1
python main.py


=======================================================
  SECTION 4 — DOCKER (ALWAYS-ALIVE SERVER MODE)
=======================================================

Prerequisites: Install Docker Desktop from https://www.docker.com/products/docker-desktop/
After installing, make sure Docker Desktop is running (whale icon in taskbar)

# Go to your folder
cd "C:\Users\YourName\Desktop\CourseSearchBot"

# BUILD and START the container (first time — takes 5-10 min to download)
docker-compose up -d

# After that, open your browser and go to:
# http://localhost:8000

# The app will:
#   - Stay alive even if you close PowerShell
#   - Restart automatically if it crashes
#   - Restart automatically when your PC reboots (restart: always)

# See live logs (Ctrl+C to stop watching, app keeps running)
docker-compose logs -f

# Check if it's running
docker-compose ps

# Stop the app
docker-compose down

# Restart after you've added new PDFs
docker-compose restart

# Rebuild after you've changed the code
docker-compose up -d --build


=======================================================
  SECTION 5 — BUILD .EXE (Real Double-Click Executable)
=======================================================

# Activate your venv first
.\venv\Scripts\Activate.ps1

# Install PyInstaller
pip install pyinstaller

# Build the exe (takes 3-5 minutes)
pyinstaller CourseSearchBot.spec

# Your .exe will be here:
# dist\CourseSearchBot\CourseSearchBot.exe

# Zip it to send to your client
Compress-Archive -Path "dist\CourseSearchBot" -DestinationPath "CourseSearchBot_v2.0_Windows.zip"


=======================================================
  SECTION 6 — USEFUL DAILY COMMANDS
=======================================================

# Check Python version (should be 3.11+)
python --version

# Check all installed packages
pip list

# Run tests
.\venv\Scripts\Activate.ps1
pip install pytest
pytest tests/ -v

# See project folder structure
tree /F

# Clear old index data (forces full re-index next launch)
Remove-Item -Recurse -Force data\
New-Item -ItemType Directory -Name data

# Check Docker containers running
docker ps

# Check Docker container health
docker inspect course_search_bot --format "{{.State.Health.Status}}"
