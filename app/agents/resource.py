"""Resource & Compliance Agent."""
from app.agents.base import get_default_llm

class ResourceComplianceAgent:
    def __init__(self, resource_tool=None):
        self.llm = get_default_llm()
        self.resource_tool = resource_tool

    def run(self, work_package_json: str) -> str:
        data = ""
        if self.resource_tool:
            try:
                data = self.resource_tool.invoke(work_package_json)
            except Exception as e:
                data = str(e)
        system = "Sen EASA Part-145 kaynak planlama uzmanısın. İş paketi ve kaynak verisine göre plan öner."
        user = f"İŞ PAKETİ:\n{work_package_json}\n\nKAYNAK VERİSİ:\n{data or '(yok)'}"
        r = self.llm.invoke([{"role": "system", "content": system}, {"role": "user", "content": user}])
        return r.content
