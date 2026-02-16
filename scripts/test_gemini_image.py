#!/usr/bin/env python3
"""
Gemini Nano Banana (parça görseli) testi.
Çalıştırma: thy-backend dizininden:
  python scripts/test_gemini_image.py
Gereksinim: .env içinde GOOGLE_GENAI_API_KEY
"""
import os
import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_root))
os.chdir(backend_root)

from app.agents.part_visual import generate_part_diagram


def main():
    print("Gemini Nano Banana (parça görseli) testi")
    part_name = "elevator trim"
    print("  Parça:", part_name)
    print()

    out = generate_part_diagram(part_name)
    if "error" in out:
        print("HATA:", out["error"])
        if "GOOGLE_GENAI_API_KEY" in str(out.get("error", "")):
            print("\n.env içinde GOOGLE_GENAI_API_KEY tanımlayın.")
        return 1

    b64 = out.get("image_base64")
    if not b64:
        print("HATA: Görsel üretilemedi")
        return 1

    import base64
    raw = base64.b64decode(b64)
    out_path = backend_root / "test_gemini_output.png"
    out_path.write_bytes(raw)
    print("OK - Görsel üretildi")
    print("  Kaydedildi:", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
