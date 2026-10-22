# Aria — AI Voice Customer Support Agent (Aura Skincare)

## Overview

A browser-based AI voice customer support agent ("Aria") for fictional D2C brand **Aura Skincare**. Evaluators can start a call, speak naturally in real time, look up live orders, resolve policy inquiries, and review structured post-call transcripts and summaries.

---

## Architecture

- **STT (Speech-to-Text):** Browser Web Speech API (`en-IN`)
- **Backend Server:** FastAPI with a single WebSocket connection (`/ws/call`)
- **LLM Reasoning & Tools:** Groq (`llama-3.3-70b-versatile`) with function calling
- **TTS (Text-to-Speech):** `edge-tts` (`en-IN-NeerjaNeural`) with browser `speechSynthesis` fallback
- **Frontend:** Plain HTML, Vanilla JS, and Vanilla CSS (no framework, no build step)

---

## Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/krishv24/Aria---Agent.git
   cd Aria---Agent
   ```

2. **Create and activate a Python virtual environment:**
   - **Windows:**
     ```powershell
     python -m venv venv
     .\venv\Scripts\Activate.ps1
     ```
   - **macOS / Linux:**
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Add your free Groq API key inside .env
   ```

5. **Run the application:**
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

---

## Environment Variables

| Variable | Description |
|---|---|
| `GROQ_API_KEY` | Free API key from [Groq Console](https://console.groq.com/keys) |

---

## How I Think

### 1. Why did you choose your particular architecture and technology stack?


### 2. What was the most difficult part of the assignment, and how did you solve it?


### 3. If you had one more week to work on this, what would you improve first and why?


### 4. Imagine this agent is handling 1,000 customer conversations a day. What do you think would need to change or improve?

