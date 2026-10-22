"""Edge-TTS integration for generating speech audio from response text."""

from typing import AsyncGenerator
import re
import edge_tts

# Default voice settings for Aria (warm Indian English, slightly brisk pace for natural conversational agents)
DEFAULT_VOICE = "en-IN-NeerjaNeural"
DEFAULT_RATE = "+5%"

# Regex to detect sentence boundaries: period, question mark, or exclamation mark followed by whitespace
SENTENCE_END_PATTERN = re.compile(r"([.?!])\s+")


async def generate_speech(
    text: str, voice: str = DEFAULT_VOICE, rate: str = DEFAULT_RATE
) -> AsyncGenerator[bytes, None]:
    """Generate audio bytes for a text snippet using Microsoft Edge TTS.

    Yields raw audio chunks (mp3 format) as they arrive from the Edge TTS service.
    """
    clean_text = text.strip()
    if not clean_text:
        return

    communicate = edge_tts.Communicate(clean_text, voice=voice, rate=rate)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            yield chunk["data"]


async def synthesize_sentence_bytes(
    text: str, voice: str = DEFAULT_VOICE, rate: str = DEFAULT_RATE
) -> bytes:
    """Convenience helper to gather all audio bytes for a sentence into a single bytes object.

    Useful when sending complete audio blobs to the frontend audio queue.
    """
    chunks: list[bytes] = []
    async for chunk in generate_speech(text, voice=voice, rate=rate):
        chunks.append(chunk)
    return b"".join(chunks)


async def stream_sentences(
    text_stream: AsyncGenerator[str, None],
) -> AsyncGenerator[str, None]:
    """Accumulate streamed tokens and yield complete sentences as soon as they form.

    This enables low-latency streaming TTS: instead of waiting for the full LLM
    reply (2-4 seconds), the first sentence is sent to TTS immediately (~500ms).
    """
    buffer = ""
    async for chunk in text_stream:
        buffer += chunk
        while True:
            match = SENTENCE_END_PATTERN.search(buffer)
            if not match:
                break
            # Split point is after the punctuation and following whitespace
            split_idx = match.end()
            sentence = buffer[:split_idx].strip()
            buffer = buffer[split_idx:]
            if sentence:
                yield sentence

    # Yield any remaining text left in the buffer when the stream completes
    remaining = buffer.strip()
    if remaining:
        yield remaining
