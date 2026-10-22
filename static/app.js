/**
 * Frontend logic for Aria - Aura Skincare Voice Agent
 * Handles call states, transcript rendering, and mock order fetching.
 */

// 1. Single source of truth for the agent call state
// Allowed values: 'idle' | 'listening' | 'thinking' | 'speaking'
let currentState = "idle";

// DOM Element references
const stateBadge = document.getElementById("stateBadge");
const stateLabel = document.getElementById("stateLabel");
const startCallBtn = document.getElementById("startCallBtn");
const endCallBtn = document.getElementById("endCallBtn");
const transcriptBox = document.getElementById("transcriptBox");
const transcriptPlaceholder = document.getElementById("transcriptPlaceholder");
const clearTranscriptBtn = document.getElementById("clearTranscriptBtn");
const ordersContainer = document.getElementById("ordersContainer");
const speechNotice = document.getElementById("speechNotice");
const interimMsg = document.getElementById("interimMsg");
const interimText = document.getElementById("interimText");

// Human-readable labels for each state
const STATE_LABELS = {
  idle: "Idle",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
};

/**
 * Single function to update the agent's state across the UI.
 * Avoids scattered booleans and keeps badge and button states synchronized.
 * @param {'idle' | 'listening' | 'thinking' | 'speaking'} newState
 */
function setState(newState) {
  if (!STATE_LABELS[newState]) {
    console.error(`Invalid state: ${newState}`);
    return;
  }

  currentState = newState;

  // 1. Update state badge classes and label text
  stateBadge.className = `state-badge state-${currentState}`;
  stateLabel.textContent = STATE_LABELS[currentState];

  // 2. Synchronize Start / End Call button enabled states
  const isCallActiveState = currentState !== "idle";
  startCallBtn.disabled = isCallActiveState;
  endCallBtn.disabled = !isCallActiveState;

  console.log(`[State Change] -> ${currentState}`);
}

/**
 * Append a customer or agent speech bubble to the live transcript.
 * @param {'customer' | 'agent'} sender
 * @param {string} text
 */
function addTranscriptMessage(sender, text) {
  if (transcriptPlaceholder) {
    transcriptPlaceholder.style.display = "none";
  }

  const msgDiv = document.createElement("div");
  msgDiv.className = `chat-msg ${sender}`;

  const senderTag = document.createElement("span");
  senderTag.className = "msg-sender";
  senderTag.textContent = sender === "customer" ? "You (Customer)" : "Aria (Support)";

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";
  bubble.textContent = text;

  msgDiv.appendChild(senderTag);
  msgDiv.appendChild(bubble);

  // Keep the interim message element always at the bottom of the transcript
  if (interimMsg && interimMsg.parentNode === transcriptBox) {
    transcriptBox.insertBefore(msgDiv, interimMsg);
  } else {
    transcriptBox.appendChild(msgDiv);
  }

  // Auto-scroll to the bottom of the transcript
  transcriptBox.scrollTop = transcriptBox.scrollHeight;
}

// ============================================================================
// Web Speech API: SpeechRecognition (STT)
// ============================================================================

// Browser compatibility fallback (Chrome, Edge use webkitSpeechRecognition)
const SpeechRecognition =
  window.SpeechRecognition || window.webkitSpeechRecognition;

let recognition = null;
let isCallActive = false; // Tracks if voice call is actively ongoing
let hasFiredSpeechStart = false; // Flags whether onSpeechStart has fired for current utterance

/**
 * Display a notice banner for browser compatibility or mic permission errors.
 * @param {string} message
 * @param {'warning' | 'danger'} type
 */
function showSpeechNotice(message, type = "warning") {
  if (!speechNotice) return;
  speechNotice.className = `speech-notice ${type}`;
  speechNotice.textContent = message;
  speechNotice.style.display = "block";
}

/**
 * Clear any active notice banner.
 */
function clearSpeechNotice() {
  if (!speechNotice) return;
  speechNotice.style.display = "none";
  speechNotice.textContent = "";
}

/**
 * Check if the browser supports the Web Speech API.
 * If unsupported, alerts the user and disables the Start Call button.
 */
function checkBrowserSpeechSupport() {
  if (!SpeechRecognition) {
    showSpeechNotice(
      "Speech recognition is not supported in this browser. Please use Google Chrome or Microsoft Edge.",
      "warning"
    );
    startCallBtn.disabled = true;
    startCallBtn.title = "Please use Chrome or Edge for voice recognition";
    return false;
  }
  return true;
}

/**
 * Show interim (in-progress) speech live on screen while the user speaks.
 * @param {string} text
 */
function showInterimText(text) {
  if (transcriptPlaceholder) {
    transcriptPlaceholder.style.display = "none";
  }
  if (!interimMsg || !interimText) return;

  interimText.textContent = text;
  interimMsg.style.display = "flex";

  // Keep interim bubble at the very bottom
  transcriptBox.appendChild(interimMsg);
  transcriptBox.scrollTop = transcriptBox.scrollHeight;
}

/**
 * Hide the interim speech bubble once speech finalizes or ends.
 */
function hideInterimText() {
  if (!interimMsg || !interimText) return;
  interimMsg.style.display = "none";
  interimText.textContent = "";
}

/**
 * Barge-in hook: fires on the FIRST interim chunk when the user begins speaking.
 * Immediately halts any active agent audio playback and purges remaining queued sentences.
 */
function onSpeechStart() {
  console.log("[Speech Start] User started speaking (barge-in hook fired)");
  audioQueue.stop();
}

/**
 * Handler for finalized user speech.
 * Displays the customer message in the transcript.
 * (Will send to backend WebSocket in the next stage).
 * @param {string} text
 */
function onUserUtterance(text) {
  console.log("[User Utterance]", text);
  addTranscriptMessage("customer", text);
  // Backend WebSocket connection will be wired here in the next stage
}

/**
 * Normalizes domain-specific terms and names that browser STT frequently misrecognizes.
 * - In Indian English (en-IN), Web Speech API transcribes "Aria" as "Arya" (the common regional spelling).
 * - "Hey are you" / "Hi are you" is a frequent phonetic mishearing of "Hey Aria" / "Hi Aria".
 * - "Ora Skincare" / "Aurora Skincare" is corrected to brand name "Aura Skincare".
 * @param {string} text
 * @returns {string}
 */
function normalizeSpeechTranscript(text) {
  if (!text) return "";

  let cleaned = text;

  // 1. Common Indian phonetic spellings of the agent's name
  cleaned = cleaned.replace(/\b(arya|aarya|ariya)\b/gi, "Aria");

  // 2. Misheard conversational greetings (e.g. "hey are you", "hi are you")
  cleaned = cleaned.replace(/\b(hey|hi|hello)\s+are\s+you\b/gi, "$1 Aria");

  // 3. Brand name corrections
  cleaned = cleaned.replace(/\b(ora|aurora)\s+skincare\b/gi, "Aura Skincare");

  return cleaned;
}

/**
 * Initialize the SpeechRecognition instance with required configuration.
 */
function initSpeechRecognition() {
  if (!SpeechRecognition || recognition) return;

  recognition = new SpeechRecognition();
  recognition.lang = "en-IN"; // Indian English accent
  recognition.continuous = true; // Listen continuously until explicitly stopped
  recognition.interimResults = true; // Emit live partial speech results

  recognition.onstart = () => {
    console.log("[SpeechRecognition] Service started listening");
  };

  recognition.onresult = (event) => {
    let interimTranscript = "";

    // Process all results returned in this speech event
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];
      const text = result[0].transcript;

      if (result.isFinal) {
        // Result is final: clear interim display and reset barge-in flag
        hideInterimText();
        hasFiredSpeechStart = false;

        const finalText = normalizeSpeechTranscript(text).trim();
        if (finalText) {
          onUserUtterance(finalText);
        }
      } else {
        // Unfinalized partial words
        interimTranscript += text;
      }
    }

    if (interimTranscript.trim()) {
      // Fire onSpeechStart only once per utterance (at first interim chunk)
      if (!hasFiredSpeechStart) {
        hasFiredSpeechStart = true;
        onSpeechStart();
      }
      showInterimText(normalizeSpeechTranscript(interimTranscript));
    }
  };

  // Auto-restart recognition if the browser stops it while the call is active.
  // Browsers (like Chrome) stop continuous recognition after brief silences.
  recognition.onend = () => {
    console.log("[SpeechRecognition] Service ended");
    hideInterimText();
    hasFiredSpeechStart = false;

    // Only restart if the user hasn't hung up
    if (isCallActive && currentState !== "idle") {
      try {
        recognition.start();
        console.log("[SpeechRecognition] Auto-restarted recognition");
      } catch (err) {
        console.warn("[SpeechRecognition] Auto-restart skipped:", err);
      }
    }
  };

  // Handle errors: mic permission denied, no-speech timeout, network errors
  recognition.onerror = (event) => {
    console.warn("[SpeechRecognition] Error:", event.error);

    if (event.error === "not-allowed" || event.error === "service-not-allowed") {
      showSpeechNotice(
        "Microphone access was denied. Please allow microphone permissions in your browser settings to speak with Aria.",
        "danger"
      );
      stopCall();
    } else if (event.error === "no-speech") {
      // Normal silence timeout; recognition.onend will auto-restart if still in call
      console.log("[SpeechRecognition] Silence detected; keeping listener active");
    } else if (event.error === "network") {
      showSpeechNotice(
        "Speech recognition network error. Please check your internet connection.",
        "warning"
      );
    }
  };
}

/**
 * Start call session: updates state and starts microphone listening.
 */
function startCall() {
  clearSpeechNotice();

  if (!checkBrowserSpeechSupport()) {
    return;
  }

  isCallActive = true;
  setState("listening");

  if (!recognition) {
    initSpeechRecognition();
  }

  try {
    recognition.start();
  } catch (err) {
    console.warn("[SpeechRecognition] start() failed or already running:", err);
  }
}

/**
 * End call session: stops speech recognition and resets state to idle.
 */
function stopCall() {
  isCallActive = false;
  audioQueue.stop();
  hideInterimText();
  hasFiredSpeechStart = false;

  if (recognition) {
    try {
      recognition.stop();
    } catch (err) {
      console.warn("[SpeechRecognition] stop() error:", err);
    }
  }

  setState("idle");
}

// ============================================================================
// Speech Output: AudioQueue & Text-to-Speech (TTS)
// ============================================================================

/**
 * Sequential Audio Queue for streaming TTS playback.
 * - Receives audio blobs from sentence-level synthesis.
 * - Plays audio items strictly in order without overlapping.
 * - Provides stop() to immediately cancel playback and flush pending items (for barge-in).
 */
class AudioQueue {
  constructor() {
    this.queue = []; // Array of { blob: Blob, text: string }
    this.currentAudio = null; // Currently playing HTMLAudioElement
    this.isPlaying = false;
  }

  /**
   * Enqueue an audio blob for playback.
   * @param {Blob} blob - MP3 audio data
   * @param {string} text - Associated sentence text
   */
  enqueue(blob, text) {
    this.queue.push({ blob, text });
    if (!this.isPlaying) {
      this.playNext();
    }
  }

  /**
   * Play the next queued audio item.
   */
  async playNext() {
    if (this.queue.length === 0) {
      this.isPlaying = false;
      this.currentAudio = null;
      if (currentState === "speaking") {
        setState(isCallActive ? "listening" : "idle");
      }
      return;
    }

    this.isPlaying = true;
    setState("speaking");

    const item = this.queue.shift();
    const url = URL.createObjectURL(item.blob);
    const audio = new Audio(url);
    this.currentAudio = audio;

    console.log(`[AudioQueue] Playing sentence: "${item.text}"`);

    audio.onended = () => {
      URL.revokeObjectURL(url);
      this.currentAudio = null;
      this.playNext();
    };

    audio.onerror = (err) => {
      console.warn("[AudioQueue] Audio error, skipping to next:", err);
      URL.revokeObjectURL(url);
      this.currentAudio = null;
      this.playNext();
    };

    try {
      await audio.play();
    } catch (err) {
      console.warn("[AudioQueue] Playback failed or cancelled:", err);
      URL.revokeObjectURL(url);
      this.currentAudio = null;
      this.playNext();
    }
  }

  /**
   * Halts any playing audio and flushes remaining queue items.
   * Used for barge-in (when user starts speaking) or call hangup.
   */
  stop() {
    console.log("[AudioQueue] Stop requested: flushing queue and halting audio");
    this.queue = [];
    this.isPlaying = false;

    if (this.currentAudio) {
      this.currentAudio.pause();
      this.currentAudio.currentTime = 0;
      this.currentAudio = null;
    }

    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }

    if (currentState === "speaking") {
      setState(isCallActive ? "listening" : "idle");
    }
  }
}

const audioQueue = new AudioQueue();

/**
 * Fallback synthesizer using browser window.speechSynthesis when edge-tts is unavailable.
 * @param {string} text
 */
function speakWithBrowserFallback(text) {
  if (!window.speechSynthesis) {
    console.error("[SpeechSynthesis] SpeechSynthesis API not supported in this browser.");
    return;
  }

  setState("speaking");
  window.speechSynthesis.cancel(); // Cancel any lingering speech

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "en-IN";
  utterance.rate = 1.05; // Slightly faster to match edge-tts (+5%)

  // Pick an Indian English voice if present in browser
  const voices = window.speechSynthesis.getVoices();
  const indianVoice = voices.find(
    (v) => v.lang === "en-IN" || v.lang === "en_IN"
  );
  if (indianVoice) {
    utterance.voice = indianVoice;
  }

  utterance.onend = () => {
    console.log(`[SpeechSynthesis] Completed speaking: "${text}"`);
    if (currentState === "speaking") {
      setState(isCallActive ? "listening" : "idle");
    }
  };

  utterance.onerror = (err) => {
    console.warn("[SpeechSynthesis] Error during speech synthesis:", err);
    if (currentState === "speaking") {
      setState(isCallActive ? "listening" : "idle");
    }
  };

  console.log(`[SpeechSynthesis] Speaking fallback for: "${text}"`);
  window.speechSynthesis.speak(utterance);
}

/**
 * Synthesizes speech for a single sentence via /api/tts (edge-tts).
 * Enqueues the audio into the AudioQueue.
 * If edge-tts fails or returns an error, triggers window.speechSynthesis fallback.
 * @param {string} sentence
 * @param {boolean} simulateFailure
 */
async function speakSentence(sentence, simulateFailure = false) {
  const text = sentence.trim();
  if (!text) return;

  try {
    const res = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, simulate_failure: simulateFailure }),
    });

    if (!res.ok) {
      throw new Error(`TTS server returned HTTP ${res.status}`);
    }

    const audioBlob = await res.blob();
    audioQueue.enqueue(audioBlob, text);
  } catch (err) {
    console.warn(`[TTS] Edge-TTS failed for "${text}". Falling back to browser SpeechSynthesis:`, err);
    speakWithBrowserFallback(text);
  }
}

/**
 * Test button: speaks a single hardcoded sentence using Edge TTS.
 */
function testSpeakSingle() {
  const sentence = "Hello! I am Aria from Aura Skincare. How can I help you today?";
  addTranscriptMessage("agent", sentence);
  speakSentence(sentence);
}

/**
 * Test button: demonstrates the sequential audio queue by sending 2 sentences back-to-back.
 * Sentence 2 is queued while Sentence 1 plays, demonstrating gapless ordered playback.
 */
function testSpeakQueue() {
  const sentence1 = "Your order ORD-101 has been dispatched with BlueDart.";
  const sentence2 = "It is out for delivery and will arrive by 6 PM today.";
  addTranscriptMessage("agent", `${sentence1} ${sentence2}`);
  speakSentence(sentence1);
  speakSentence(sentence2);
}

/**
 * Test button: tests the browser window.speechSynthesis fallback by simulating an edge-tts failure.
 */
function testSpeakFallback() {
  const sentence = "This is a fallback test spoken directly by your browser using speech synthesis.";
  addTranscriptMessage("agent", sentence);
  speakSentence(sentence, true); // simulate_failure = true
}

/**
 * Fetch mock orders from the FastAPI backend and render them in the helper panel.
 */
async function fetchOrders() {
  try {
    const res = await fetch("/api/orders");
    if (!res.ok) {
      throw new Error(`Failed to load orders: ${res.status}`);
    }
    const orders = await res.json();
    renderOrders(orders);
  } catch (err) {
    console.error("Error loading orders:", err);
    ordersContainer.innerHTML = `
      <div class="loading-orders" style="color: var(--danger);">
        Could not load test orders from backend.
      </div>
    `;
  }
}

/**
 * Render order cards into the test helper panel.
 */
function renderOrders(orders) {
  if (!orders || orders.length === 0) {
    ordersContainer.innerHTML = '<div class="loading-orders">No orders found.</div>';
    return;
  }

  ordersContainer.innerHTML = orders
    .map((order) => {
      const statusClass = `status-${order.status.toLowerCase().replace(/\s+/g, "-")}`;
      return `
        <div class="order-card">
          <div class="order-card-header">
            <span class="order-id">${order.order_id}</span>
            <span class="order-status ${statusClass}">${order.status}</span>
          </div>
          <div class="order-detail-row">
            <strong>Customer:</strong> ${order.customer}
          </div>
          <div class="order-detail-row">
            <strong>Product:</strong> ${order.product} (₹${order.value})
          </div>
          <div class="order-notes">
            <strong>Notes:</strong> ${order.notes}
          </div>
        </div>
      `;
    })
    .join("");
}

/**
 * Helper to simulate a back-and-forth chat turn during UI testing.
 */
let sampleTurnIndex = 0;
const sampleTurns = [
  { sender: "customer", text: "Hi, can you tell me the status of order ORD-101?" },
  { sender: "agent", text: "Hello! Let me check that for you. ORD-101 is currently Out for Delivery via BlueDart and expected by 6 PM today." },
  { sender: "customer", text: "Can I return order ORD-102? I opened it last week." },
  { sender: "agent", text: "I understand! However, our policy accepts returns within 7 days of delivery for unopened items. Since ORD-102 was delivered 14 days ago, it cannot be returned." },
  { sender: "customer", text: "I want to cancel order ORD-103." },
  { sender: "agent", text: "Sure thing! ORD-103 is currently Processing, so I've successfully cancelled it for you." },
];

function addSampleChatTurn() {
  const turn = sampleTurns[sampleTurnIndex % sampleTurns.length];
  addTranscriptMessage(turn.sender, turn.text);
  sampleTurnIndex++;
}

// Event Listeners for Call Buttons
startCallBtn.addEventListener("click", () => {
  startCall();
});

endCallBtn.addEventListener("click", () => {
  stopCall();
});

clearTranscriptBtn.addEventListener("click", () => {
  // Remove all completed chat messages while preserving placeholder & interim DOM
  const messages = transcriptBox.querySelectorAll(".chat-msg:not(.interim)");
  messages.forEach((msg) => msg.remove());
  if (transcriptPlaceholder) {
    transcriptPlaceholder.style.display = "block";
  }
  hideInterimText();
});

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  setState("idle");
  fetchOrders();
  checkBrowserSpeechSupport();
});

// ----- THROWAWAY: Text Chat Test (remove once voice pipeline is live) -----

// Conversation history for the text chat panel (separate from voice transcript)
let textChatHistory = [];

const textChatBox = document.getElementById("textChatBox");
const textInput = document.getElementById("textInput");
const textSendBtn = document.getElementById("textSendBtn");

/**
 * Add a message bubble into the text chat test box.
 * @param {'user' | 'assistant' | 'thinking'} role
 * @param {string} text
 * @returns {HTMLElement} the bubble element (so we can update 'thinking' in-place)
 */
function appendTextBubble(role, text) {
  const div = document.createElement("div");
  div.className = `text-chat-msg ${role}`;
  div.textContent = text;
  textChatBox.appendChild(div);
  textChatBox.scrollTop = textChatBox.scrollHeight;
  return div;
}

/**
 * Send the text input to POST /api/chat, stream back the reply, and display it.
 * History is maintained across multiple turns so Aria has context.
 */
async function sendTextMessage() {
  const userText = textInput.value.trim();
  if (!userText) return;

  // Disable input while waiting for response
  textInput.value = "";
  textInput.disabled = true;
  textSendBtn.disabled = true;

  // Show the user's message and add it to history
  appendTextBubble("user", userText);
  textChatHistory.push({ role: "user", content: userText });

  // Show a "thinking" placeholder while the request is in flight
  const thinkingBubble = appendTextBubble("thinking", "Aria is thinking...");

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ history: textChatHistory }),
    });

    if (!res.ok) {
      throw new Error(`Server error: ${res.status}`);
    }

    // Read the streamed response text
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let fullReply = "";

    // Replace the "thinking" bubble with the actual reply as it streams in
    thinkingBubble.className = "text-chat-msg assistant";
    thinkingBubble.textContent = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      fullReply += chunk;
      thinkingBubble.textContent = fullReply;
      textChatBox.scrollTop = textChatBox.scrollHeight;
    }

    // Add the completed reply to history for the next turn
    textChatHistory.push({ role: "assistant", content: fullReply });
  } catch (err) {
    thinkingBubble.className = "text-chat-msg assistant";
    thinkingBubble.textContent = `Error: ${err.message}`;
    console.error("Text chat error:", err);
  } finally {
    textInput.disabled = false;
    textSendBtn.disabled = false;
    textInput.focus();
  }
}

/** Clear the text chat history and display. */
function clearTextChat() {
  textChatHistory = [];
  textChatBox.innerHTML = "";
}

// Allow pressing Enter to send in the text input
textInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !textSendBtn.disabled) {
    sendTextMessage();
  }
});
