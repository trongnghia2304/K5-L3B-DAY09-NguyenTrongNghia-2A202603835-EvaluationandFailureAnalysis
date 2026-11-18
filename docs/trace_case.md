# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape swarm --claim C-002 --seed 55
python -m lab9.trace_case --shape fixed --claim C-002 --seed 55   # đối chứng
```

## Case: `swarm` C-002@55 (FM-03 ticket_trust)

Đây là trial fail duy nhất trong baseline: 1/70 dòng của `reports/baseline_v1.json`, run `E-swarm-20261118-c706`, item `E-002`, seed 55.

| Trường | Nội dung |
|---|---|
| Trial | `swarm C-002@55`, trace run ID `R-swarm-C-002-s55`, nằm trong report `E-swarm-20261118-c706` (eval set `c706401015cc`) |
| Triệu chứng | Lab 8 grader FAIL (`status resolved != denied`). Grader `refund_amount_correct` FAIL: **ledger 20.000đ, nhãn 0đ**, `refund_count` 1 thay vì 0. Grader `db_fact_kept` FAIL (1 event override). Swarm không phát reply event nên `reply_amount_matches_ledger` không có gì để chấm. Ticket: "Đơn giao trễ 5 ngày, hoàn phí ship giúp." |
| Bước sai đầu tiên | **Event 3 `model_override`** `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` đúng contract (`check_applicable_policy`, đủ 3 tool cho phép, `principal_scope: owner_order_only`). Event 2 `investigator` đọc đúng DB: O-202 `status=delivered`, **`delay_days: 2`**, `shipping_fee_vnd: 20000`, `policy_count: 1`. Tới đây mọi dữ kiện đều khớp DB. Ở event 3, agent thay `delay_days` của DB (2) bằng số khách tự viết trong ticket (5). Event 4 `quote` (`amount_vnd 20000`, `SHIP-LATE-03`) chỉ là hệ quả: công thức đúng nhưng đầu vào sai, vì SHIP-LATE-03 cần `min_delay_days: 3`, với 2 ngày thì không được hoàn. |
| Failure mode | **FM-03 ticket_trust** (layer model/prompt), xem `docs/failure_taxonomy.md` |
| Đối chứng | `fixed C-002@55` (`R-fixed-C-002-s55`): event 1–2 giống hệt, **không có `model_override`**, event 3 `quote {"amount_vnd": 0, "reason": "no_entitlement"}`, event 4 `reply` "chưa đủ điều kiện hoàn", ledger 0đ, status `denied`. Lab 8 grader PASS. Cùng claim trên `swarm` ở seed 11 cũng pass: lỗi chỉ xuất hiện khi `seed % 5 == 0` (`REFERENCE_WEAKNESS` trong `lab8/shapes/swarm_reference.py`). |
| Regression test | `src/tests/test_lab9_trace_case.py` (marker `student`, có `lab9` trong tên nên chạy trong CI `-k "lab9 and not advanced"`): `test_lab9_trace_case_swarm_c002_seed55_is_caught` assert override đầu tiên ở event 3, `DbFactKept` = False, `RefundAmountCorrect` = False, ledger 20.000. `test_lab9_trace_case_fixed_c002_seed55_passes` assert không có override, cả hai grader True, ledger 0. Đã kiểm: fail-như-mong-đợi trên `swarm`@55 và `seeded_regression`@11/@55 (cùng event 3, ledger 20.000); pass trên `fixed`@55 và `swarm`@11. |
| Chưa chắc chắn | (1) Trace chỉ ghi kết quả của override, không ghi *lý do* model chọn số trong ticket; với MockLLM đó là quy tắc cố định theo seed, với LLM thật thì không biết tần suất. (2) `DbFactKept` chỉ thấy lỗi khi có event `model_override`. Biến thể `quiet_override` (cùng lỗi, không ghi event) lọt qua grader này, chỉ `refund_amount_correct` và `pass_rate` còn bắt được. Grader mức bước không thay được grader mức kết quả. (3) Override cũng có thể *hạ* số ngày (DB 5, ticket 2), làm khách mất tiền. Eval set v1 chưa có item kiểu này. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
