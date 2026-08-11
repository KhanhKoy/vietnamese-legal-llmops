import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from rag_core.dataset_reader import iter_documents
from rag_core.config import get_settings

settings = get_settings()
print(f"HF_DATASET_NAME = {settings.hf_dataset_name}")

print("🔍 Bắt đầu iter_documents...")
try:
    for i, doc in enumerate(iter_documents(content_limit=2)):
        print(f"Doc {i}: {doc['document_id']} - {len(doc['text'])} chars")
        break
except Exception as e:
    print(f"❌ LỗI: {e}")
    import traceback
    traceback.print_exc()