# ARCHITECTURE.md

# Bản đồ kiến trúc dự án Chatbot RAG Pháp luật Việt Nam

Tài liệu này mô tả vai trò dự kiến của từng thư mục, từng file Python, và hai luồng chính của hệ thống:

- **Data Pipeline**: tải dữ liệu pháp luật từ HuggingFace, chia nhỏ văn bản, tạo embedding, lưu vào Vector DB.
- **Query Pipeline**: nhận câu hỏi người dùng, truy xuất tài liệu liên quan, tạo prompt, sinh câu trả lời.

Một số file trong repository hiện còn rỗng hoặc chưa hoàn thiện. Vì vậy, tài liệu này vừa phản ánh logic code hiện có, vừa mô tả chức năng phỏng đoán hợp lý theo kiến trúc RAG/LLMOps để làm bản đồ phát triển tiếp.

---

## 1. Tổng quan kiến trúc

Dự án là một hệ thống **Retrieval-Augmented Generation (RAG)** cho hỏi đáp pháp luật Việt Nam.

Nguồn dữ liệu chính:

- HuggingFace dataset: `th1nhng0/vietnamese-legal-documents`

Mục tiêu hệ thống:

1. Tải văn bản pháp luật và metadata.
2. Chia văn bản dài thành các chunk phù hợp.
3. Tạo embedding cho từng chunk bằng SentenceTransformer.
4. Lưu chunk và vector vào Vector DB dạng SQLite.
5. Khi người dùng hỏi, truy xuất các chunk liên quan nhất.
6. Ghép context vào prompt và gọi LLM để sinh câu trả lời.
7. Về sau triển khai API, Chainlit UI, logging, evaluation và deploy AWS.

Kiến trúc logic:

```text
HuggingFace Dataset
        |
        v
dataset_reader.py
        |
        v
chunking.py
        |
        v
embeddings.py
        |
        v
vector_store.py
        |
        v
SQLite Vector Store


User / Chainlit / API
        |
        v
api/*
        |
        v
qa_service.py
        |
        +--> retriever.py --> vector_store.py + embeddings.py
        |
        +--> prompt.py
        |
        +--> generator.py
        |
        v
Answer
```

---

## 2. Cấu trúc thư mục

## `configs/`

Chứa các file cấu hình theo môi trường. Hiện nhiều file có thể đang rỗng, nhưng về mặt kiến trúc nên dùng để tách cấu hình ra khỏi code.

- `dev.yaml`: cấu hình môi trường phát triển local.
- `prod.yaml`: cấu hình môi trường production.
- `aws.yaml`: cấu hình liên quan AWS như S3 bucket, region, IAM role, đường dẫn artifact.
- `logging.yaml`: cấu hình logging, format log, level log, output log.

Gợi ý phát triển:

- Không hard-code endpoint, bucket name, model path trong code.
- Dùng `.env` cho secret hoặc biến môi trường.
- Dùng YAML cho cấu hình không nhạy cảm.

## `deploy/`

Chứa tài nguyên phục vụ đóng gói và triển khai.

- `Dockerfile`: định nghĩa Docker image cho app/API/Chainlit.
- `docker-compose.yml`: chạy local nhiều service nếu cần, ví dụ app, local volume, mock S3.
- `entrypoint.sh`: script khởi động container, ví dụ kiểm tra vector store, tải artifact từ S3, rồi chạy API hoặc Chainlit.

Trong tương lai khi deploy AWS, thư mục này có thể dùng cho:

- ECS/Fargate.
- EC2.
- ECR image build.
- Batch job build index.
- Container chạy Chainlit.

## `scripts/`

Chứa các script chạy thủ công hoặc chạy theo job.

Đây là nhóm file rất quan trọng trong LLMOps vì nó tách các tác vụ vận hành khỏi runtime API.

- `build_index.py`: script khởi tạo Vector DB từ dataset.
- `eval.py`: script chạy đánh giá offline.
- `run_api.py`: script chạy API local.
- `sync_to_s3.py`: script đồng bộ artifact như vector store lên S3.

## `src/`

Chứa source code chính của hệ thống.

Các module được chia theo trách nhiệm:

- `rag_core/`: lõi RAG.
- `api/`: lớp HTTP API.
- `evaluation/`: đánh giá chất lượng retrieval/answer.
- `monitoring/`: logging, feedback, quan sát hệ thống.

## `test/`

Chứa unit test và integration test.

Vai trò dự kiến:

- Kiểm tra chunking có đúng không.
- Kiểm tra retriever trả đúng top-k.
- Kiểm tra pipeline build index hoạt động.
- Kiểm tra API schema và endpoint.

## File gốc

- `main.py`: entrypoint chính của app, thường dùng để chạy API hoặc Chainlit.
- `requirements.txt`: danh sách dependencies Python.
- `.env.sample`: mẫu biến môi trường cho local/dev/prod.
- `README.md`: hướng dẫn cài đặt và sử dụng.
- `ARCHITECTURE.md`: bản đồ kiến trúc dự án, chính là file này.

---

## 3. Giải thích từng file Python

## `scripts/build_index.py`

Đây là script điều khiển **Data Pipeline**.

Vai trò chính:

1. Parse command line arguments như `--metadata-limit`, `--content-limit`.
2. Thêm `src/` vào `sys.path` để import được `rag_core`.
3. Gọi `build_index_pipeline()` trong `src/rag_core/pipeline.py`.
4. In ra số chunk đã lưu vào vector store.

Luồng tư duy:

```text
python scripts/build_index.py
        |
        v
build_index_pipeline()
        |
        v
Tải data -> chunk -> embed -> lưu Vector DB
```

Đây nên được xem là script chạy offline/batch, không phải code chạy mỗi lần user hỏi.

## `scripts/eval.py`

File dự kiến dùng để chạy evaluation offline.

Vai trò phỏng đoán:

- Đọc test cases từ `src/evaluation/test_cases.json`.
- Gọi retriever hoặc QA pipeline.
- Tính các metric như Recall@K, MRR, Precision@K.
- Xuất report để đánh giá chất lượng retrieval.

Trong một dự án RAG, evaluation rất quan trọng vì model trả lời tốt hay không phụ thuộc nhiều vào retrieval.

## `scripts/run_api.py`

File dự kiến dùng để chạy API local.

Vai trò phỏng đoán:

- Import FastAPI app từ `src/api/app.py`.
- Chạy `uvicorn`.
- Cho phép dev chạy nhanh bằng lệnh:

```bash
python scripts/run_api.py
```

Về sau nếu dùng Chainlit làm giao diện chính, file này vẫn hữu ích để expose REST API nội bộ.

## `scripts/sync_to_s3.py`

Script đồng bộ artifact lên AWS S3.

Vai trò hiện tại:

- Nhận `--bucket`, `--prefix`, `--source-dir`.
- Duyệt các file trong thư mục vector store.
- Upload từng file lên S3.

Vai trò LLMOps:

- Sau khi build index local hoặc bằng job, upload `models/vector_store/` lên S3.
- Khi deploy production, container có thể tải lại vector store từ S3 thay vì build lại từ đầu.

Gợi ý mở rộng:

- Thêm chế độ download từ S3.
- Thêm checksum/version.
- Thêm prefix theo ngày hoặc version dataset.

---

## `src/rag_core/config.py`

File cấu hình trung tâm cho RAG core.

Vai trò chính:

- Load `.env` bằng `python-dotenv`.
- Định nghĩa `PROJECT_ROOT`, `SRC_ROOT`, `MODEL_DIR`, `VECTOR_STORE_DIR`.
- Định nghĩa dataclass `Settings`.
- Cung cấp `get_settings()` có cache.

Các cấu hình quan trọng:

- `HF_DATASET_NAME`: tên dataset HuggingFace.
- `HF_METADATA_CONFIG`: config metadata của dataset.
- `HF_CONTENT_PARQUET_URL`: URL file parquet chứa content.
- `CHUNK_SIZE_CHARS`: kích thước chunk.
- `CHUNK_OVERLAP_CHARS`: overlap giữa các chunk.
- `EMBEDDING_MODEL_NAME`: model embedding.
- `EMBEDDING_BATCH_SIZE`: batch size khi embed.
- `TOP_K`: số chunk truy xuất.
- `VECTOR_STORE_DIR`: nơi lưu Vector DB.
- `DEVICE`: CPU/GPU/auto.

Đây là nơi nên tập trung cấu hình runtime thay vì rải rác trong code.

## `src/rag_core/dataset_reader.py`

File chịu trách nhiệm đọc dữ liệu pháp luật.

Vai trò chính:

- Stream metadata từ HuggingFace dataset.
- Đọc content từ parquet bằng `fsspec` và `pyarrow`.
- Join metadata và content theo `id`.
- Trả ra object `LegalDocument`.

Các thành phần chính:

- `LegalDocument`: dataclass gồm `document_id`, `text`, `metadata`.
- `iter_metadata_rows()`: stream metadata rows.
- `_build_metadata_db()`: đưa metadata vào SQLite tạm để tránh load toàn bộ vào RAM.
- `iter_content_rows()`: đọc content parquet theo batch.
- `iter_documents()`: join metadata + content và yield từng `LegalDocument`.
- `load_documents()`: load toàn bộ documents vào list.
- `documents_to_dicts()`: chuyển dataclass sang dict.

Điểm thiết kế tốt:

- Dùng streaming để tránh OOM.
- Dùng SQLite tạm cho metadata lookup.
- Phù hợp với dataset lớn.

## `src/rag_core/chunking.py`

File chia văn bản pháp luật thành chunk.

Vai trò chính:

- Làm sạch text.
- Ưu tiên tách theo heading pháp luật như Chương, Điều, Mục, Khoản.
- Nếu không tách được theo heading, fallback sang sliding window theo số ký tự.
- Trả về danh sách `Chunk`.

Các thành phần chính:

- `Chunk`: dataclass biểu diễn một chunk.
- `_clean_text()`: chuẩn hóa xuống dòng, khoảng trắng.
- `_window_chunks()`: chia văn bản theo cửa sổ ký tự có overlap.
- `split_text()`: hàm tách text chính.
- `chunk_document()`: chia một document thành nhiều chunk.
- `chunk_documents()`: chia nhiều document.

Lưu ý kỹ thuật:

- Với văn bản pháp luật, chunk theo điều/khoản thường tốt hơn chunk theo độ dài thô.
- Chunk quá dài làm prompt tốn token.
- Chunk quá ngắn làm mất ngữ cảnh.
- Overlap giúp giảm mất thông tin ở ranh giới chunk.

## `src/rag_core/embeddings.py`

File tạo vector embedding.

Vai trò chính:

- Load SentenceTransformer model.
- Encode danh sách text thành vector.
- Encode query của người dùng thành vector.
- Normalize embedding để dot product gần tương đương cosine similarity.

Các thành phần chính:

- `EmbeddingService`: service đóng gói embedding model.
- `embed_texts()`: tạo embedding cho nhiều chunk.
- `embed_query()`: tạo embedding cho câu hỏi.
- `dimension`: lấy số chiều vector của model.

Trong RAG, embedding model quyết định chất lượng truy xuất. Với tiếng Việt pháp luật, nên test nhiều model embedding khác nhau.

## `src/rag_core/vector_store.py`

File lưu và tìm kiếm vector.

Vai trò chính:

- Tạo SQLite database lưu chunk + metadata + embedding.
- Lưu embedding dạng BLOB.
- Search bằng similarity giữa query vector và chunk vector.

Các thành phần chính:

- `VectorStore`: lớp quản lý vector database.
- `reset()`: xóa và tạo lại schema.
- `add()`: thêm chunks và embeddings.
- `commit()`: commit transaction định kỳ.
- `save()`: lưu metadata của store.
- `load()`: load vector store đã build.
- `search_by_embedding()`: tìm top-k chunk gần nhất theo vector.
- `search()`: embed query rồi search.

Hiện tại vector store dùng SQLite và brute-force search theo batch. Cách này phù hợp demo/đồ án/quy mô nhỏ đến vừa. Nếu dữ liệu lớn hơn, có thể cân nhắc FAISS, Qdrant, OpenSearch Vector Engine, hoặc pgvector.

## `src/rag_core/pipeline.py`

File orchestration của RAG core.

Vai trò chính:

- Điều phối toàn bộ Data Pipeline khi build index.
- Cung cấp helper cho Query Pipeline.

Các hàm chính:

- `build_index_pipeline()`: pipeline build vector index.
- `ask_pipeline()`: gọi `QAService` để hỏi đáp.

Trong `build_index_pipeline()`:

1. Tạo hoặc nhận `VectorStore`.
2. Reset vector store.
3. Tạo `EmbeddingService`.
4. Gọi `iter_documents()` để stream document.
5. Gọi `split_text()` để chunk từng document.
6. Buffer chunks và texts.
7. Khi đủ batch, gọi `embed_texts()`.
8. Lưu vào vector store bằng `store.add()`.
9. Commit định kỳ.
10. Save vector store.

Đây là file nối các module nhỏ thành một workflow hoàn chỉnh.

## `src/rag_core/retriever.py`

File truy xuất tài liệu liên quan khi người dùng hỏi.

Vai trò chính:

- Đảm bảo vector store đã được load.
- Embed câu hỏi.
- Search top-k chunk liên quan.
- Format context cho prompt hoặc debug.

Các thành phần chính:

- `Retriever`: service truy xuất.
- `_ensure_loaded()`: load vector store nếu chưa có chunk.
- `retrieve()`: trả về top-k results.
- `format_context()`: format kết quả retrieval thành text context.
- `retrieve_with_context()`: trả cả question, results, context.

Retriever là phần rất quan trọng của RAG. Nếu retrieval sai, LLM sẽ có context sai hoặc thiếu.

## `src/rag_core/prompt.py`

File xây dựng prompt cho LLM.

Vai trò chính:

- Định nghĩa system prompt.
- Chuyển retrieved chunks thành context block.
- Ghép question + context + instruction thành prompt hoàn chỉnh.

Các thành phần chính:

- `SYSTEM_PROMPT`: hướng dẫn LLM trả lời dựa trên context, không bịa luật.
- `build_context_block()`: format danh sách chunk thành context.
- `build_prompt()`: tạo prompt cuối cùng.

Trong chatbot pháp luật, prompt cần nhấn mạnh:

- Chỉ trả lời dựa trên context.
- Không bịa điều luật/khoản luật.
- Nếu thiếu căn cứ thì nói rõ.
- Nêu disclaimer không phải tư vấn pháp lý chính thức.

## `src/rag_core/generator.py`

File gọi LLM để sinh câu trả lời.

Vai trò chính:

- Load text-generation pipeline từ HuggingFace Transformers.
- Nhận prompt.
- Sinh answer.

Các thành phần chính:

- `GeneratorService`: service đóng gói LLM.
- `generate()`: gọi model sinh text.

Hiện tại model được lấy từ biến môi trường `LLM_MODEL_NAME`. Nếu chưa cấu hình model, service sẽ báo lỗi.

Gợi ý mở rộng:

- Hỗ trợ OpenAI, AWS Bedrock, hoặc vLLM.
- Tách interface `BaseGenerator`.
- Thêm timeout, retry, logging token usage.

## `src/rag_core/qa_service.py`

File điều phối luồng hỏi đáp.

Vai trò chính:

- Nhận câu hỏi.
- Gọi retriever lấy context.
- Gọi prompt builder.
- Gọi generator sinh câu trả lời.
- Trả về answer, context, prompt, results.

Luồng trong `QAService.ask()`:

```text
question
   |
   v
Retriever.retrieve_with_context()
   |
   v
build_prompt()
   |
   v
GeneratorService.generate()
   |
   v
answer + retrieved results
```

Đây là service trung tâm của Query Pipeline.

---

## `src/api/app.py`

File dự kiến tạo FastAPI application.

Vai trò phỏng đoán:

- Khởi tạo `FastAPI()`.
- Include router từ `routes.py`.
- Cấu hình middleware nếu cần.
- Cấu hình startup/shutdown event.

Ví dụ chức năng tương lai:

- Health check endpoint.
- Load QA service singleton.
- CORS cho frontend/Chainlit nếu cần.

## `src/api/routes.py`

File dự kiến định nghĩa HTTP routes.

Vai trò phỏng đoán:

- Endpoint `/ask` nhận câu hỏi.
- Gọi `QAService.ask()`.
- Trả về answer và retrieved chunks.

Ví dụ route logic:

```text
POST /ask
   |
   v
AskRequest
   |
   v
QAService.ask()
   |
   v
AskResponse
```

## `src/api/schemas.py`

File dự kiến định nghĩa Pydantic schemas.

Vai trò phỏng đoán:

- `AskRequest`: request body gồm `question`, `top_k`.
- `AskResponse`: response gồm `answer`, `sources`, `context`, metadata.
- `RetrievedChunk`: schema cho từng chunk retrieved.

Pydantic giúp API rõ contract, dễ test, dễ sinh OpenAPI docs.

---

## `src/evaluation/metrics.py`

File dự kiến định nghĩa metric đánh giá.

Vai trò phỏng đoán:

- `recall_at_k`.
- `precision_at_k`.
- `mrr`.
- Có thể thêm faithfulness/answer relevance nếu dùng LLM judge.

Với RAG pháp luật, nên bắt đầu từ retrieval metrics trước vì dễ kiểm chứng hơn answer generation.

## `src/evaluation/eval_runner.py`

File dự kiến chạy evaluation logic.

Vai trò phỏng đoán:

- Load test cases.
- Gọi retriever hoặc QA service.
- Tính metric.
- In hoặc lưu report.

## `src/evaluation/test_cases.json`

File dữ liệu test case cho evaluation.

Mỗi test case nên có:

- `question`: câu hỏi.
- `expected_document_ids`: danh sách document nên retrieve.
- `expected_keywords`: từ khóa nên xuất hiện.
- `notes`: ghi chú nghiệp vụ.

---

## `src/monitoring/logging_config.py`

File dự kiến cấu hình logging.

Vai trò phỏng đoán:

- Cấu hình log format.
- Cấu hình log level.
- Cấu hình output stdout/file.
- Dùng cho API, build index, evaluation.

Trong AWS, log nên đi ra stdout để CloudWatch Logs thu thập.

## `src/monitoring/feedback_store.py`

File dự kiến lưu feedback người dùng.

Vai trò phỏng đoán:

- Lưu câu hỏi, câu trả lời, source chunks.
- Lưu user rating như thumbs up/down.
- Lưu comment sửa sai.

Feedback này dùng để:

- Cải thiện prompt.
- Cải thiện retrieval.
- Xây bộ test cases mới.
- Làm dữ liệu đánh giá cho đồ án.

## `src/monitoring/__init__.py`

File đánh dấu `monitoring` là Python package.

---

## `main.py`

Entry point cấp cao của project.

Vai trò phỏng đoán:

- Chạy API bằng uvicorn.
- Hoặc về sau chạy Chainlit app.
- Có thể đọc biến môi trường để chọn mode:
  - `api`
  - `chainlit`
  - `worker`

Ví dụ tư duy tương lai:

```text
python main.py
        |
        v
Start API or Chainlit runtime
```

---

## 4. Data Pipeline: build Vector DB

Data Pipeline được điều khiển bởi:

```text
scripts/build_index.py
```

Luồng chi tiết:

```text
scripts/build_index.py
        |
        v
rag_core.pipeline.build_index_pipeline()
        |
        v
dataset_reader.iter_documents()
        |
        v
chunking.split_text()
        |
        v
embeddings.EmbeddingService.embed_texts()
        |
        v
vector_store.VectorStore.add()
        |
        v
vector_store.VectorStore.save()
        |
        v
models/vector_store/
```

## Bước 1: `build_index.py`

Người dùng chạy:

```bash
python scripts/build_index.py
```

Hoặc chạy giới hạn dữ liệu để test nhanh:

```bash
python scripts/build_index.py --metadata-limit 1000 --content-limit 1000
```

Script gọi:

```python
build_index_pipeline(
    metadata_limit=args.metadata_limit,
    content_limit=args.content_limit,
)
```

## Bước 2: `dataset_reader.py`

`iter_documents()` thực hiện:

1. Stream metadata từ HuggingFace.
2. Ghi metadata vào SQLite tạm.
3. Đọc content parquet theo batch.
4. Join content với metadata theo `id`.
5. Yield từng `LegalDocument`.

Output dạng logic:

```python
LegalDocument(
    document_id="...",
    text="...",
    metadata={...}
)
```

## Bước 3: `chunking.py`

Với mỗi document:

```python
chunk_texts = split_text(document.text)
```

Mục tiêu:

- Tách theo cấu trúc pháp luật nếu nhận diện được heading.
- Nếu không, chia theo chunk size và overlap.

Output:

```python
[
    "chunk text 1",
    "chunk text 2",
    ...
]
```

## Bước 4: `embeddings.py`

Pipeline gom nhiều chunk vào buffer.

Khi đủ batch:

```python
embeddings = embedder.embed_texts(text_buffer)
```

Output là ma trận vector:

```text
num_chunks x embedding_dimension
```

Ví dụ:

```text
32 x 384
```

## Bước 5: `vector_store.py`

Pipeline gọi:

```python
store.add(chunk_buffer, embeddings)
```

Vector store lưu:

- `chunk_id`
- `document_id`
- `chunk_index`
- `text`
- `metadata_json`
- `embedding`

Cuối pipeline:

```python
store.save()
```

Kết quả được lưu vào:

```text
models/vector_store/vector_store.sqlite3
models/vector_store/store_meta.json
```

## Ghi chú LLMOps cho Data Pipeline

Trong production/AWS, Data Pipeline nên được chạy như batch job, không chạy trong request API.

Gợi ý AWS:

- Chạy build index bằng ECS Task, AWS Batch, hoặc EC2 job.
- Lưu artifact vector store lên S3.
- API container khi start sẽ tải vector store từ S3.
- Gắn version cho vector store theo dataset version, ngày build, model embedding.

---

## 5. Query Pipeline: người dùng hỏi

Luồng truy vấn dự kiến:

```text
User / Chainlit / HTTP Client
        |
        v
src/api/routes.py
        |
        v
QAService.ask()
        |
        +--> Retriever.retrieve()
        |       |
        |       +--> EmbeddingService.embed_query()
        |       |
        |       +--> VectorStore.search_by_embedding()
        |
        +--> build_prompt()
        |
        +--> GeneratorService.generate()
        |
        v
Answer + Sources
```

## Bước 1: API nhận request

Với FastAPI, request dự kiến:

```http
POST /ask
Content-Type: application/json

{
  "question": "Người sử dụng đất có quyền gì?",
  "top_k": 5
}
```

`routes.py` sẽ validate request bằng schema trong `schemas.py`, sau đó gọi `QAService`.

## Bước 2: `qa_service.py`

`QAService.ask()` là điểm điều phối chính:

```python
retrieval = self.retriever.retrieve_with_context(question, top_k=top_k)
prompt = build_prompt(question, retrieval["results"])
answer = self.generator.generate(prompt)
```

Output gồm:

- `question`
- `answer`
- `top_k`
- `results`
- `context`
- `prompt`

## Bước 3: `retriever.py`

Retriever làm ba việc:

1. Load vector store nếu chưa load.
2. Embed query.
3. Search top-k chunk liên quan.

Luồng:

```text
question
   |
   v
EmbeddingService.embed_query()
   |
   v
VectorStore.search_by_embedding()
   |
   v
top-k chunks
```

## Bước 4: `prompt.py`

Prompt builder nhận:

- Câu hỏi người dùng.
- Danh sách chunk retrieve được.

Sau đó tạo prompt gồm:

- System instruction.
- Context pháp luật.
- Câu hỏi.
- Yêu cầu trả lời.

Mục tiêu là ép LLM trả lời dựa trên nguồn, giảm hallucination.

## Bước 5: `generator.py`

Generator nhận prompt và gọi LLM.

Hiện tại dùng HuggingFace Transformers pipeline:

```python
pipeline(
    task="text-generation",
    model=self.model_name,
    tokenizer=self.model_name,
)
```

Output là câu trả lời cuối cùng.

## Bước 6: API trả response

Response dự kiến:

```json
{
  "answer": "...",
  "retrieved_chunks": [
    {
      "chunk_id": "...",
      "document_id": "...",
      "score": 0.82,
      "text": "...",
      "metadata": {}
    }
  ]
}
```

Với Chainlit, thay vì trả JSON cho người dùng, app có thể hiển thị:

- Answer.
- Danh sách nguồn trích dẫn.
- Score hoặc metadata nếu cần debug.

---

## 6. Vai trò của Chainlit trong tương lai

Chainlit nên được xem là lớp giao diện, không thay thế RAG core.

Kiến trúc nên giữ:

```text
Chainlit UI
    |
    v
QAService
    |
    v
RAG Core
```

Không nên viết logic retrieval trực tiếp trong file Chainlit. Chainlit chỉ nên:

- Nhận message người dùng.
- Gọi `QAService.ask()`.
- Render answer.
- Render sources.
- Thu feedback nếu có.

Cách này giúp cùng một RAG core có thể phục vụ:

- FastAPI.
- Chainlit.
- CLI.
- Evaluation scripts.
- Batch test.

---

## 7. Gợi ý thứ tự hoàn thiện dự án

Thứ tự nên làm để dự án ổn định:

1. Sửa encoding tiếng Việt trong các file source và README nếu bị lỗi.
2. Hoàn thiện `chunking.py` và test chunking.
3. Chạy `scripts/build_index.py` với limit nhỏ để validate pipeline.
4. Hoàn thiện `api/app.py`, `api/routes.py`, `api/schemas.py`.
5. Viết test cho API và Retriever.
6. Hoàn thiện `scripts/sync_to_s3.py` cả upload và download.
7. Thêm Chainlit UI gọi `QAService`.
8. Thêm logging và feedback store.
9. Thêm evaluation cases và metrics.
10. Đóng gói Docker.
11. Thiết kế deploy AWS.

---

## 8. Nguyên tắc thiết kế nên giữ

- RAG core không phụ thuộc API hoặc Chainlit.
- API/Chainlit chỉ gọi service, không chứa logic retrieval phức tạp.
- Build index là batch job, không chạy trong request.
- Vector store là artifact có version.
- Prompt phải luôn yêu cầu trả lời dựa trên context.
- Cần logging cho câu hỏi, retrieved chunks, latency, lỗi model.
- Cần evaluation để biết thay đổi chunking/embedding có cải thiện thật không.
- Với pháp luật, luôn có disclaimer: câu trả lời không phải tư vấn pháp lý chính thức.

