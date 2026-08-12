# meetings-agent

Agent tham gia họp nhóm (Slack huddle): lắng nghe, transcript, tóm tắt nội dung, ghi lại action items, và sync các "knowledge updates" vào file knowledge chung của team bạn.

Đây là bản **tổng quát hóa, public** của một tool nội bộ — mọi nội dung/thuật ngữ đặc thù của công ty gốc đã được gỡ bỏ. Bạn cần tự điền glossary, tự chỉnh prompts theo văn hóa họp của team, và tự cấu hình API key riêng (xem [Customize cho team của bạn](#customize-cho-team-của-bạn)).

## Cách hoạt động (và giới hạn của Slack)

Slack **không có API chính thức** cho phép bot tự join huddle và truy cập audio stream. Vì vậy agent này chạy trên máy của một người tham gia huddle:

1. **Record** — thu âm hệ thống (loopback: nghe được tất cả mọi người trong huddle — trên Windows dùng WASAPI có sẵn, trên macOS/Linux cần setup virtual audio device, xem [Setup audio trên macOS](#setup-audio-trên-macos)) + microphone (giọng của người chạy agent), mix thành một file WAV.
2. **Transcribe** — chuyển audio thành transcript có timestamp bằng [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (chạy local, hỗ trợ tiếng Việt + tiếng Anh) hoặc Groq API (cloud, nhanh hơn nhiều). Được "mồi" trước bằng danh sách từ khóa trong `glossary.md` để nghe đúng thuật ngữ hơn ngay từ đầu.
3. **Correct** — whisper không biết tên riêng/thuật ngữ nội bộ nên hay nghe sai (vd "architecture" → "ạc quốc"). Bước này dùng Claude đọc lại toàn bộ transcript + `glossary.md` để sửa những chỗ nghe sai dựa vào ngữ cảnh, không đổi nghĩa hay bịa thêm nội dung.
4. **Summarize** — dùng Claude API tóm tắt theo đúng cấu trúc buổi họp (sprint/khách hàng/chung — xem bên dưới), trích action items, quyết định, và các knowledge updates.
5. **Sync** — append phần knowledge updates vào file markdown knowledge chung của team bạn.

## Các loại buổi họp có sẵn

Chỉ bước **Summarize** phụ thuộc loại họp (record/transcribe/correct/sync dùng chung cho mọi buổi) — agent có sẵn 3 profile, chọn qua `--type` hoặc để `auto` tự nhận diện:

- **`sprint`** — họp sprint nội bộ. Nghe cả buổi (họp chung + phần dev/QA planning) nhưng summary chỉ giữ ngắn gọn: tổng kết sprint vừa rồi (goal đạt hay không, update lớn), roadmap sprint tới (epic + sprint goal đã chốt), và phần **next actions** chi tiết nhất (không liệt kê từng issue — cái đó đã có trên Jira/board).
- **`client`** — họp với khách hàng/partner. Tập trung vào nhu cầu/yêu cầu của khách, phản hồi, và cam kết của cả hai phía.
- **`general`** — mọi buổi họp khác (retro, brainstorm, 1-1, design review...). Tự chia theo chủ đề thực tế được bàn, không ép theo khuôn có sẵn.

Cả 3 đều trích **action items** và **knowledge updates**. Đây chỉ là 3 profile có sẵn, không phải giới hạn — xem [Customize cho team của bạn](#customize-cho-team-của-bạn) để sửa nội dung từng loại hoặc thêm loại họp mới.

```powershell
meetings-agent summarize meetings/_raw/general/2026-07-09 --type auto      # tự nhận diện loại họp từ transcript (mặc định)
meetings-agent summarize meetings/_raw/general/2026-07-09 --type sprint    # họp sprint chung + planning dev/QA (2 phần trong 1 summary)
meetings-agent summarize meetings/_raw/general/2026-07-09 --type client    # họp online với khách/partner: nhu cầu, phản hồi, cam kết
meetings-agent summarize meetings/_raw/general/2026-07-09 --type general   # linh hoạt: overview, sections theo chủ đề, quyết định, action items, câu hỏi mở
```

Mặc định `auto`: nếu quên đổi loại họp, tool tự phân loại transcript vào đúng profile (sprint/client/general) rồi mới tóm tắt + lưu — nên với đa số trường hợp bạn không cần chỉ định `--type` gì cả. Giá trị mặc định lấy từ `MEETING_TYPE` trong `.env` (không set thì `auto`). Trong GUI có dropdown "Loại họp" để chọn trước khi bấm Summarize.

## Cài đặt

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e .
copy .env.example .env   # rồi điền ANTHROPIC_API_KEY
```

macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate && pip install -e . && cp .env.example .env`.

Yêu cầu: Python 3.10+. **Windows**: thu âm loopback dùng WASAPI, hoạt động ngay không cần setup thêm. **macOS/Linux**: không có API loopback nên cần cài virtual audio device trước — xem [Setup audio trên macOS](#setup-audio-trên-macos) bên dưới.

### Setup audio trên macOS

macOS không có API cho phép "nghe lại" audio hệ thống như WASAPI của Windows, nên cần 1 bước setup thêm: route audio hệ thống sang một virtual audio device, rồi agent thu device đó như một microphone bình thường.

1. Cài [BlackHole](https://existential.audio/blackhole/) (virtual audio driver, miễn phí):
   ```bash
   brew install blackhole-2ch
   ```
2. Mở app **Audio MIDI Setup** (Spotlight tìm đúng tên) → góc dưới trái bấm "+" → **Create Multi-Output Device** → tick cả loa hiện tại của bạn (vd "MacBook Pro Speakers") **và** "BlackHole 2ch". Cách này giúp bạn vẫn nghe được cuộc họp bình thường, đồng thời audio cũng được route sang BlackHole để agent thu.
3. System Settings → Sound → Output → chọn Multi-Output Device vừa tạo làm output, **trước khi** join huddle.
4. Trong `.env`, trỏ agent vào đúng device đó:
   ```
   LOOPBACK_DEVICE=BlackHole 2ch
   ```
5. Chạy `meetings-agent check-audio` để xác nhận cả 2 kênh (loopback qua BlackHole + mic) đều bắt được tín hiệu, trước khi ghi âm buổi họp thật.

Xong buổi họp, nhớ đổi Output về lại loa thường — Multi-Output Device có độ trễ nhỏ, không nên để làm mặc định lâu dài ngoài lúc ghi họp.

(Linux: PulseAudio thường có sẵn "monitor" source cho mỗi sink, không cần cài gì thêm — set `LOOPBACK_DEVICE` thành tên monitor đó, vd `Monitor of Built-in Audio`.)

## Sử dụng

### Trước mỗi buổi họp — kiểm tra audio

Trên Windows, `soundcard` tự lấy bất kỳ thiết bị nào đang là **Default Playback Device**, nên nếu output audio khi họp là TV (qua HDMI/cast) thay vì loa laptop, agent vẫn hoạt động — miễn là bạn đã set TV làm Default Device trong Windows Sound settings *trước khi* chạy `record`. Một số driver audio (đặc biệt HDMI/display) có thể không hỗ trợ loopback tốt, nên luôn kiểm tra trước. Trên macOS, đây cũng là bước xác nhận `LOOPBACK_DEVICE` đã trỏ đúng và Multi-Output Device đang là output hiện tại:

```powershell
meetings-agent check-audio
```

**Lưu ý về loopback không ổn định:** trên một số driver audio, loopback stream đôi khi "chết" ngay khi mở — im lặng tuyệt đối dù có audio đang phát. Agent tự phát hiện (im lặng bit-chính-xác, khác với âm thanh thật dù nhỏ vẫn có nhiễu nền) và tự mở lại stream tối đa 3 lần trước khi bắt đầu ghi thật. Nếu vẫn thất bại sau 3 lần, sẽ có cảnh báo `WARNING: still silent after 3 attempts` trên console khi chạy `record` — nếu thấy dòng này, dừng lại và chạy `check-audio` để kiểm tra trước khi họp tiếp tục.

```powershell
# Cách nhanh nhất: join huddle trên Slack rồi chạy, Ctrl+C khi họp xong
# (record -> transcribe -> correct -> summarize, tự động)
meetings-agent run

# Hoặc chạy từng bước (profile-agnostic — dùng chung cho mọi loại họp)
meetings-agent record meetings/_raw/general/2026-07-04       # thu âm, Ctrl+C để dừng
meetings-agent transcribe meetings/_raw/general/2026-07-04   # tạo transcript.md + segments.json
meetings-agent correct meetings/_raw/general/2026-07-04      # sửa lỗi ASR -> transcript_corrected.md
meetings-agent summarize meetings/_raw/general/2026-07-04    # tạo summary.md + knowledge.md

# Sync knowledge updates vào file knowledge chung của team
meetings-agent sync meetings/_raw/general/2026-07-04 --to "C:\path\to\your\knowledge.md"
```

Hoặc dùng GUI (click thay vì gõ lệnh terminal):

```powershell
meetings-agent gui
# hoặc double-click scripts\launch_gui.bat
```

`summarize` tự động ưu tiên dùng `transcript_corrected.md` nếu đã chạy `correct`, nếu không sẽ dùng `transcript.md` gốc. Cách chọn loại họp (`--type`) xem mục [Các loại buổi họp có sẵn](#các-loại-buổi-họp-có-sẵn) ở trên.

## Customize cho team của bạn

Đây là 3 chỗ bạn cần tự sửa để dùng cho team mình:

1. **[`glossary.md`](glossary.md)** — điền thuật ngữ, tên sản phẩm/feature, tên khách hàng lớn, tên platform, tên đội **của team bạn** (file hiện tại chỉ là template rỗng có ví dụ). Càng đầy đủ, cả whisper (nghe đúng ngay từ đầu) lẫn Claude (sửa lỗi bằng ngữ cảnh) càng chính xác hơn theo thời gian. Cập nhật liên tục khi có tên mới xuất hiện.

   Agent chạy trên máy của **người đang ngồi trong huddle**, tức mỗi buổi có thể là một người khác. Nếu glossary chỉ nằm trong repo của từng người thì mỗi máy nghe đúng một kiểu và không ai tích luỹ được gì. Đặt `GLOSSARY_FILE` trong `.env` để trỏ tới một file glossary dùng chung của team (repo private, thư mục share...) — mọi người dùng chung một bộ thuật ngữ, ai thêm từ mới thì cả team hưởng, và tên nội bộ không phải nằm trong repo này:
   ```
   GLOSSARY_FILE=C:\path\to\your\team-glossary.md
   ```

2. **[`prompts/*.md`](prompts/)** — nội dung/cấu trúc mà agent tóm tắt theo. 4 file:
   - `sprint_summary.md` — họp sprint (profile `sprint`)
   - `client_meeting.md` — họp khách hàng/partner (profile `client`)
   - `general_summary.md` — mọi buổi họp khác (profile `general`)
   - `transcript_correction.md` — bước sửa lỗi ASR dùng glossary

   Sửa trực tiếp các file này nếu văn hóa họp của team bạn khác (vd không có phần dev/QA planning riêng, hoặc muốn thêm mục "risks" vào summary). Muốn thêm **loại họp mới**: tạo 1 file prompt trong `prompts/` + 1 `Profile` (schema + cách render) trong [`src/meetings_agent/profiles.py`](src/meetings_agent/profiles.py) — record/transcribe/correct/sync không cần đổi gì.

3. **`.env`** (copy từ `.env.example`) — API key riêng của bạn:
   - `ANTHROPIC_API_KEY` — bắt buộc, dùng cho bước correct + summarize.
   - `GROQ_API_KEY` — chỉ cần nếu bật `TRANSCRIBE_BACKEND=groq` để transcribe nhanh hơn qua cloud (xem cảnh báo bên dưới).

### Cấu trúc output

File thô của mỗi buổi (audio + transcript trung gian) nằm trong `meetings/_raw/<profile>/<ngày>/` (gitignore, không commit). Summary đã chắt lọc được publish theo từng profile:

```
meetings/
├── _raw/                          # [gitignore] file làm việc, chia theo profile
│   └── sprint/2026-07-12/
│       ├── recording.wav
│       ├── transcript.md
│       ├── segments.json
│       ├── transcript_corrected.md
│       ├── summary.json           # bản structured (dùng cho sync)
│       └── knowledge.md
├── sprint/2026-07.md              # 1 file/tháng, gộp các sprint — H1 "07/2026 - Sprint 174 & 175"
├── client/<tên-khách>/2026-07.md  # theo khách + tháng (gộp nhiều buổi cùng khách/tháng)
└── general/2026-07/<tên-ngắn>.md  # theo tháng, mỗi buổi 1 file, tên tự đặt từ tiêu đề
```

- **sprint**: chạy summarize sẽ *append* buổi vào file tháng, key theo số sprint (lấy từ transcript, hoặc `--sprint N`); chạy lại cùng sprint sẽ *thay thế* mục đó (không nhân đôi).
- **client**: gom theo tên khách (lấy từ transcript) rồi theo tháng.
- **general**: mỗi buổi một file, tên ngắn tự sinh từ `meeting_title`.

Summary được commit để team xem; `_raw/` và `*.wav` thì gitignore (nội dung thô/nhạy cảm không commit).

## Cấu hình (.env)

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | API key của Anthropic (bắt buộc cho correct + summarize) |
| `CLAUDE_MODEL` | `claude-sonnet-5` | Model dùng để correct + tóm tắt |
| `MEETING_TYPE` | `auto` | `auto` (tự nhận diện) / `sprint` / `client` / `general` |
| `AUTO_PUSH` | `false` | `true` = tự commit + push file summary lên GitHub sau khi summarize |
| `TRANSCRIBE_BACKEND` | `local` | `local` (faster-whisper, free) hoặc `groq` (cloud, nhanh hơn nhiều) |
| `WHISPER_MODEL` | `medium` | Kích thước model whisper khi backend là `local` |
| `GROQ_API_KEY` | — | Bắt buộc khi `TRANSCRIBE_BACKEND=groq` (lấy tại console.groq.com) |
| `LOOPBACK_DEVICE` | — | Chỉ cần trên macOS/Linux — tên virtual audio device dùng làm loopback (vd `BlackHole 2ch`). Xem [Setup audio trên macOS](#setup-audio-trên-macos) |
| `WHISPER_LANGUAGE` | *(auto)* | Ép ngôn ngữ transcript, ví dụ `vi` |
| `KNOWLEDGE_FILE` | `meetings/knowledge-updates.md` | Đường dẫn mặc định cho `meetings-agent sync` (thay cho `--to`) |

**Lưu ý về `TRANSCRIBE_BACKEND=groq`**: audio buổi họp thật sẽ được upload lên Groq (bên thứ 3) để transcribe. Cân nhắc kỹ nếu nội dung họp có thông tin nhạy cảm/bảo mật trước khi bật — mặc định `local` chạy hoàn toàn trên máy bạn, không gửi đi đâu.

**Lưu ý về `AUTO_PUSH=true`**: summary sẽ được tự động commit + push lên GitHub ngay sau khi `summarize` xong — **không qua bước review nào của người**. Nếu repo bạn dùng để publish summary là **public** (hoặc có người ngoài team xem được), đừng bật flag này trừ khi bạn chắc chắn muốn mọi buổi họp lên đó tự động — nội dung nhạy cảm lỡ nói trong họp sẽ public ngay lập tức mà không ai kịp chặn. An toàn hơn: để `false` (mặc định) và tự `git push` sau khi đã đọc lại summary.

## Roadmap

- [ ] Speaker diarization (phân biệt ai đang nói)
- [ ] Tự động post summary lên Slack channel sau họp
- [ ] Đọc agenda/issues từ tracker trước họp để tóm tắt chính xác hơn
- [ ] Agent tự tổ chức họp (điều phối agenda, chốt quyết định)

## License

MIT — xem [LICENSE](LICENSE).
