"""
Parça görseli: Gemini Nano Banana ile üretim, Gemini VLM ile doğrulama.
"""
import base64
import os
from pathlib import Path
from app.config import settings

# Disk + bellek cache dizini
_CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "parts"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_IMAGE_CACHE: dict[str, str] = {}


def _slugify_part_name(part_name: str) -> str:
    base = (part_name or "").strip().lower()
    # Sadece harf, rakam ve alt çizgi bırakalım
    out = []
    for ch in base:
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "/"):
            out.append("_")
    slug = "".join(out).strip("_") or "part"
    return slug


PART_DIAGRAM_PROMPT = (
    "Create a clear, detailed technical diagram of the aircraft component: {part_name}. "
    "Show the component as it appears in real aircraft maintenance contexts. "
    "Include visible structural features, mounting points, connections, and key physical characteristics. "
    "Use a clean, professional technical drawing style suitable for maintenance training documentation. "
    "The image should be recognizable as the specific aircraft part mentioned. "
    "No text labels, annotations, or text overlays on the image itself."
)
VLM_VERIFY_PROMPT = (
    'Does this image clearly show the aircraft component or part named "{part_name}"? '
    "The image should depict the actual physical part, its structure, shape, and recognizable features. "
    "Answer only YES or NO in the first word, then optionally one short reason."
)


def _genai_client():
    key = settings.GOOGLE_GENAI_API_KEY or os.getenv("GOOGLE_GENAI_API_KEY")
    if not key:
        import logging
        logging.warning(
            "GOOGLE_GENAI_API_KEY bulunamadı. settings.GOOGLE_GENAI_API_KEY=%s, os.getenv=%s",
            settings.GOOGLE_GENAI_API_KEY,
            os.getenv("GOOGLE_GENAI_API_KEY"),
        )
        return None
    try:
        from google import genai
        return genai.Client(api_key=key)
    except ImportError as e:
        import logging
        logging.warning("google-genai paketi yüklü değil. pip install google-genai | %s", e)
        return None


def generate_part_diagram(part_name: str) -> dict:
    """Gemini Nano Banana (GENAI_IMAGE_MODEL) ile parça çizimi üretir.

    Sık istenen parçalar için disk + bellek tabanlı cache kullanır.
    """
    slug = _slugify_part_name(part_name)

    # Önce bellek cache
    if slug in _IMAGE_CACHE:
        return {"image_base64": _IMAGE_CACHE[slug], "mime_type": "image/png"}

    # Sonra disk cache
    cache_path = _CACHE_DIR / f"{slug}.png"
    if cache_path.exists():
        raw = cache_path.read_bytes()
        b64 = base64.b64encode(raw).decode("ascii")
        _IMAGE_CACHE[slug] = b64
        return {"image_base64": b64, "mime_type": "image/png"}

    client = _genai_client()
    if not client:
        return {"error": "Gemini client yok (GOOGLE_GENAI_API_KEY veya google-genai paketi eksik)"}
    prompt = PART_DIAGRAM_PROMPT.format(part_name=part_name)
    try:
        response = client.models.generate_content(model=settings.GENAI_IMAGE_MODEL, contents=[prompt])
        parts = []
        if hasattr(response, "candidates") and response.candidates:
            content = response.candidates[0].content
            parts = getattr(content, "parts", []) or []
        for part in parts:
            inline = getattr(part, "inline_data", None) or (part.get("inline_data") if isinstance(part, dict) else None)
            if not inline:
                continue
            raw = getattr(inline, "data", None) or (inline.get("data", b"") if isinstance(inline, dict) else b"")
            if raw:
                # Disk cache'e yaz
                try:
                    cache_path.write_bytes(raw)
                except Exception:
                    # Cache yazılamasa da ana akış devam etsin
                    pass
                b64 = base64.b64encode(raw).decode("ascii")
                _IMAGE_CACHE[slug] = b64
                mime = getattr(inline, "mime_type", None) or (inline.get("mime_type", "image/png") if isinstance(inline, dict) else "image/png")
                return {"image_base64": b64, "mime_type": mime or "image/png"}
        return {"error": "Görsel üretilemedi"}
    except Exception as e:
        return {"error": str(e)}


def verify_part_image(image_url: str | None, image_base64: str | None, part_name: str) -> dict:
    """Gemini VLM ile görselin o parçayı gösterip göstermediğini doğrular."""
    client = _genai_client()
    if not client:
        return {"verified": False, "reason": "Gemini client yok (GOOGLE_GENAI_API_KEY veya google-genai paketi eksik)"}
    if not image_url and not image_base64:
        return {"verified": False, "reason": "Görsel yok"}
    content_parts = []
    if image_base64:
        content_parts.append({
            "inline_data": {"mime_type": "image/png", "data": base64.b64decode(image_base64)},
        })
    elif image_url:
        return {"verified": False, "reason": "Gemini VLM için image_base64 kullanın"}
    content_parts.append({"text": VLM_VERIFY_PROMPT.format(part_name=part_name)})
    try:
        response = client.models.generate_content(
            model=settings.GEMINI_VLM_MODEL,
            contents=content_parts,
        )
        text = ""
        if hasattr(response, "text") and response.text:
            text = response.text
        elif hasattr(response, "candidates") and response.candidates:
            for p in getattr(response.candidates[0].content, "parts", []) or []:
                if getattr(p, "text", None):
                    text += p.text
        text = text.strip().upper()
        verified = "YES" in text[:60] or "EVET" in text[:60]
        return {"verified": verified, "reason": text or ""}
    except Exception as e:
        return {"verified": False, "reason": str(e)}
