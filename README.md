# Course Search Bot

AI-powered semantic search for university course PDFs.

## How To Run

### Desktop App (Windows)
1. Open the CourseSearchBot folder
2. Run Setup_Windows.bat (first time only)
3. Run Launch_Windows.bat every time after

### Server Mode (Docker)
```powershell
cd CourseSearchBot
docker-compose up -d
```  
Then open: http://localhost:8000

## Add Your PDFs
Put PDF files inside CourseSearchBot/course_docs/ then click Build Index.

## Requirements
- Python 3.11 or newer
- Docker Desktop (only for server mode)

*Version 2.0*
