# AeroTech Agentic Hub – Backend

FastAPI backend. Railway'de Dockerfile ile ayağa kalkar.

## GitHub'a yükleme

```bash
cd thy-backend
git init -b main
git add .
git commit -m "Initial backend repo"
git remote add origin https://github.com/Daption-ciray/aerotech-backend.git
git push -u origin main
```

(Önce GitHub'da boş repo oluştur: `aerotech-backend`)

## Railway'de deploy

1. [Railway](https://railway.app) → New Project → Deploy from GitHub repo → `aerotech-backend` seç.
2. Root Dockerfile otomatik algılanır. Deploy edin.
3. **Variables** ekleyin: `OPENAI_API_KEY`, isteğe bağlı `TAVILY_API_KEY`, `SERPER_API_KEY`, `LLM_MODEL`.
4. **Settings** → **Networking** → **Generate Domain** ile public URL alın (örn. `https://xxx.railway.app`). Bu URL'yi frontend'de `VITE_API_URL` olarak kullanacaksınız.

## Yerel çalıştırma

```bash
python -m venv .venv && source .venv/bin/activate  # veya Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # .env'i düzenleyin
uvicorn app.main:app --reload --port 8000
```
