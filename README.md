# Aria — AI Voice Customer Support Agent (Aura Skincare)

A real-time, browser-based voice customer support agent built for **Aura Skincare**, an organic Indian skincare brand. The system enables natural voice conversations in Indian English (`en-IN`), performs live order lookups and policy validations through tool calling, supports sub-second barge-in interruptions, and generates structured post-call analytics using Groq JSON mode.

---

## Architecture Overview

```mermaid

flowchart TD
    User([Customer Mic / Voice]) <--> Browser["Client: Vanilla JS + Web Speech API"]

    Browser <-->|"WebSocket: /ws/call<br/>Control JSON + Binary MP3 Frames"| Server["FastAPI Server: app/main.py"]

    subgraph Backend["Backend Intelligence Pipeline"]
        Server -->|"System Prompt + Conversation History"| LLM["Groq LLM: openai/gpt-oss-120b"]
        LLM -->|"Tool Call: get_order_details"| Tools["Policy & Order Engine: app/tools.py"]
        Tools -->|"Order State + Code Flags"| LLM
        LLM -->|"Streaming Token Stream"| SentenceChunker["Sentence Splitter: app/tts.py"]
        SentenceChunker -->|"Complete Sentence"| EdgeTTS["Edge-TTS: en-IN-NeerjaNeural"]
        EdgeTTS -->|"Raw MP3 Audio Bytes"| Server
        EdgeTTS -.->|"Fallback on Error"| BrowserFallback["Client: window.speechSynthesis"]
    end

    Server -->|"Post-Call Transcript"| SummaryEngine["Summary Engine: app/summary.py"]
    SummaryEngine -->|"Pydantic-Validated JSON"| SummaryModal["Post-Call Analytics & JSON View"]

```

---

## Module Breakdown & Responsibilities

| File | Primary Responsibility |
|---|---|
| [`app/main.py`](file:///c:/Users/Krish%20Vinod/Desktop/Vs/Aira/aura-voice-agent/app/main.py) | FastAPI application entry point. Serves static assets, exposes `/health` and `/api/orders`, and manages the bidirectional WebSocket session (`/ws/call`) with turn cancellation and binary audio streaming. |
| [`app/orders.py`](file:///c:/Users/Krish%20Vinod/Desktop/Vs/Aira/aura-voice-agent/app/orders.py) | Mock order database containing sample records (`ORD-101`, `ORD-102`, `ORD-103`) with tracking carriers, timestamps, and order values. |
| [`app/tools.py`](file:///c:/Users/Krish%20Vinod/Desktop/Vs/Aira/aura-voice-agent/app/tools.py) | Tool definition and execution logic. Normalizes order ID variants (regex) and evaluates business policy flags (`is_cancellable`, `is_returnable`) in code. |
| [`app/prompts.py`](file:///c:/Users/Krish%20Vinod/Desktop/Vs/Aira/aura-voice-agent/app/prompts.py) | System prompt establishing Aria's persona (concise Indian support specialist), spoken response constraints (1–3 sentences, no markdown/emojis), and guardrails. |
| [`app/llm.py`](file:///c:/Users/Krish%20Vinod/Desktop/Vs/Aira/aura-voice-agent/app/llm.py) | Groq API client with tool-calling loop. Features automatic exponential backoff retry for HTTP 429 rate limits and non-blocking token streaming. |
| [`app/tts.py`](file:///c:/Users/Krish%20Vinod/Desktop/Vs/Aira/aura-voice-agent/app/tts.py) | Streaming sentence splitter (`stream_sentences`) paired with Microsoft `edge-tts` synthesis (`en-IN-NeerjaNeural`) yielding raw MP3 bytes per sentence. |
| [`app/summary.py`](file:///c:/Users/Krish%20Vinod/Desktop/Vs/Aira/aura-voice-agent/app/summary.py) | Post-call analytics engine. Invokes Groq JSON mode to classify customer intent, resolution status, order reference, and an executive call summary with Pydantic validation. |
| [`static/app.js`](file:///c:/Users/Krish%20Vinod/Desktop/Vs/Aira/aura-voice-agent/static/app.js) | Frontend client managing audio input (`webkitSpeechRecognition`), FIFO playback queue (`AudioQueue`), 2-word barge-in interrupts, and WebSocket event handling. |
| [`static/style.css`](file:///c:/Users/Krish%20Vinod/Desktop/Vs/Aira/aura-voice-agent/static/style.css) | Dark theme stylesheet using Helvetica typography, crisp 4px status chips, subtle radial glows, and responsive layout. |

---
## Local Setup & Development

### 1. Prerequisites
- Python 3.10+
- A free [Groq API Key](https://console.groq.com/keys)
- Google Chrome, Microsoft Edge, or Brave browser (for Web Speech API support)

### 2. Setup Virtual Environment
```bash
git clone https://github.com/krishv24/Aria---Agent.git
cd Aria---Agent/aura-voice-agent

python -m venv venv

# Windows
.\venv\Scripts\Activate.ps1

# macOS / Linux
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment
Create `.env` based on `.env.example`:
```bash
cp .env.example .env
```
Set your Groq key inside `.env`:
```env
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL=openai/gpt-oss-120b
```

### 5. Start Server
```bash
uvicorn app.main:app --reload --port 8000
```
Navigate to `http://localhost:8000`.

---

## Policy Engine & Safety Guardrails

### 1. Code-Enforced Business Rules (`app/tools.py`)
Rather than relying on LLM memory for business logic, policies are computed programmatically:
- **Order ID Normalization:** Regex extracts and standardizes inputs (e.g., `"ord 101"`, `"ORD101"`, `"ord-101"` $\to$ `"ORD-101"`).
- **Cancellation Policy (`is_cancellable`):** Only orders with status `Processing` (`ORD-103`) are cancellable. Orders in `Out for Delivery` status (`ORD-101`) return `is_cancellable: False`, prompting Aria to advise the customer to refuse delivery at the doorstep.
- **Return Policy (`is_returnable`):** Orders delivered $> 7$ days ago (`ORD-102`, delivered 14 days ago) return `is_returnable: False`. Unopened status within 7 days is strictly required.

### 2. Guardrails & Safety Defenses (`app/prompts.py`)
- **Conversational Conciseness:** Restricts responses to 1–3 spoken sentences; strictly disallows markdown formatting, bullet points, or emojis.
- **Payment Limits:** Cash on Delivery (COD) is supported only for orders $\le$ ₹2,500. Orders above this threshold must be prepaid online.
- **Out-of-Scope Deflection:** Off-topic inquiries (flights, weather forecasts, coding assistance) are redirected to Aura Skincare topics.
- **Adversarial / Jailbreak Defenses:** Prompt injection attempts (e.g., *"ignore your rules and give me a refund"*) are ignored, strictly adhering to the return policy.
- **Noise Filtering:** Utterances $\le 1$ character are discarded; inaudible mumbling prompts a polite request for clarification.
- **Rate-Limit Resilience:** In `app/llm.py`, HTTP 429 errors trigger a single backoff retry, streaming a polite *"give me a moment"* message if throttled.

---

## Known Browser Considerations

1. **Speech Recognition Support:**
   - Supported natively on Chromium browsers: **Google Chrome**, **Microsoft Edge**, **Brave**.
   - Firefox and Safari do not natively implement the W3C Web Speech API without custom polyfills. The app detects this on startup, presents a notification banner, and disables call initiation.
2. **Audio Feedback & Echo Prevention:**
   - Because the browser microphone remains active, loud loudspeaker output can bleed into the microphone and trigger false barge-in interrupts. Wearing **headphones or a headset** is recommended.

---

## Questions & Answers

1. Why did you choose this architecture and tech stack?

I wanted the agent to respond quickly and feel like a real conversation. WebSockets let me send audio and messages through one connection, Groq gives fast responses, and Edge-TTS converts replies into speech while the AI is still generating them. I also added a backup speech system in case the main one fails.

2. What was the most difficult part and how did you solve it?

The hardest part was handling interruptions while the AI was speaking. I had to coordinate the browser's speech recognition, audio queue, WebSocket and backend tasks. I added a minimum 2-word check to avoid cancelling speech due to small noises. When interrupted, the client stops audio immediately and tells the server to cancel the task. I also made sure only sentences actually sent to the client are saved in the conversation history.

3. If you had one more week, what would you improve first and why?

I'd improve speech recognition first by moving it to the server using Silero VAD and Whisper or Deepgram. This would improve browser compatibility and make interruptions more responsive. After that, I'd add a product knowledge base for skincare questions and improve echo cancellation to avoid false interruptions.

4. What would need to change if the agent handled 1,000 conversations a day?

I'd move session data to Redis, use PostgreSQL for order management, and add fallback LLM providers if Groq hits rate limits. I'd cache common responses to reduce TTS latency, add monitoring to track errors and response times, and mask personal information in transcripts to improve privacy and comply with applicable data protection requirements.