"""
main.py
Course Search Bot — Entry point.
Double-click this file or run: python main.py
"""
import os
import sys

# Ensure we run from the project root regardless of where Python is invoked from
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

# Create default documents folder if it doesn't exist
os.makedirs("course_docs", exist_ok=True)
os.makedirs("data", exist_ok=True)

from ui.app import App

if __name__ == "__main__":
    app = App()
    app.run()
