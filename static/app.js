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
  const isCallActive = currentState !== "idle";
  startCallBtn.disabled = isCallActive;
  endCallBtn.disabled = !isCallActive;

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

  transcriptBox.appendChild(msgDiv);
  // Auto-scroll to the bottom of the transcript
  transcriptBox.scrollTop = transcriptBox.scrollHeight;
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
  // Start call initiates listening state
  setState("listening");
});

endCallBtn.addEventListener("click", () => {
  // End call returns agent to idle state
  setState("idle");
});

clearTranscriptBtn.addEventListener("click", () => {
  transcriptBox.innerHTML = `
    <div class="transcript-placeholder" id="transcriptPlaceholder">
      Click <strong>Start Call</strong> and speak to Aria, or use the simulation buttons below to test states.
    </div>
  `;
});

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  setState("idle");
  fetchOrders();
});
