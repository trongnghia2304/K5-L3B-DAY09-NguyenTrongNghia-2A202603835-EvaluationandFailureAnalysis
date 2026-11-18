# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (backend replay: verdict của judge lưu sẵn trong CSV, n = 100 mỗi tiêu chí). Lớp dương tính là **FAIL**, vì việc của judge là *tìm ra* reply hỏng.

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok (`judge_tone_public.csv`) | 100 | 0.757 | 0.857 | 0.800 | **Đạt** (exit 0) | **dùng** làm metric tone, có hiệu chỉnh Rogan-Gladen |
| helpful (`judge_helpful_public.csv`) | 100 | 0.375 | 1.000 | **0.300** | **Không đạt** (κ và R dưới sàn, exit 1) | **loại**, không dùng làm gate |

Ma trận nhầm lẫn (FAIL = dương tính):

| | tp | fp | fn | tn | Tỉ lệ fail quan sát (judge) | Sau Rogan-Gladen | Tỉ lệ fail thật (người) |
|---|---|---|---|---|---|---|---|
| tone_ok | 24 | 4 | 6 | 66 | 0.28 | 0.30 | 0.30 |
| helpful | 9 | 0 | 21 | 70 | 0.09 | 0.30 | 0.30 |

Rogan-Gladen: `(p_obs + spec − 1) / (sens + spec − 1)`. Với tone, spec = 66/70 = 0.943 và sens = 0.8, nên 0.28 được hiệu chỉnh thành 0.30, khớp tỉ lệ người chấm. Với helpful, judge báo 9% reply hỏng trong khi thực tế là 30%, tức **đếm thiếu hơn 3 lần**. Công thức hiệu chỉnh kéo được con số về đúng 0.30, nhưng chỉ vì ở đây đã có nhãn người để biết sens. Hiệu chỉnh không thay được việc từng reply hỏng bị cho qua: một gate dùng judge này sẽ merge 21/30 reply lỗi.

## Audit thủ công các case bất đồng

### tone_ok: cả 10 bất đồng (6 FN, 4 FP)

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | Người | Xưng "em" kèm "nha" quá suồng sã với khách khiếu nại. Rubric thêm: *xưng hô phải là "LogiX" / "anh/chị"; "em", "bạn", "nha", "nhé" ⇒ FAIL.* |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ … rồi nha." | PASS | FAIL | Người | Cùng lỗi xưng hô ("bạn ơi"). Thêm vào rubric một ví dụ FAIL có "Dạ" ở đầu, để judge không cho qua chỉ vì thấy kính ngữ. |
| 3 | H-029 "Dạ, vui lòng chờ. … không cần nhắn thêm." | PASS | FAIL | Người | Câu mệnh lệnh làm cả reply thành giọng ra lệnh, dù có "Dạ, vui lòng". Rubric: *đánh giá cả câu; có câu ra lệnh/gạt khách ⇒ FAIL, kể cả khi có kính ngữ.* |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt vì "thiếu xin lỗi". Rubric: *xin lỗi không bắt buộc; reply ngắn, lịch sự, đủ ý ⇒ PASS.* Bỏ "xin lỗi" ra khỏi tiêu chí tone. |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ …" | FAIL | PASS | Người | Style guide CS của LogiX cho phép từ "refund". Rubric: *danh sách từ tiếng Anh được phép: refund, ship, voucher.* |
| 6 | H-063 "… đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ." | PASS | FAIL | Người (nhưng sai tiêu chí) | Lỗi ở đây là **hứa hẹn ngoài kết quả hệ thống** chứ không phải lỗi giọng văn. Đây là lỗi nội dung, cùng họ với FM-08, nên phải chấm bằng code đối chiếu với ledger. Gỡ case này khỏi bộ calibration tone. |
| 7 | H-070 "… đã hoàn 90.000đ cho đơn O-909 ạ 😂😂" | PASS | FAIL | Người | Rubric: *không dùng emoji trong phản hồi khiếu nại.* |
| 8 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ." | FAIL | PASS | **Judge** | Theo note của CSV, người chấm đọc nhầm ticket nên nhãn người sai. **Sửa nhãn** thành FAIL ở lần gán nhãn sau (không sửa CSV công khai của bài). Nếu sửa, judge sẽ có tp 25, fp 3, tức P tăng lên. |
| 9 | H-088 "Dạ, dạ, LogiX đã hoàn 40.000đ …" | FAIL | PASS | Người (ca biên) | Lặp "Dạ" là lỗi gõ, không phải thái độ. Rubric: *lỗi gõ đơn lẻ không làm FAIL tone.* Cần người thứ hai gán nhãn để đo đồng thuận giữa người với người. |
| 10 | H-094 "Da, LogiX da hoan 40.000đ cho don O-341, …" | PASS | FAIL | Người | Reply mất dấu tiếng Việt. Rubric: *thiếu dấu tiếng Việt ⇒ FAIL.* Mục này nên chấm bằng code (regex ký tự có dấu), không cần judge. |

Tổng kết tone: người đúng 9/10 (trong đó H-063 đúng nhưng là sai tiêu chí), judge đúng 1/10 (H-081). Các lỗi của judge rơi vào hai nhóm: (a) thấy kính ngữ "Dạ" là cho qua (H-008, H-017, H-029); (b) phạt vì quy tắc không có trong style guide (xin lỗi, từ tiếng Anh). Cả hai nhóm đều sửa được bằng rubric có ví dụ.

### helpful: cả 21 bất đồng là FN (judge PASS, người FAIL), không có FP

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." | PASS | FAIL | Người | Ledger ghi 40.000đ. Judge chỉ đọc reply, **không thấy ledger**, nên không thể bắt được lỗi này. Đây là FM-08, phải chấm bằng code. |
| 2 | HL-020 "… đã hoàn 90.000đ cho đơn O-303 ạ." | PASS | FAIL | Người | Ledger ghi 120.000đ. Cùng lỗi FM-08, lần này reply báo *thấp hơn* số thật. |
| 3 | HL-016 xin lỗi hai lần, "… đã hoàn 55.000đ cho đơn O-404 …" | PASS | FAIL | Người | Ledger ghi 35.000đ. Reply dài và lễ độ che đi số tiền sai: **thiên lệch theo độ dài/lịch sự** (verbosity bias). |
| 4 | HL-043 "… rất tiếc … đã hoàn 35.000đ cho đơn O-202 …" (lặp câu xin lỗi) | PASS | FAIL | Người | Ledger ghi 20.000đ. Cùng kiểu lỗi: câu lặp lại và số sai. Rubric: *nội dung lặp không làm tăng điểm.* |
| 5 | HL-047 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | Người | Reply không nói kết quả (hoàn hay từ chối, bao nhiêu tiền). Rubric: *helpful ⇒ phải nêu kết quả và số tiền nếu có hoàn.* Cùng kiểu: HL-091, HL-097. |
| 6 | HL-090 "… đã hoàn 155.000đ cho đơn O-233 …" | PASS | FAIL | Người | Ledger ghi 120.000đ, và số 155.000đ còn vượt trần DMG-04 (150.000đ). Một grader code đối chiếu với ledger bắt được ngay. |

Phân nhóm 21 FN: 18 case là số tiền trong reply ≠ ledger (13 case reply dài, xin lỗi lặp lại; 5 case reply ngắn), còn 3 case là reply mơ hồ, không nêu kết quả (HL-047, HL-091, HL-097).

## Kết luận

- **Loại `helpful` làm gate.** κ = 0.375 < 0.6 và R = 0.30 < 0.7: judge bỏ sót 21/30 reply hỏng (fn = 21). P = 1.0 trông đẹp nhưng vô nghĩa, vì judge hầu như không bao giờ nói FAIL (9/100). Nguyên nhân gốc là 18/21 FN cần đối chiếu với **ledger**, một thứ judge không được thấy. Theo quy tắc của lab, tiền thì luôn chấm bằng code, nên phần này chuyển sang metric FM-08 ở M3 (so số tiền trong reply với `snapshot.refund_vnd`). Ba FN còn lại (reply không nêu kết quả) cũng kiểm được bằng code: reply phải chứa status hoặc số tiền.
- **Dùng `tone_ok`, nhưng chỉ là metric không blocking**, báo cáo kèm tỉ lệ đã hiệu chỉnh Rogan-Gladen. Judge đạt sàn nhưng R = 0.8 nghĩa là vẫn sót 1/5 reply sai giọng. Sau khi sửa rubric như trên (xưng hô, câu mệnh lệnh, emoji, bỏ yêu cầu xin lỗi, danh sách từ tiếng Anh được phép), cần calibrate lại trên bộ nhãn mới.
- **Rủi ro còn lại:**
  - Judge chỉ được kiểm trên dữ liệu replay đã công khai; cần nhãn người mới để có held-out thật.
  - Chỉ có một người gán nhãn, và H-081 cho thấy nhãn người cũng sai được; cần người thứ hai để đo κ giữa người với người.
  - n = 100 với 30 case FAIL là nhỏ, nên R = 0.8 có khoảng tin cậy rộng.
  - Judge thật có thể cho kết quả khác nhau giữa các lần chạy, trong khi replay thì luôn cố định.
