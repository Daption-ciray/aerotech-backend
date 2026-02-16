"""Search & RAG Agent."""
from langchain_core.messages import HumanMessage, SystemMessage
from app.agents.base import get_default_llm

class SearchRAGAgent:
    def __init__(self, retriever, web_search_tool=None):
        self.llm = get_default_llm()
        self.retriever = retriever
        self.web_search_tool = web_search_tool

    def run(self, query: str) -> str:
        rag = ""
        if self.retriever:
            try:
                docs = self.retriever.invoke(query)
                rag = "\n\n".join(d.page_content for d in docs[:5])
            except Exception:
                pass
        web = ""
        if self.web_search_tool:
            try:
                web = self.web_search_tool.invoke(query)
            except Exception:
                pass
        system = "Sen uçak bakım teknik araştırma asistanısın. Soruya kaynaklara dayanarak yanıt ver."
        prompt = f"SORU: {query}\n\n--- RAG ---\n{rag or '(yok)'}\n\n--- WEB ---\n{web or '(yok)'}"
        r = self.llm.invoke([SystemMessage(content=system), HumanMessage(content=prompt)])
        return (r.content or "").strip()
