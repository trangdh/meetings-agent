# Glossary thuật ngữ

File này giúp agent nhận dạng và sửa đúng các thuật ngữ, tên sản phẩm/feature, tên khách hàng lớn, tên platform, tên đội của **team bạn** mà whisper (speech-to-text) không biết trước. Đây là file bạn cần tự điền — càng đầy đủ, agent càng nghe đúng thuật ngữ nội bộ ngay từ đầu.

Cập nhật file này thường xuyên — mỗi khi có tên mới xuất hiện trong họp mà agent nghe sai, hãy thêm vào đây.

Có 2 phần:

1. **Whisper prompt keywords** — một dòng duy nhất, liệt kê các từ khóa ngắn gọn (tên riêng, viết tắt) cách nhau bởi dấu phẩy. Dòng này được đưa thẳng vào whisper để "mồi" trước khi nhận dạng giọng nói, giúp nghe đúng hơn ngay từ đầu.
2. **Chi tiết thuật ngữ** — giải thích từng thuật ngữ, dùng bởi bước sửa lỗi bằng Claude sau khi có transcript thô, giúp Claude hiểu ngữ cảnh để sửa đúng.

---

## Whisper prompt keywords

<!-- Ví dụ — xóa dòng này và điền từ khóa của team bạn: -->
sprint, epic, issue, backlog, PO, deploy, release, staging, production, roadmap, MVP

---

## Chi tiết thuật ngữ

<!-- Ví dụ cấu trúc — xóa và điền thuật ngữ thật của team bạn -->

### Thuật ngữ sản phẩm / quy trình

- **[Tên feature/sản phẩm]**: giải thích ngắn gọn, whisper hay nghe nhầm thành gì.

### Tên khách hàng lớn / đối tác

- **[Tên khách hàng]**: ghi rõ cách viết đúng nếu whisper hay nghe sai.

### Tên platform / công cụ

- **[Tên platform]**: vd Shopify, Jira, Slack...

### Tên đội / vai trò

- **[Tên đội]**: dev, QA, support, marketing, PO...
