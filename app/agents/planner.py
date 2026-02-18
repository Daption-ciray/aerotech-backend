"""Work Package Planner Agent."""
from langchain_openai import ChatOpenAI
from app.config import settings


class WorkPackagePlannerAgent:
    def __init__(self):
        # Planlama için mümkünse ayrı, hızlı bir model kullan
        model_name = settings.PLANNER_LLM_MODEL or settings.LLM_MODEL
        self.llm = ChatOpenAI(model=model_name, temperature=0)

    def run(self, fault_description: str, tech_context: str) -> str:
        system = (
            "Sen Part-145 uyumlu uçak bakım planlayıcısısın. "
            "Sadece GEÇERLİ JSON üret. Açıklama, yorum veya düz metin ekleme.\n\n"
            "JSON formatı:\n"
            "{\n"
            '  \"work_package_id\": \"string\",\n'
            '  \"aircraft_type\": \"string\",\n'
            '  \"component\": \"string\",\n'
            '  \"steps\": [\n'
            '    {\"step\": 1, \"description\": \"string\", \"estimated_minutes\": 30}\n'
            "  ],\n"
            '  \"total_estimated_minutes\": 120\n'
            "}\n"
        )
        user = (
            "TEKNİK BAĞLAM (özetlenmiş):\n"
            f"{tech_context}\n\n"
            "ARIZA / ŞİKAYET:\n"
            f"{fault_description}\n\n"
            "Yukarıdaki formatta TEK bir iş paketi JSON'u üret."
        )
        r = self.llm.invoke(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
        )
        return r.content or ""
