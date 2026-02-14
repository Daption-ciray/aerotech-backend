"""
One-off script to build a chunk + summary index for FAA / AMT PDFs.

Bu script, embedding üretmek yerine:
- PDF'leri chunk'lara böler
- Her chunk için LLM ile 1-2 cümlelik teknik özet çıkarır
- Sonucu app/data/chunk_index.json dosyasına yazar

Kullanım:

    cd /Users/daption-ciray/Desktop/Project/THY
    source .venv/bin/activate
    python -m app.build_chunk_index
"""

from pathlib import Path
from typing import List
import time
import sys

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from .config import settings
from .chunk_index import ChunkRecord, save_chunk_index, DATA_DIR
from .setup import VECTOR_DIR


def main():
    pdf_files: List[str] = [
        "faa_phak_pilots_handbook.pdf",
        "faa_amt_general_handbook.pdf",
        "faa_amt_powerplant_handbook.pdf",
        "faa_amt_technician_handbook.pdf",
    ]

    print(f"[build_chunk_index] DATA_DIR = {DATA_DIR}")

    docs = []
    for name in pdf_files:
        pdf_path = DATA_DIR / name
        if not pdf_path.exists():
            print(f"[build_chunk_index] WARN: {pdf_path} bulunamadı, atlanıyor.")
            continue
        print(f"[build_chunk_index] Loading PDF: {pdf_path}")
        loader = PyPDFLoader(str(pdf_path))
        file_docs = loader.load()
        docs.extend(file_docs)

    if not docs:
        raise FileNotFoundError(
            f"Hiçbir FAA PDF'i bulunamadı. Beklenen klasör: {DATA_DIR}"
        )

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_documents(docs)
    print(f"[build_chunk_index] Toplam chunk sayısı: {len(chunks)}")

    start_time = time.time()
    llm = ChatOpenAI(model=settings.LLM_MODEL, temperature=0)

    records: List[ChunkRecord] = []
    for idx, ch in enumerate(chunks):
        chunk_id = f"chunk-{idx:05d}"
        source = ch.metadata.get("source", "") or ch.metadata.get("file_path", "")
        page = ch.metadata.get("page")

        prompt = [
            {
                "role": "system",
                "content": (
                    "Aşağıdaki metin FAA/AMT havacılık dokümanından bir parçadır. "
                    "Bu parçanın ne anlattığını 1-2 cümlelik teknik bir özet olarak yaz. "
                    "Primary/secondary flight control surfaces, bakım prosedürleri, "
                    "emniyet uyarıları gibi kavramları mümkün olduğunca koru."
                ),
            },
            {
                "role": "user",
                "content": ch.page_content,
            },
        ]

        resp = llm.invoke(prompt)
        summary = resp.content.strip()

        records.append(
            ChunkRecord(
                id=chunk_id,
                source=str(source),
                page=int(page) if isinstance(page, int) else None,
                summary=summary,
                text=ch.page_content,
            )
        )

        if idx % 50 == 0:
            elapsed = time.time() - start_time
            avg_per_chunk = elapsed / (idx + 1)
            remaining = (len(chunks) - idx - 1) * avg_per_chunk
            msg = (
                f"[build_chunk_index] Chunk {idx}/{len(chunks)} işlendi… "
                f"tahmini kalan: {remaining/60:.1f} dk"
            )
            print(msg, flush=True, file=sys.stderr)

    print(f"[build_chunk_index] Toplam {len(records)} chunk için özet üretildi. Kaydediliyor…")
    save_chunk_index(records)

    # Ayrıca aynı chunk'ları embedleyip Chroma store'a yaz
    print(f"[build_chunk_index] Chroma store yazılıyor: {VECTOR_DIR}")
    embeddings = OpenAIEmbeddings(openai_api_key=settings.OPENAI_API_KEY)
    VECTOR_DIR.mkdir(parents=True, exist_ok=True)

    docs_for_embed = [
      Document(
          page_content=rec.text,
          metadata={
              "id": rec.id,
              "source": rec.source,
              "page": rec.page,
          },
      )
      for rec in records
    ]

    Chroma.from_documents(
        documents=docs_for_embed,
        embedding=embeddings,
        persist_directory=str(VECTOR_DIR),
    )

    print("[build_chunk_index] Chunk index + embeddings tamamlandı.")


if __name__ == "__main__":
    main()

