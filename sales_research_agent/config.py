CHECKLIST = [
    "company snapshot (size, industry, HQ)",
    "funding history / financials",
    "headcount trend",
    "tech stack signals",
    "recent news / announcements",
    "org changes (leadership moves, hiring surges)",
]

TOP_N_RESULTS = 3

OLLAMA_MODEL = "qwen2.5:3b"
OLLAMA_URL = "http://localhost:11434/api/generate"

FETCH_TIMEOUT = 15
EXTRACT_TIMEOUT = 200
MAX_EXTRACT_CHARS = 6000

EVIDENCE_STORE_PATH = "evidence.json"
BRIEF_MD_PATH = "brief.md"
BRIEF_JSON_PATH = "brief.json"
