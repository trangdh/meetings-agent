# Glossary thuật ngữ

File này giúp agent nhận dạng và sửa đúng các thuật ngữ, tên sản phẩm/feature, tên khách hàng lớn, tên platform, tên đội của **team bạn** mà whisper (speech-to-text) không biết trước. Đây là file bạn cần tự điền — càng đầy đủ, agent càng nghe đúng thuật ngữ nội bộ ngay từ đầu.

Cập nhật file này thường xuyên — mỗi khi có tên mới xuất hiện trong họp mà agent nghe sai, hãy thêm vào đây.

Có 2 phần:

1. **Whisper prompt keywords** — một dòng duy nhất, liệt kê các từ khóa ngắn gọn (tên riêng, viết tắt) cách nhau bởi dấu phẩy. Dòng này được đưa thẳng vào whisper để "mồi" trước khi nhận dạng giọng nói, giúp nghe đúng hơn ngay từ đầu.
2. **Chi tiết thuật ngữ** — giải thích từng thuật ngữ, dùng bởi bước sửa lỗi bằng Claude sau khi có transcript thô, giúp Claude hiểu ngữ cảnh để sửa đúng.

---

## Whisper prompt keywords

Claude, Anthropic, LLM, GPT, Gemini, Whisper, ASR, prompt, token, context window, embedding, RAG, fine-tuning, inference, hallucination, agent, MCP, model, API, SDK, skill, harness, project, connector, schedule, compact, remote, sprint, epic, issue, backlog, PO, deploy, release, staging, production, roadmap, MVP

---

## Chi tiết thuật ngữ

### Thuật ngữ AI / mô hình ngôn ngữ

- **LLM (Large Language Model)**: mô hình ngôn ngữ lớn, whisper hay nghe nhầm thành "L L M" tách rời hoặc "el el em".
- **Claude / Anthropic**: tên model/công ty đang dùng cho agent này — whisper hay nghe nhầm "Claude" thành "clode" hoặc "cloud".
- **GPT**: whisper hay nghe nhầm thành "gee pee tee" hoặc "GBT".
- **RAG (Retrieval-Augmented Generation)**: kỹ thuật truy xuất dữ liệu ngoài rồi đưa vào prompt cho model — hay nghe nhầm thành "rag" (giẻ lau) hoặc "rack".
- **Prompt / prompt engineering**: câu lệnh đưa cho model, và kỹ thuật thiết kế câu lệnh đó.
- **Token / context window**: đơn vị model tính chi phí/độ dài, và giới hạn lượng text model đọc được cùng lúc.
- **Embedding**: vector số hoá của text, dùng cho tìm kiếm ngữ nghĩa — whisper hay nghe nhầm "embedding" thành "em bedding".
- **Fine-tuning**: huấn luyện thêm model trên dữ liệu riêng.
- **Inference**: bước model tạo ra câu trả lời (khác với training).
- **Hallucination**: model bịa thông tin sai — whisper hay nghe nhầm thành "hallucinations" bị cắt âm.
- **Agent / MCP (Model Context Protocol)**: agent tự động gọi tool; MCP là chuẩn kết nối agent với tool/data nguồn ngoài — whisper hay nghe nhầm "MCP" thành "M C P" tách rời hoặc "empty".
- **Whisper / ASR**: model speech-to-text mà chính tool này dùng để transcribe — dễ nhầm với "Whisper" (tên riêng khác) trong ngữ cảnh.

### Thuật ngữ Claude Code / agent harness

- **Skill**: gói hướng dẫn/quy trình đóng gói sẵn cho agent (vd slash command riêng) — whisper hay nghe nhầm thành "school" hoặc "skil".
- **Harness**: lớp điều phối chạy agent (CLI/app đang chứa agent, quản lý tool call, context...) — hay nghe nhầm thành "harnest" hoặc "harness" bị cắt âm thành "hardness".
- **Project**: thư mục/workspace agent đang làm việc, gắn với context riêng của project đó.
- **Connector**: tích hợp bên ngoài agent kết nối tới (Slack, Jira, Google Calendar...) — hay nghe nhầm thành "connecter" hoặc "connect to".
- **Context**: lượng thông tin/hội thoại agent đang "nhớ" trong phiên làm việc — phân biệt với "context window" (giới hạn kỹ thuật) ở trên.
- **Schedule / scheduled task**: tác vụ được hẹn giờ chạy tự động (cron job cho agent) — hay nghe nhầm "schedule" thành "sketch you" hoặc "shedule".
- **Compact**: thao tác nén bớt lịch sử hội thoại khi context sắp đầy, để agent tiếp tục làm việc — hay nghe nhầm thành "compat" hoặc "compact" bị cắt âm.
- **Remote**: agent/tác vụ chạy trên môi trường cloud từ xa thay vì máy local — hay nghe nhầm thành "remo" hoặc "remote" bị nuốt âm cuối.

### Thuật ngữ sản phẩm / quy trình

- **[Tên feature/sản phẩm]**: giải thích ngắn gọn, whisper hay nghe nhầm thành gì.

### Tên khách hàng lớn / đối tác

- **[Tên khách hàng]**: ghi rõ cách viết đúng nếu whisper hay nghe sai.

### Tên platform / công cụ

- **[Tên platform]**: vd Shopify, Jira, Slack...

### Tên đội / vai trò

- **[Tên đội]**: dev, QA, support, marketing, PO...
