"""Sprint Planning Agent."""
import json
import re
import uuid
from dataclasses import asdict
from app.agents.base import get_default_llm
from app.sprint import BacklogItem, add_items, find_item_by_title, list_items, update_item_status

class SprintPlanningAgent:
    def __init__(self):
        self.llm = get_default_llm()

    def run(self, request: str) -> dict:
        from app.db import crud
        wps = crud.list_work_packages()
        ctx = "\n".join(f"  id: {r['id']}, title: {r['title']}, status: {r.get('status')}" for r in wps) or "  (yok)"
        r = self.llm.invoke([
            {"role": "system", "content": "Sadece JSON dön. operation: create_items | list_items | update_status. create_items için items dizisi; update_status için update.item_id ve update.status (todo/in_progress/done)."},
            {"role": "user", "content": f"Mevcut item'lar:\n{ctx}\n\nİstek: {request}"},
        ])
        raw = (r.content or "").strip()
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if m:
            raw = m.group(1).strip()
        try:
            ops = json.loads(raw)
        except json.JSONDecodeError:
            ops = {"operation": "list_items", "filters": {}}
        op = ops.get("operation")
        if op == "create_items":
            items = [BacklogItem(id=x.get("id") or "", type=x.get("type", "product"), title=x.get("title", ""), description=x.get("description", ""), status=x.get("status", "todo")) for x in ops.get("items", [])]
            for i in items:
                if not i.id:
                    i.id = str(uuid.uuid4())
            add_items(items)
            return {"operation": "create_items", "created": [i.id for i in items]}
        if op == "update_status":
            u = ops.get("update", {}) or {}
            item_id = u.get("item_id")
            status = (u.get("status") or "").strip().lower()
            if not item_id and u.get("item_title"):
                found = find_item_by_title(u["item_title"])
                if found:
                    item_id = found.id
            if not item_id or status not in ("todo", "in_progress", "done"):
                return {"operation": "update_status", "error": "item_id veya geçerli status gerekli"}
            updated = update_item_status(item_id, status)
            return {"operation": "update_status", "item": updated} if updated else {"operation": "update_status", "error": "bulunamadı"}
        flt = ops.get("filters") or {}
        items = list_items(type=flt.get("type"), sprint=flt.get("sprint"), status=flt.get("status"))
        return {"operation": "list_items", "items": [asdict(i) for i in items]}
