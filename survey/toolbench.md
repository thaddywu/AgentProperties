主线：漏斗

toolenv 里的 tool json 总数                                  10,656
  ├─ 有 score 字段的                                          5,926   (55.6%)
  │   ├─ avgSuccessRate == 100（当年真的活着）                 2,615   (24.5%)
  │   └─ avgSuccessRate >= 80                                3,888   (36.5%)
  │
  │  ↓ 在 sr==100 的 2,615 个里继续筛「endpoint 名含状态动词」
  │       ├─ >= 1 个状态 endpoint                               452   (4.2%)
  │       ├─ >= 2 个                                            182   (1.7%)
  │       ├─ >= 3 个 且 覆盖 >= 2 类动词                          43   (0.4%)
  │       └─ >= 4 个 且 覆盖 >= 3 类（真有生命周期）               17   (0.2%)
  │
  │  ↓ 这 17 个里再要求「ToolBench 真给它生成过 query 且跑出 trace」
  └────────────────────────────────────────────────────────────  7
动词类别我分了 6 类（create/delete/update/auth/toggle/exec），全库覆盖：create 1,172 个 tool、exec 661、auth 395、update 228、delete 188、toggle 84。可以看到 delete/toggle 极稀少 —— 这就是"能闭合的生命周期"稀少的直接原因。

最后活下来的 7 个 + trace 量：

tool	category	sr	#API	状态 endpoint	#query	#有 trace
sms77io	SMS	100	37	20	553	492
Felina Multisig Wallet API	Database	100	10	8	186	140
D7SMS	SMS	100	10	5	127	53
CatalogAPI	Business	0	16	10	82	44
QuickMocker	Tools	100	5	4	78	42
English Talking	Communication	100	8	6	68	21
Request Boomerang	Data	100	6	4	23	9
（另外 10 个 —— Inventory and eCommerce、Twitter Auth API、Google Spreadsheets、CRUD API Storage、TextGears、Luxand、DoppelMe 等 —— spec 很漂亮但 ToolBench 从来没给它们生成过 query，一条 trace 都没有。）