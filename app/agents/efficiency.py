"""Efficiency Agent."""
import json as _json
from app.agents.base import get_default_llm
from app.analytics import list_completed, compute_efficiency_summary
from app.services.data import get_efficiency_metrics, get_work_packages

class EfficiencyAgent:
    def __init__(self):
        self.llm = get_default_llm()

    def run(self) -> dict:
        metrics = compute_efficiency_summary()
        completed = list_completed()
        wp_list = get_work_packages()
        fallback = get_efficiency_metrics()
        approved = sum(1 for p in wp_list if p.get("status") == "approved")
        total = len(wp_list) or 1
        if not metrics.get("total_completed") and not completed:
            metrics = {"total_completed": approved, "total_work_packages": len(wp_list), "first_pass_rate": round(approved / total * 100, 1) if total else 0, "avg_completion_days": fallback.get("avg_completion_days"), "throughput_per_day": fallback.get("tasks_per_hour")}
        system = "Sen verimlilik analisti. Metrikleri özetle ve kısa iyileştirme önerileri ver."
        user = f"METRİKLER:\n{_json.dumps(metrics, ensure_ascii=False)}\n\nÖrnek tamamlanan: {[{'id': c.id, 'rework': c.rework_count} for c in completed[:5]]}"
        r = self.llm.invoke([{"role": "system", "content": system}, {"role": "user", "content": user}])
        try:
            data = _json.loads(r.content)
        except Exception:
            data = {"summary": r.content, "suggestions": []}
        data["metrics"] = metrics
        return data
