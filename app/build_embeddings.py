"""
One-off script to build vector embeddings for FAA / AMT PDFs.

Kullanım:

    cd /Users/daption-ciray/Desktop/Project/THY
    source .venv/bin/activate
    python -m app.build_embeddings

Bu script çalıştıktan sonra, FastAPI uygulaması startup sırasında
embeddings üretmek zorunda kalmaz; sadece hazır Chroma store'dan okur.
"""

from pathlib import Path
from typing import List

from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import settings
from .setup import DATA_DIR, VECTOR_DIR


def main():
    pdf_files: List[str] = [
        "faa_phak_pilots_handbook.pdf",
        "faa_amt_general_handbook.pdf",
        "faa_amt_powerplant_handbook.pdf",
        "faa_amt_technician_handbook.pdf",
    ]

    print(f"[build_embeddings] DATA_DIR = {DATA_DIR}")
    print(f"[build_embeddings] VECTOR_DIR = {VECTOR_DIR}")

    docs = []
    for name in pdf_files:
        pdf_path = DATA_DIR / name
        if not pdf_path.exists():
            print(f"[build_embeddings] WARN: {pdf_path} bulunamadı, atlanıyor.")
            continue
        print(f"[build_embeddings] Loading PDF: {pdf_path}")
        loader = PyPDFLoader(str(pdf_path))
        file_docs = loader.load()
        # Demo için çok büyük dosyaları kısıtlamak istersen buradan slice alabilirsin.
        docs.extend(file_docs)

    if not docs:
        raise FileNotFoundError(
            f"Hiçbir FAA PDF'i bulunamadı. Beklenen klasör: {DATA_DIR}"
        )

    print(f"[build_embeddings] Toplam doküman sayısı: {len(docs)}")

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    split_docs = splitter.split_documents(docs)
    print(f"[build_embeddings] Split doküman sayısı: {len(split_docs)}")

    embeddings = OpenAIEmbeddings(openai_api_key=settings.OPENAI_API_KEY)

    VECTOR_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[build_embeddings] Chroma store yazılıyor: {VECTOR_DIR}")

    Chroma.from_documents(
        documents=split_docs,
        embedding=embeddings,
        persist_directory=str(VECTOR_DIR),
    )

    print("[build_embeddings] Tamamlandı.")


if __name__ == "__main__":
    main()

