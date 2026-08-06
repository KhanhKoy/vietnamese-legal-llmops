# Kế hoạch cải thiện tốc độ và áp dụng kiến trúc AWS

Tài liệu này chia công việc thành hai luồng. Trạng thái **đã làm trong code** không có nghĩa tài nguyên đã được tạo trên tài khoản AWS.

## A. Cải thiện tốc độ trả lời

### P0 — bắt buộc

- [x] Khi dùng pgvector, mỗi câu truy vấn chỉ gọi `VectorStore.search()` một lần.
- [x] Không gọi `hybrid_search`/`keyword_search` có `LIKE '%...%'` trên RDS trong đường mặc định.
- [x] Không chạy `COUNT(*)` trước mỗi truy vấn pgvector.
- [x] Dùng chung một `EmbeddingService` giữa Retriever và VectorStore.
- [x] Tắt query rewrite mặc định; chỉ bật bằng `ENABLE_QUERY_REWRITE=true` sau benchmark.
- [x] Tắt reranker mặc định; chỉ bật sau khi đo CPU/latency.
- [x] Thêm timeout kết nối, SQL retrieval và LLM.
- [x] Thêm tổng thời gian `latency_ms` vào response.
- [x] Thêm `timings_ms` theo stage: retrieval, embedding, DB search, rerank, LLM, tổng.
- [x] Không bắt buộc HNSW/IVFFlat; exact pgvector search được phép khi `REQUIRE_VECTOR_INDEX=false`.
- [ ] Chạy `ANALYZE legal_chunks` sau mỗi lượt nạp dữ liệu lớn.
- [ ] Benchmark tối thiểu 20 câu bằng `scripts/benchmark_qa.py`: p50, p95, max cho embedding/RDS/LLM/tổng.
- [ ] Nếu exact search vượt ngưỡng latency mong muốn, cân nhắc IVFFlat/HNSW như tối ưu tùy chọn.

### P1 — sau khi đường cơ bản ổn định

- [ ] Bật `pg_stat_statements`/CloudWatch Database Insights để tìm top SQL.
- [ ] Nếu cần keyword search, tạo PostgreSQL full-text/GIN hoặc pg_trgm; không khôi phục full scan cũ.
- [ ] Thêm structured logging theo stage thay cho `print`.
- [ ] Thêm connection pool/RDS Proxy khi có nhiều API/Lambda worker.
- [ ] So sánh recall/latency của exact search với IVFFlat/HNSW nếu sau này cần ANN index.
- [ ] Bật lại reranker và query rewrite từng tính năng, benchmark riêng trước/sau.

## B. Áp dụng kiến trúc AWS mới

### Đã bổ sung trong repo

- [x] FastAPI entrypoint và nhóm API chat/conversation/admin.
- [x] Cognito JWT verification và RBAC `users/editors/admins`.
- [x] Cognito admin service: list, enable, disable, gán group.
- [x] DynamoDB chat repository: conversation metadata, message, user GSI, admin date GSI, TTL.
- [x] Admin tạo presigned S3 upload thay vì gửi file xuyên qua app server.
- [x] S3 manifest chứa metadata/actor cho ingestion.
- [x] Lambda nhận SQS hoặc S3 event, hỗ trợ partial batch failure và retry/DLQ.
- [x] Soft delete luật và loại document đã xóa khỏi vector retrieval.
- [x] Chọn Gemini hoặc Bedrock LLM bằng `LLM_PROVIDER`.
- [x] CloudFormation nền: Cognito, DynamoDB, S3, SQS và DLQ.
- [x] Docker entrypoint cho FastAPI/Chainlit.

### Còn phải triển khai/cấu hình trên AWS

- [ ] Chọn region, domain, VPC, subnet và RDS instance class.
- [ ] Deploy `infra/foundation.yaml` với tên S3 bucket duy nhất.
- [ ] Đóng gói/deploy Lambda cùng dependencies hoặc chuyển ingestion nặng sang ECS worker.
- [ ] Gắn SQS event source mapping cho Lambda và bật `ReportBatchItemFailures`.
- [ ] Cấp IAM tối thiểu cho API/Lambda: S3, SQS, DynamoDB, Cognito, Bedrock, Secrets Manager.
- [ ] Tạo bảng chuẩn `legal_documents` và migration FK/version với `legal_chunks`.
- [ ] Thêm processing status `UPLOADED/QUEUED/INDEXED/FAILED` và API retry.
- [ ] Thêm application audit log cho thao tác admin.
- [ ] Chuyển RDS password/API key sang Secrets Manager; bỏ AWS access key khỏi `.env` production.
- [ ] Tạo RDS Proxy nếu Lambda/API tạo nhiều connection.
- [ ] Tạo Bedrock Runtime, S3, DynamoDB, Secrets Manager và CloudWatch VPC endpoints theo nhu cầu.
- [ ] Đặt app trong private app subnets, RDS trong isolated DB subnets, ALB ở hai public subnets.
- [ ] Thêm ACM HTTPS, Route 53, WAF và security groups tối thiểu.
- [ ] Chạy ít nhất hai ECS tasks/EC2 instances ở hai AZ nếu yêu cầu HA.
- [ ] CloudWatch logs/metrics/alarms và SNS cho API 5xx, RDS, Lambda, SQS age và DLQ.
- [ ] Xây frontend admin thực tế; repo hiện mới cung cấp backend API.

## Thứ tự rollout

1. Deploy bản sửa performance, chạy `ANALYZE legal_chunks` và benchmark exact pgvector search.
2. Deploy FastAPI ở môi trường dev với `AUTH_DISABLED=true`; không dùng cờ này ở staging/production.
3. Deploy Cognito/DynamoDB/S3/SQS, cấu hình các environment output từ stack.
4. Bật Cognito, kiểm tra quyền User/Editor/Admin.
5. Deploy ingestion worker, thử một PDF text nhỏ và kiểm tra idempotency/retry.
6. Tạo `legal_documents`, audit log và admin frontend.
7. Chuyển Gemini/embedding sang Bedrock bằng index version mới; không trộn embedding model.
8. Bổ sung HA, WAF, backup và monitoring trước production.
