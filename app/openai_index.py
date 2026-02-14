"""
OpenAI Vector Store index builder for FAA / AMT PDFs.

Bu script, PDF'leri OpenAI'ye yükleyip managed vector store oluşturur.

Kullanım:

    cd /Users/daption-ciray/Desktop/Project/THY
    source .venv311/bin/activate
    python -m app.openai_index

Script sonunda üretilen VECTOR_STORE_ID'yi .env dosyasına
OPENAI_VECTOR_STORE_ID olarak eklemelisin.
"""

from pathlib import Path
import os
import requests

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "app" / "data" if (BASE_DIR / "app" / "data").exists() else BASE_DIR / "data"


def _get_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY .env içinde tanımlı olmalı.")
    return api_key


def create_vector_store(name: str = "aerotech-faa-amt") -> str:
    api_key = _get_api_key()
    resp = requests.post(
        "https://api.openai.com/v1/vector_stores",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "OpenAI-Beta": "assistants=v2",
        },
        json={"name": name},
        timeout=3000,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["id"]


def upload_pdfs_to_store(vector_store_id: str):
    api_key = _get_api_key()

    # Önce PDF'leri File API ile yükle
    pdf_paths = [
        DATA_DIR / "faa_phak_pilots_handbook.pdf",
        DATA_DIR / "faa_amt_general_handbook.pdf",
        DATA_DIR / "faa_amt_powerplant_handbook.pdf",
        DATA_DIR / "faa_amt_technician_handbook.pdf",
    ]

    file_ids = []
    for path in pdf_paths:
        if not path.exists():
            print(f"[openai_index] WARN: {path} bulunamadı, atlanıyor.")
            continue
        print(f"[openai_index] Uploading PDF: {path}")
        with open(path, "rb") as f:
            resp = requests.post(
                "https://api.openai.com/v1/files",
                headers={
                    "Authorization": f"Bearer {api_key}",
                },
                data={"purpose": "assistants"},
                files={"file": (path.name, f, "application/pdf")},
                timeout=6000,
            )
        resp.raise_for_status()
        file_ids.append(resp.json()["id"])

    if not file_ids:
        print("[openai_index] Yüklenecek PDF bulunamadı.")
        return []

    # Sonra bu file_id'leri vector store'a ekle
    resp = requests.post(
        f"https://api.openai.com/v1/vector_stores/{vector_store_id}/files",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "OpenAI-Beta": "assistants=v2",
        },
        json={"file_ids": file_ids},
        timeout=6000,
    )
    resp.raise_for_status()

    print(f"[openai_index] {len(file_ids)} dosya vector store'a eklendi.")
    return file_ids


def main():
    vs_id = create_vector_store()
    print("VECTOR_STORE_ID:", vs_id)
    upload_pdfs_to_store(vs_id)
    print(
        "\nLütfen bu VECTOR_STORE_ID değerini .env dosyasına şu şekilde ekle:\n"
        f"OPENAI_VECTOR_STORE_ID={vs_id}\n"
    )


if __name__ == "__main__":
    main()

