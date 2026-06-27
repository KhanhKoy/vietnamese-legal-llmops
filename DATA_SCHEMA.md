# DATA_SCHEMA.md

# Schema dữ liệu HuggingFace cho RAG Pháp luật Việt Nam

Tài liệu này mô tả cấu trúc dữ liệu của dataset HuggingFace:

```text
th1nhng0/vietnamese-legal-documents
```

Dataset này được dùng làm nguồn dữ liệu chính cho hệ thống Chatbot RAG Pháp luật Việt Nam. Về mặt xử lý dữ liệu, dataset gồm ba nhóm thông tin chính:

1. `metadata`: thông tin mô tả văn bản pháp luật.
2. `content`: nội dung toàn văn của văn bản.
3. `relationships`: quan hệ giữa các văn bản pháp luật.

Trong pipeline RAG, không nên xử lý từng config một cách tách rời. Cần merge `metadata` và `content` theo cột `id` để tạo ra document hoàn chỉnh trước khi chunking và embedding.

---

## 1. Tổng quan dataset

## HuggingFace dataset

```text
Dataset name: th1nhng0/vietnamese-legal-documents
```

## Các config chính

| Config | Vai trò | Ghi chú |
|---|---|---|
| `metadata` | Chứa metadata của văn bản pháp luật | Khoảng 153k dòng |
| `content` | Chứa nội dung toàn văn | Nội dung nằm ở dạng HTML thô |
| `relationships` | Chứa quan hệ giữa các văn bản | Dùng để hiểu văn bản nào sửa đổi, bổ sung, thay thế văn bản nào |

## Khóa chính để liên kết dữ liệu

Cột quan trọng nhất là:

```text
id
```

Ý nghĩa:

- Trong `metadata`, `id` là định danh của văn bản pháp luật.
- Trong `content`, `id` là định danh dùng để join với metadata.
- Trong `relationships`, `doc_id` và `other_doc_id` tham chiếu đến các `id` của văn bản.

---

## 2. Config `metadata`

## Mục đích

`metadata` chứa thông tin mô tả, phân loại và trạng thái hiệu lực của từng văn bản pháp luật.

Đây là phần rất quan trọng cho RAG vì metadata giúp:

- Hiển thị nguồn trích dẫn rõ ràng.
- Lọc văn bản theo hiệu lực.
- Lọc theo loại văn bản.
- Lọc theo cơ quan ban hành.
- Tăng chất lượng câu trả lời bằng thông tin ngữ cảnh.

## Số lượng dòng

```text
Khoảng 153k dòng
```

## Các cột

| Cột | Ý nghĩa | Vai trò trong RAG |
|---|---|---|
| `id` | Định danh duy nhất của văn bản | Khóa join với `content.id`; dùng làm `document_id` |
| `title` | Tiêu đề văn bản | Dùng hiển thị nguồn và citation |
| `so_ky_hieu` | Số ký hiệu văn bản | Dùng trích dẫn, ví dụ số luật/nghị định/thông tư |
| `ngay_ban_hanh` | Ngày ban hành | Dùng lọc theo thời gian hoặc hiển thị nguồn |
| `loai_van_ban` | Loại văn bản | Ví dụ Luật, Nghị định, Thông tư, Quyết định |
| `co_quan_ban_hanh` | Cơ quan ban hành | Ví dụ Quốc hội, Chính phủ, Bộ, UBND |
| `tinh_trang_hieu_luc` | Tình trạng hiệu lực | Dùng để lọc bỏ văn bản hết hiệu lực nếu cần |

## Ví dụ record logic

```json
{
  "id": "doc_123",
  "title": "Luật Đất đai ...",
  "so_ky_hieu": "...",
  "ngay_ban_hanh": "YYYY-MM-DD",
  "loai_van_ban": "Luật",
  "co_quan_ban_hanh": "Quốc hội",
  "tinh_trang_hieu_luc": "Còn hiệu lực"
}
```

## Gợi ý sử dụng metadata trong RAG

Nên giữ metadata đi kèm mỗi chunk sau khi chunking:

```python
chunk = {
    "chunk_id": "...",
    "document_id": metadata["id"],
    "text": "...",
    "metadata": {
        "title": "...",
        "so_ky_hieu": "...",
        "ngay_ban_hanh": "...",
        "loai_van_ban": "...",
        "co_quan_ban_hanh": "...",
        "tinh_trang_hieu_luc": "..."
    }
}
```

Lý do:

- Khi trả lời, chatbot có thể ghi nguồn rõ ràng.
- Khi debug retrieval, có thể biết chunk đến từ văn bản nào.
- Khi lọc dữ liệu, có thể loại bỏ văn bản hết hiệu lực trước khi embedding.

---

## 3. Config `content`

## Mục đích

`content` chứa nội dung toàn văn của văn bản pháp luật.

Đây là phần được dùng để:

- Parse thành plain text.
- Chunking.
- Tạo embedding.
- Lưu vào vector store.
- Làm context cho LLM.

## Các cột

| Cột | Ý nghĩa | Vai trò trong RAG |
|---|---|---|
| `id` | Định danh văn bản | Khóa join với `metadata.id` |
| `content_html` | Nội dung toàn văn dạng HTML thô | Phải parse thành plain text trước khi chunking |

## Lưu ý quan trọng về `content_html`

Cột `content_html` không phải plain text. Đây là HTML thô.

Vì vậy, không được đưa trực tiếp `content_html` vào:

- `chunking.py`
- embedding model
- vector store
- prompt LLM

Nếu đưa HTML thô vào pipeline, hệ thống có thể gặp các vấn đề:

- Chunk chứa tag HTML như `<p>`, `<div>`, `<table>`, `<br>`.
- Embedding bị nhiễu bởi markup.
- Retrieval kém chính xác.
- Prompt dài hơn cần thiết.
- Câu trả lời có thể chứa ký tự HTML không mong muốn.

## Cách xử lý đúng

Phải parse HTML sang plain text trước:

```python
from bs4 import BeautifulSoup

def html_to_text(content_html: str) -> str:
    soup = BeautifulSoup(content_html or "", "html.parser")

    for tag in soup(["script", "style"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)
```

Sau đó mới đưa text vào chunking:

```python
plain_text = html_to_text(row["content_html"])
chunks = split_text(plain_text)
```

## Output mong muốn sau khi parse

```python
{
    "document_id": "doc_123",
    "text": "Plain text của văn bản pháp luật...",
    "metadata": {
        "title": "...",
        "so_ky_hieu": "...",
        "tinh_trang_hieu_luc": "..."
    }
}
```

---

## 4. Config `relationships`

## Mục đích

`relationships` chứa các liên kết pháp lý giữa các văn bản.

Ví dụ:

- Văn bản A sửa đổi văn bản B.
- Văn bản A bổ sung văn bản B.
- Văn bản A thay thế văn bản B.
- Văn bản A bị thay thế bởi văn bản B.

Thông tin này chưa bắt buộc cho pipeline RAG cơ bản, nhưng rất có giá trị cho phiên bản nâng cao.

## Các cột

| Cột | Ý nghĩa | Vai trò |
|---|---|---|
| `doc_id` | ID của văn bản chính | Tham chiếu đến `metadata.id` |
| `other_doc_id` | ID của văn bản liên quan | Tham chiếu đến `metadata.id` |
| `relationship` | Loại quan hệ giữa hai văn bản | Sửa đổi, bổ sung, thay thế, liên quan |

## Ví dụ record logic

```json
{
  "doc_id": "doc_123",
  "other_doc_id": "doc_456",
  "relationship": "thay thế"
}
```

## Vai trò trong RAG nâng cao

Có thể dùng `relationships` để:

- Cảnh báo văn bản đã bị thay thế.
- Gợi ý văn bản mới hơn có liên quan.
- Mở rộng retrieval sang các văn bản liên quan.
- Xây dựng legal knowledge graph.
- Ưu tiên văn bản còn hiệu lực trong câu trả lời.

## Cách lưu quan hệ

Trong giai đoạn đầu, có thể chưa cần đưa relationship vào chunk text. Thay vào đó, nên lưu thành bảng riêng hoặc metadata bổ sung.

Ví dụ:

```text
relationships table:

doc_id      other_doc_id      relationship
------      ------------      ------------
doc_123     doc_456           thay thế
doc_123     doc_789           sửa đổi
```

Ở giai đoạn retrieval nâng cao, sau khi tìm được chunk thuộc `doc_id`, hệ thống có thể lookup thêm các văn bản liên quan.

---

## 5. Mô hình document chuẩn cho pipeline RAG

Sau khi join `metadata` và `content`, mỗi document nên có dạng chuẩn:

```python
{
    "document_id": "...",
    "text": "...",
    "metadata": {
        "title": "...",
        "so_ky_hieu": "...",
        "ngay_ban_hanh": "...",
        "loai_van_ban": "...",
        "co_quan_ban_hanh": "...",
        "tinh_trang_hieu_luc": "..."
    }
}
```

Trong đó:

- `document_id` lấy từ `metadata.id` hoặc `content.id`.
- `text` là plain text đã parse từ `content_html`.
- `metadata` giữ lại các trường mô tả từ config `metadata`.

Không nên lưu HTML thô vào `text`.

Nếu muốn debug hoặc tái xử lý, có thể lưu HTML thô riêng ở storage khác, nhưng không nên đưa vào vector embedding.

---

## 6. Quy trình xử lý dữ liệu đề xuất

## Bước 1: Load metadata

Load config:

```text
metadata
```

Giữ các cột:

```text
id
title
so_ky_hieu
ngay_ban_hanh
loai_van_ban
co_quan_ban_hanh
tinh_trang_hieu_luc
```

## Bước 2: Lọc hiệu lực nếu cần

Có thể dùng cột:

```text
tinh_trang_hieu_luc
```

để loại bỏ các văn bản đã hết hiệu lực.

Ví dụ logic:

```python
if metadata["tinh_trang_hieu_luc"] == "Hết hiệu lực":
    skip_document()
```

Lưu ý:

- Không phải mọi bài toán đều nên bỏ văn bản hết hiệu lực.
- Nếu chatbot cần trả lời lịch sử pháp lý, nên giữ lại.
- Nếu chatbot chỉ phục vụ tra cứu luật hiện hành, nên lọc bỏ hoặc giảm ưu tiên văn bản hết hiệu lực.

## Bước 3: Load content

Load config:

```text
content
```

Giữ các cột:

```text
id
content_html
```

## Bước 4: Join metadata và content

Join theo:

```text
metadata.id = content.id
```

Kiểu join khuyến nghị:

- `inner join`: chỉ lấy văn bản có cả metadata và content.
- `left join`: dùng khi muốn thống kê văn bản thiếu content.

Với build index RAG, nên dùng `inner join`.

Ví dụ:

```python
merged = metadata.merge(content, on="id", how="inner")
```

Nếu xử lý streaming, có thể:

1. Đưa metadata vào SQLite tạm.
2. Stream content.
3. Lookup metadata theo `id`.
4. Yield từng document đã merge.

## Bước 5: Parse HTML sang plain text

Với mỗi dòng sau join:

```python
plain_text = html_to_text(row["content_html"])
```

Thư viện khuyến nghị:

```text
beautifulsoup4
```

Cài đặt:

```bash
pip install beautifulsoup4
```

Hoặc thêm vào:

```text
requirements.txt
```

## Bước 6: Chunking

Sau khi có plain text:

```python
chunks = split_text(plain_text)
```

Mỗi chunk cần giữ metadata:

```python
{
    "chunk_id": f"{document_id}::chunk_{idx}",
    "document_id": document_id,
    "text": chunk_text,
    "chunk_index": idx,
    "metadata": metadata
}
```

## Bước 7: Embedding

Encode chunk text:

```python
embeddings = embedder.embed_texts([chunk["text"] for chunk in chunks])
```

Không encode:

- HTML thô.
- Metadata JSON nguyên khối.
- Text chưa clean.

## Bước 8: Lưu Vector DB

Lưu vào vector store:

```python
store.add(chunks, embeddings)
store.save()
```

Vector store cần giữ cả:

- Vector embedding.
- Text chunk.
- Metadata dùng để cite nguồn.

---

## 7. Gợi ý dùng `relationships`

Giai đoạn đầu:

- Có thể bỏ qua `relationships` để hoàn thiện RAG cơ bản.
- Tập trung build được vector store từ `metadata` + `content`.

Giai đoạn nâng cao:

- Load `relationships` thành bảng riêng.
- Khi retrieve được văn bản A, tìm các văn bản liên quan đến A.
- Nếu A đã bị thay thế, ưu tiên truy xuất văn bản thay thế.
- Hiển thị cảnh báo hiệu lực trong câu trả lời.

Ví dụ logic nâng cao:

```text
User hỏi
  |
  v
Retrieve chunk từ doc_id = A
  |
  v
Lookup relationships của A
  |
  v
Nếu A bị thay thế bởi B, retrieve thêm B hoặc cảnh báo user
```

---

## 8. Những lỗi dữ liệu cần tránh

## Lỗi 1: Chunk trực tiếp HTML

Sai:

```python
chunks = split_text(row["content_html"])
```

Đúng:

```python
plain_text = html_to_text(row["content_html"])
chunks = split_text(plain_text)
```

## Lỗi 2: Không join metadata với content

Sai:

```python
document_id = content_row["id"]
metadata = {}
```

Đúng:

```python
metadata = metadata_by_id[content_row["id"]]
```

## Lỗi 3: Bỏ metadata khi lưu chunk

Sai:

```python
chunk = {"text": chunk_text}
```

Đúng:

```python
chunk = {
    "document_id": doc_id,
    "text": chunk_text,
    "metadata": metadata
}
```

## Lỗi 4: Không xử lý tình trạng hiệu lực

Nếu chatbot hướng đến luật hiện hành, cần xử lý:

```text
tinh_trang_hieu_luc
```

Không xử lý hiệu lực có thể làm chatbot trích dẫn văn bản đã hết hiệu lực.

---

## 9. LLM Instructions

Các hướng dẫn sau dành cho LLM hoặc coding agent khi làm việc với dataset `th1nhng0/vietnamese-legal-documents`.

## Bắt buộc về join dữ liệu

- Dataset có nhiều config, không được xem `metadata` và `content` là hai nguồn độc lập.
- Phải merge hoặc join `metadata` và `content` trên cột `id`.
- `metadata.id` phải khớp với `content.id`.
- Output sau join phải tạo ra document có đủ:
  - `document_id`
  - `text`
  - `metadata`

## Bắt buộc về xử lý HTML

- Nội dung văn bản nằm trong cột `content_html`.
- `content_html` là HTML thô, không phải plain text.
- Bắt buộc dùng thư viện parse HTML như `BeautifulSoup` trước khi chunking.
- Không được đưa HTML thô trực tiếp vào embedding model.
- Không được đưa HTML thô trực tiếp vào prompt LLM.
- Plain text sau parse mới được đưa vào `chunking.py`.

## Bắt buộc về hiệu lực văn bản

- Cột `tinh_trang_hieu_luc` nằm trong `metadata`.
- Có thể dùng `tinh_trang_hieu_luc` để lọc bỏ các văn bản đã `"Hết hiệu lực"`.
- Nếu mục tiêu là hỏi đáp luật hiện hành, nên lọc bỏ hoặc giảm ưu tiên văn bản hết hiệu lực.
- Nếu mục tiêu là nghiên cứu lịch sử pháp luật, có thể giữ văn bản hết hiệu lực nhưng phải hiển thị rõ tình trạng hiệu lực trong câu trả lời.

## Bắt buộc về citation

- Khi lưu chunk, phải giữ metadata đi kèm.
- Khi trả lời, nên trích nguồn bằng các trường:
  - `title`
  - `so_ky_hieu`
  - `ngay_ban_hanh`
  - `co_quan_ban_hanh`
  - `tinh_trang_hieu_luc`

## Bắt buộc về `relationships`

- `relationships` không thay thế cho `metadata` hoặc `content`.
- `relationships` chỉ mô tả quan hệ giữa các văn bản.
- Dùng `doc_id` và `other_doc_id` để tham chiếu về `metadata.id`.
- Có thể dùng `relationships` ở giai đoạn nâng cao để xử lý văn bản sửa đổi, bổ sung, thay thế.

