import os
import re
import json
import time
import tempfile
from groq import Groq
from duckduckgo_search import DDGS
from .rag_service import query_rag

# ---------------------------------------------------------------------------
# LLM: Groq (llama-3.3-70b-versatile)
#   Free tier: 14,400 req/day, 30 RPM — far more generous than Gemini free
# Image gen: Gemini Imagen (optional — fails gracefully if key is expired)
# ---------------------------------------------------------------------------

_MAX_TOPIC_CHARS     = 3000   # transcript / text → ~750 tokens
_MAX_RESEARCH_CHARS  = 400    # web/RAG context snippet
_MAX_CONTENT_PREVIEW = 1500   # chars sent for re-generation

GROQ_MODEL = "llama-3.3-70b-versatile"   # best free Groq model


# ---------------------------------------------------------------------------
# Groq client
# ---------------------------------------------------------------------------

def get_groq_client() -> Groq:
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY is not set. Add it to your .env file. "
            "Get a free key at https://console.groq.com"
        )
    return Groq(api_key=api_key)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class QuotaExceededError(Exception):
    """Raised when all retries are exhausted due to quota limits."""
    pass

class InvalidApiKeyError(Exception):
    """Raised when an API key is invalid."""
    pass


# ---------------------------------------------------------------------------
# Groq text generation with retry
# ---------------------------------------------------------------------------

def groq_generate(prompt: str, max_tokens: int = 1200, max_retries: int = 2) -> str:
    """
    Call Groq's chat completions API with automatic retry on rate-limit errors.
    Returns the response text string.
    Groq free limits: 30 RPM, 14,400 RPD — much more generous than Gemini free.
    """
    client = get_groq_client()

    for attempt in range(max_retries + 1):
        try:
            completion = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.7,
            )
            return completion.choices[0].message.content

        except Exception as e:
            err_str = str(e)
            err_lower = err_str.lower()

            # Invalid key — stop immediately
            if any(k in err_lower for k in ("invalid api key", "authentication", "unauthorized", "401")):
                raise InvalidApiKeyError(
                    "Your Groq API key is invalid. "
                    "Please check https://console.groq.com and update GROQ_API_KEY in .env"
                )

            # Rate limit / quota — retry with back-off
            is_quota = any(k in err_lower for k in ("429", "rate limit", "quota", "too many"))
            if is_quota:
                if attempt < max_retries:
                    wait = 20 * (attempt + 1)   # 20s, 40s
                    print(f"[Groq] Rate limited. Retrying in {wait}s (attempt {attempt+1}/{max_retries})...")
                    time.sleep(wait)
                else:
                    raise QuotaExceededError(
                        "Groq rate limit reached. "
                        "Wait a minute and try again, or check https://console.groq.com/usage"
                    )
            else:
                raise   # unknown error — bubble up


# ---------------------------------------------------------------------------
# Image generation — powered by Pollinations.ai
# Free, no API key required, high quality FLUX model.
# ---------------------------------------------------------------------------

def generate_blog_image(title: str, keywords: str) -> bytes | None:
    """
    Generates a blog thumbnail using Pollinations.ai (free, no API key).
    Returns raw JPEG/PNG bytes on success, None on any failure (non-fatal).
    """
    import urllib.request
    import urllib.parse

    try:
        prompt = (
            f"A professional blog header image for an article titled: '{title}'. "
            f"Themes: {keywords}. "
            "Modern digital illustration, vibrant colors, clean design. "
            "No text, no letters, no watermarks."
        )
        
        encoded_prompt = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=576&nologo=true"

        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            image_bytes = response.read()
            print(f"[Image] Thumbnail generated via Pollinations.ai ({len(image_bytes)} bytes)")
            return image_bytes

    except Exception as e:
        print(f"[Image] Image generation failed: {e}")
        return None



# ---------------------------------------------------------------------------
# YouTube: yt-dlp audio download
# ---------------------------------------------------------------------------

def download_yt_audio(yt_url: str, video_id: str) -> str:
    """
    Downloads the best available audio track from a YouTube video.
    Returns the absolute path to the downloaded file.
    """
    import yt_dlp

    tmp_dir = tempfile.mkdtemp()
    out_template = os.path.join(tmp_dir, video_id)

    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best',
        'outtmpl': out_template,
        'quiet': True,
        'no_warnings': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(yt_url, download=True)
        ext = info.get('ext', 'm4a')

    candidate = f"{out_template}.{ext}"
    if os.path.exists(candidate):
        return candidate
    if os.path.exists(out_template):
        return out_template

    raise FileNotFoundError(f"[YT] Downloaded file not found. Tried: {candidate}, {out_template}")


# ---------------------------------------------------------------------------
# AssemblyAI transcription
# ---------------------------------------------------------------------------

def transcribe_with_assemblyai(audio_path: str) -> str:
    """
    Sends a local audio file to AssemblyAI and returns the transcript text.
    """
    import assemblyai as aai

    api_key = os.environ.get("ASSEMBLYAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("ASSEMBLYAI_API_KEY is not set in your .env file.")

    aai.settings.api_key = api_key

    config = aai.TranscriptionConfig(speech_models=["universal-3-pro"])
    transcriber = aai.Transcriber()

    print(f"[AssemblyAI] Uploading {os.path.basename(audio_path)} for transcription...")
    transcript = transcriber.transcribe(audio_path, config=config)

    if transcript.status == aai.TranscriptStatus.error:
        raise Exception(f"AssemblyAI error: {transcript.error}")

    print(f"[AssemblyAI] Transcription complete ({len(transcript.text)} chars)")
    return transcript.text


# ---------------------------------------------------------------------------
# Research (zero API calls)
# ---------------------------------------------------------------------------

class ResearchAgent:
    def execute(self, topic: str, use_search: bool = False, use_rag: bool = False) -> str:
        parts = []

        if use_rag:
            try:
                ctx = query_rag(topic)
                if ctx:
                    parts.append(f"[Document Context]:\n{ctx[:_MAX_RESEARCH_CHARS]}")
            except Exception as e:
                print(f"[RAG] Error: {e}")

        if use_search:
            try:
                results = DDGS().text(topic[:200], max_results=3)
                snippets = [f"- {r['title']}: {r['body'][:150]}" for r in results]
                parts.append("[Web Research]:\n" + "\n".join(snippets))
            except Exception as e:
                print(f"[Search] Error: {e}")

        return "\n\n".join(parts)[:_MAX_RESEARCH_CHARS]


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

def _extract_json(raw: str) -> dict | None:
    clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", clean)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


def _length_hint(target_length: str) -> str:
    return {
        "short":  "~400 words",
        "medium": "~700 words",
        "long":   "~1200 words",
    }.get((target_length or "medium").lower(), "~700 words")


# ---------------------------------------------------------------------------
# Main blog generation workflow  — powered by Groq
# ---------------------------------------------------------------------------

class BlogGenerationWorkflow:
    """
    ONE Groq API call per blog.
    Groq free tier: 14,400 req/day, 30 RPM — no quota issues.
    Image generation via Gemini is optional and non-blocking.
    """

    def run(self, topic: str, params: dict) -> dict:
        tone          = params.get("tone", "Informative")
        audience      = params.get("audience", "General")
        target_length = params.get("target_length", "Medium")
        language      = params.get("language", "English")
        use_search    = params.get("use_search", False)
        use_rag       = params.get("use_rag", False)

        # 1. Research (zero API calls)
        research_ctx = ResearchAgent().execute(topic, use_search=use_search, use_rag=use_rag)

        # 2. Trim input to stay lean
        trimmed = topic[:_MAX_TOPIC_CHARS]
        if len(topic) > _MAX_TOPIC_CHARS:
            trimmed += "\n[... content trimmed ...]"

        research_block = (
            f"\nAdditional context:\n{research_ctx}\n" if research_ctx else ""
        )

        # 3. Single Groq call — write + SEO in one prompt
        prompt = f"""You are a professional blog writer. Write a blog post and return its SEO metadata as JSON.

Source Content: {trimmed}
Tone: {tone} | Audience: {audience} | Length: {_length_hint(target_length)} | Language: {language}
{research_block}
Rules:
- Write ONLY in {language}
- Use a strong hook, H2/H3 section headings, and a conclusion
- Do NOT mention YouTube, video, transcript, or audio — write as a natural article
- Be informative, engaging, and well-structured

Return ONLY valid JSON (no markdown fences, no extra text):
{{"content": "<full blog in Markdown>", "meta_title": "<max 60 chars>", "meta_description": "<max 160 chars>", "keywords": "<comma-separated>"}}"""

        print(f"[Groq] Generating blog with {GROQ_MODEL}...")
        raw = groq_generate(prompt, max_tokens=1200)
        print(f"[Groq] Generation complete ({len(raw)} chars)")

        parsed = _extract_json(raw)

        if parsed and "content" in parsed:
            final_content = parsed["content"]
            seo_data = {
                "meta_title":       parsed.get("meta_title", topic[:55]),
                "meta_description": parsed.get("meta_description", ""),
                "keywords":         parsed.get("keywords", ""),
            }
        else:
            print("[Workflow] JSON parse failed — using raw text as blog content.")
            final_content = raw
            seo_data = {
                "meta_title":       topic[:55] + ("..." if len(topic) > 55 else ""),
                "meta_description": topic[:155] + ("..." if len(topic) > 155 else ""),
                "keywords":         "blog, article",
            }

        # 4. Generate thumbnail (optional, Gemini — fails gracefully)
        image_bytes = generate_blog_image(
            title=seo_data["meta_title"],
            keywords=seo_data["keywords"]
        )

        return {
            "content":     final_content,
            "seo_data":    seo_data,
            "image_bytes": image_bytes,
        }


# ---------------------------------------------------------------------------
# Regeneration helper — also powered by Groq
# ---------------------------------------------------------------------------

def regenerate_content(original_content: str, instruction: str) -> str:
    preview = original_content[:_MAX_CONTENT_PREVIEW]
    suffix  = "\n[... content continues ...]" if len(original_content) > _MAX_CONTENT_PREVIEW else ""

    prompt = (
        f"You are a blog editor.\n"
        f"Instruction: {instruction}\n\n"
        f"Apply the instruction to the blog post below and return the COMPLETE updated post.\n\n"
        f"Original Post:\n{preview}{suffix}"
    )

    print(f"[Groq] Regenerating blog with instruction: {instruction[:60]}...")
    return groq_generate(prompt, max_tokens=1200)
