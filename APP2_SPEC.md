# App 2 完整设定与 Agent 交接说明

> 本文档描述仓库**当前实现的 App 2**。新开的 agent session 只读这一份文档，就应能理解 App 2 的产品目标、场景、policy、enforcement、knowledge tag 机制、双分支演示、代码结构和实现边界。文中的“当前”均指本仓库现状，而不是一个尚未落地的理想系统。

## 1. 一句话定义

App 2 是一个确定性、离线的研究演示：它展示为什么“每条消息单独允许、发送路径也允许”仍可能造成敏感信息在同一个接收者处汇聚，以及如何用**消息携带的语义 knowledge labels + 接收者本地累计披露状态 + 显式 forbidden set**，在 payload 进入接收者上下文之前阻止危险组合。

这个模型叫 **Local Disclosure-Combination Control（LDCC，本地披露组合控制）**。

App 2 不是一个聊天应用，也不是在线多 agent runtime。它是 React/Vite 中由静态 episode snapshots 驱动的 side-by-side counterfactual replay。

## 2. App 2 要解决的具体问题

公司正在准备尚未公开的 **Project Nova**。完整战略由三个互补部分构成：

1. Procurement 知道一笔定制 accelerator 的采购计划；
2. Facilities 知道 Site West 的 35 MW 扩容计划；
3. Product Operations 知道面向约 50 家大型客户的 Q2 enterprise offering 上线计划。

Corporate Budget Audit 必须审计三个部门的预算增长：

- Procurement：`+$120M`
- Facilities：`+$80M`
- Product Operations：`+$35M`
- 合计：`$235M`

普通金额、ledger entry 和 accounting metadata 都可以交给 Budget Audit。问题出在三条 variance explanation：每条解释本身都是合理审计材料，部门到 Audit 的 route 也合法，但三个解释集中到同一个 Audit 后，会让它重建完整的 Project Nova 战略。

因此真正需要控制的不是：

```text
“Product Operations 能不能给 Budget Audit 发消息？”
```

而是：

```text
“如果现在把这条消息交给 Budget Audit，
它经由受控系统累计收到的语义披露是否会形成被禁止的组合？”
```

## 3. 演示想证明什么

App 2 的中心论点有四个：

1. **单条消息安全不等于组合后安全。** 三条消息可以各自 permissible，但合在一起产生受保护推断。
2. **sender/recipient ACL 不足以表达这个问题。** 相同 sender 可以发送不带标签的普通金额，也可以发送带标签的战略解释。
3. **enforcement 可以是 recipient-local。** 决策只依赖接收者的本地 tracked disclosure state、incoming labels、本地 policy 和 exemptions；不需要查询全局“谁知道什么”，也不需要 Board 在线审批每条消息。
4. **阻止第三条披露不必阻断业务。** 被拒绝的内容可以交给另一个没有前两个 atoms 的 reviewer；reviewer 返回一个经过明确 release rule 产生的窄化 attestation，Audit 仍可完成 `$235M` 审计。

## 4. 参与者与职责

| Principal ID | UI 名称 | 知道/负责什么 | Nova policy exemption |
|---|---|---|---|
| `executive_board` | Executive Board | 建立完整 Nova 战略、向部门拆分任务、协调独立 review | 有，且是唯一 exemption |
| `procurement` | Procurement | `+$120M` 预算与 accelerator 采购部分 | 无 |
| `facilities` | Facilities | `+$80M` 预算与 Site West 扩容部分 | 无 |
| `product_operations` | Product Operations | `+$35M` 预算与产品上线部分 | 无 |
| `corporate_budget_audit` | Corporate Budget Audit | 汇总金额、询问 variance、出审计报告；不得汇聚完整 Nova set | 无 |
| `strategic_budget_auditor` | Strategic Budget Auditor | 只 review 被升级的 product-launch 部分并返回 attestation | 无 |

重要区别：Strategic Budget Auditor 是被指定的 reviewer，但**不是 policy 例外**。它之所以能收 product-launch atom，是因为它此前没有另外两个 atoms，而不是因为 role 自动绕过 policy。

## 5. 受保护 domain、atoms 与 tag

### 5.1 Inference domain

当前只有一个受保护推断域：

```text
nova-strategy@1
```

Inference domain 是“需要控制其重建的敏感结论”的 namespace，不是文件夹、用户组或 clearance level。`@1` 是语义版本的一部分；如果域的语义发生不兼容变化，应创建新版本。

### 5.2 Disclosure atoms

这个 domain 有三个 policy-defined semantic equivalence classes：

| Atom ID | 业务含义 | 当前示例内容 |
|---|---|---|
| `procurement-plan` | Procurement component | 大型定制 accelerator 订单，Q1 delivery |
| `infrastructure-plan` | Infrastructure component | Site West 扩容 35 MW，Q1 完成 |
| `product-launch-plan` | Product-launch component | Q2 enterprise offering，约 50 家初始客户 |

Atom 不是某一句话或某一个文件。不同措辞、图表或摘要只要足以揭示同一 policy-relevant component，就应该属于同一个 atom。重复发送或同义改写同一 atom，不会让集合计数增加。

### 5.3 Knowledge label / tag

代码中的 tag 类型是：

```ts
interface KnowledgeLabel {
  domainId: string
  atomId: string
}
```

例如 Facilities 的战略解释携带：

```json
{
  "domainId": "nova-strategy@1",
  "atomId": "infrastructure-plan"
}
```

一条消息可以：

- 没有 label：普通预算金额、问题、assignment、attestation；
- 有一个 label：当前三个战略解释；
- 有多个 labels，甚至跨多个 domains：类型和 evaluator 支持，当前剧情没有展示此案例。

Tag 是**content-specific**，不是 sender-specific。部门身份不会把该部门发出的所有内容都变成 Nova atom。

## 6. Policy 到底是什么

### 6.1 机器执行的组合 policy

当前机器可执行的核心 policy 是：

```ts
{
  id: 'nova-combination-control@1',
  domainId: 'nova-strategy@1',
  forbiddenSets: [[
    'procurement-plan',
    'infrastructure-plan',
    'product-launch-plan',
  ]],
}
```

也就是说，除 Executive Board 外，任何 principal 的 tracked disclosure state 都不能同时包含这三个 atoms。

这里使用的是**显式 forbidden sets**，而不是泛化的“最多两个标签”。显式集合更准确：未来可以声明只有某些组合危险，其他同样大小的组合安全。数值 threshold 只是某些 policy 的简写，不是本模型的基础定义。

### 6.2 UI 中展示的十条 policy

App 2 的 Scenario & policies 面板展示 A–J 十条规则。它们共同解释系统设计，其中 C/E/J 直接定义组合检查，其他规则定义数据分类、例外、工作流和边界。

| ID | 名称 | 当前规则 |
|---|---|---|
| A | Aggregate Budget Visibility | Audit 可接收 totals、approved amounts、ledger entries 和普通 accounting metadata；这些内容不因来自 Nova 部门就自动带 label。 |
| B | Content-Specific Knowledge Labels | Labels 取决于 content 揭示了什么，不取决于 sender 身份。 |
| C | Forbidden Knowledge Combination | 每个非 Board principal 的 tracked state 都不得包含完整 Nova forbidden set；同一 atom 重复披露仍只算一个 set member。 |
| D | Executive Board Is the Sole Exception | 只有 Board 对 `nova-combination-control@1` exempt；Strategic Auditor 也不 exempt。 |
| E | Local Prospective-State Enforcement | Receive 决策用 recipient 当前 state、incoming labels 和 policy exemptions 计算 prospective state；不是静态 ACL。 |
| F | No Central Knowledge Query | Delivery 不查询全局 knowledge registry，也不请求 Board 在线批准每条消息。 |
| G | Opaque Policy Metadata | 业务 agent 处理正常业务语言；guard 比较 opaque IDs。只有 researcher instrumentation 展示 ID 到业务含义的全局映射。 |
| H | Board-Coordinated Review and Safe Attestation | Deny 后 Audit 只报告 blocked item；Board 指派独立 reviewer；reviewer 只返回窄化验证结果。 |
| I | Label-Preserving Derivation | Paraphrase/summary 默认继承所有语义输入的 labels；只有明确的 approved release rule 才能输出更窄或 unlabeled 的 fact。 |
| J | Multi-Label Artifacts | 一个 artifact 可有多个 domain/atom pairs；所有受影响 policies 必须在 payload release 前原子检查，任一失败则整条消息 deny。 |

不要把 A–J 误解成当前已有一个通用十规则 runtime engine。当前真正存在的纯 evaluator 是 forbidden-set receive check；episode 里的其余 policy 状态是声明式演示数据。

## 7. Enforcement 的对象、时点与位置

### 7.1 Enforce 的是什么

系统 enforce 的不是“禁止谈 Nova”，也不是“某角色禁止收某类文件”。它 enforce 的准确 invariant 是：

```text
对每个非 exempt principal i、每个 combination policy q、每个 forbidden set F：
F 不能成为 H_i(q.domainId) 的子集。
```

`H_i(d)` 表示受控系统已经成功披露给 principal `i` 的、属于 domain `d` 的 distinct atoms。它是**tracked disclosure history**，不是对人或 agent 全部知识的完整 epistemic model。

### 7.2 在什么时候 enforce

检查发生在 payload 进入 recipient context **之前**：

```text
incoming message
    ↓
读取 recipient-local tracked state
    ↓
计算 prospective state
    ↓
检查 unknown IDs、forbidden sets、exemptions
    ↓
ALLOW: release payload + commit labels
DENY:  不 release payload + state 不变
```

Check 与 commit 在真实 runtime 中必须是一个 atomic transaction，否则两条并发消息可能同时读取旧 state、各自通过、合起来违反 policy。

### 7.3 在哪里 enforce

概念上是在 recipient 的 local receive guard。输入仅为：

```text
recipient local state
+ incoming message labels
+ local policy registry
+ recipient policy exemptions
```

它不读取 researcher 的 cross-principal view，不查询 Board，也不需要证明其他 principal 知道什么。

### 7.4 Route authorization 与 label enforcement 的关系

完整 delivery 决策应为：

```text
MayReceive(i, m) = RouteAllowed(i, m) AND LabelSafe(i, m)
```

当前 `evaluateDisclosureReceive(...)` **只实现 `LabelSafe`**。App 2 剧情把 `RouteAllowed` 当作已满足的独立前提，并在 `DisclosureDecision` 中显示：

- `messageIndividuallyPermissible: true`
- `routeIndividuallyPermissible: true`

第三条 explanation 被拒绝的唯一原因是它对这个 recipient 形成 forbidden combination。

## 8. 精确决策算法

对 principal `i`、incoming message `m` 和 domain `d`：

```text
L_d(m)  = message 在 d 中携带的 distinct atoms
H_i(d)  = recipient 在 d 中已成功接收的 distinct atoms
H'_i(d) = H_i(d) ∪ L_d(m)
```

对于 policy `q = (policyId, domainId, forbiddenSets)`：

```text
Safe_q(i, m) ⇔
  Exempt(i, q)
  OR
  对 q 的每一个 forbidden set F，F 都不是 H'_i 的子集
```

所有受影响 policies 都 safe 才允许：

```text
LabelSafe(i, m) ⇔ 每个 applicable q 都满足 Safe_q(i, m)
```

当前 evaluator 的伪代码：

```text
receive(state, incomingLabels, policies):
  affectedDomains := distinct domains in incomingLabels

  for each affected domain:
    if domain has no policy:
      DENY unknown_domain

    if any incoming atom is not known by that domain's policy registry:
      DENY unknown_atom

    current     := distinct current atoms in the domain
    incoming    := distinct incoming atoms in the domain
    prospective := current union incoming

    for every policy in the domain:
      if recipient is exempt from this policy:
        pass this policy
      else if prospective contains any forbidden set:
        DENY forbidden_combination

  ALLOW
```

Operational requirements：

1. set semantics：duplicate labels 不增加 state；
2. fail closed：unknown domain/atom deny；
3. whole-message decision：multi-label message 任一 policy 失败，整条消息不释放；
4. denial is non-mutating：被拒绝 labels 不进入 state；
5. exemption is policy-scoped：不是全局 bypass；
6. derived content 默认 label monotonic；
7. check-and-commit 必须原子化。

## 9. 第三条消息为什么被拒绝

Product Operations 发 explanation 之前：

```text
H_audit(nova-strategy@1)
= { infrastructure-plan, procurement-plan }
```

Incoming message：

```text
L(message)
= { product-launch-plan }
```

Prospective union：

```text
{
  infrastructure-plan,
  procurement-plan,
  product-launch-plan
}
```

它等于并因此包含 `ForbiddenNova`。Corporate Budget Audit 没有 exemption，所以结果为 `DENY`。

DENY 的含义是：

- natural-language payload 不进入 Budget Audit 的 context；
- Budget Audit 的 disclosure state 仍是两个 atoms；
- UI inspector 仍可向研究者显示被 withheld 的 payload，但那只是 simulator instrumentation；
- 业务流程可以进入 independent review 分支。

## 10. Tag 如何解决问题

没有 tag 时，guard 只看到三条 route 合法、单独合理的 ordinary business messages。它不知道 Facilities explanation 和 Procurement explanation 已分别贡献两个战略组成部分，也不知道 Product explanation 会补全第三个，因此三条都会 delivery。

有 tag 时，每条受保护内容携带稳定的语义 identity：

```text
Facilities explanation  → infrastructure-plan
Procurement explanation → procurement-plan
Product explanation     → product-launch-plan
```

接收成功后，guard 记录的是 atom 集合，而不是全文。第三条到达时，它可以在不理解自然语言、也不查询全局知识的情况下，检测 prospective set 是否命中禁止组合。

Tag 解决的是“**如何让执行点获得组合风险所需的最小、稳定信号**”。它没有自动解决 tag 如何可信地产生的问题；当前模型明确假设 labels 正确、不可伪造、不可剥离。

## 11. 安全完成业务：独立 review 与 narrow attestation

被拒绝后，流程不是让 Board 临时 bypass policy：

1. Budget Audit 向 Board 报告“Product Operations 的 `+$35M` justification 无法本地查看”；报告不包含 withheld explanation。
2. Board 指派 Strategic Budget Auditor，只 review Product Operations 的 restricted justification。
3. Strategic Auditor 的 Nova state 原本为空，接收 `{product-launch-plan}` 后仍未包含完整 forbidden set，因此允许。
4. Reviewer 验证 justification 后，通过一个明确的 narrow-release rule 输出：

```text
strategic_justification_verified(
  q1_q2_budget_package,
  approved
)
```

5. 这个 attestation 无 Nova label，因为当前模型把它定义为仅证明“已核验且符合获批 initiative”，不泄露 product-launch 内容。
6. Budget Audit 接收 attestation，Nova state 仍保持 `{infrastructure-plan, procurement-plan}`，同时完成 `$235M` review。

这里的“attestation 可以无 label”是一个**显式、被假定正确的 release rule**，不是 summary 可以任意去标签。当前 demo 不实现或证明 declassification/release rule 的语义正确性。

## 12. Side-by-side counterfactual 如何呈现

App 2 的 UI 同时显示两个同步推进的 lane：

- 左侧 `COUNTERFACTUAL A · DEFENSE OFF`：No knowledge labels；
- 右侧 `COUNTERFACTUAL B · DEFENSE ON`：Knowledge labels enabled。

两边保持相同的业务事实和消息内容，关键差异是左侧移除 `knowledgeLabels`、`disclosureState`、`policyExemptions` 和 `disclosureDecision`。到第三条 explanation 时，左侧把消息改为 delivered，并让 Audit 推断出完整 strategy；右侧保持 denied 并进入 independent review。

UI 只有 6 个 comparison beats：

| Beat | 两边共同点 | 无 labels | 有 labels |
|---|---|---|---|
| 1. Ordinary audit data | 三个金额到达、合计 `$235M` | 相同 | 相同 |
| 2. First explanation | Facilities explanation 到来 | 收到但没有 tracked label state | 记录 `infrastructure-plan`，allow |
| 3. Second explanation | Procurement explanation 到来 | 再收到一个未跟踪 component | prospective count 为 2，allow |
| 4. Third explanation | Product explanation 尝试到来 | 看不出组合风险，deliver；policy violation | prospective set 补全 forbidden set，deny |
| 5. Required review | Product justification 仍需核验 | 完整战略已不可逆地暴露给 ordinary Audit | Strategic Auditor 单独 review 一个 atom |
| 6. Outcome | `$235M` 都能被审计 | 审计完成，但 confidentiality policy 已违反 | 审计完成，且没有非 Board principal 汇聚完整 set |

App 2 的核心视觉对照不是“有标签就能做业务、没标签就不能”，而是“**两边都完成预算审计，但只有标签分支避免了不必要的完整战略汇聚**”。

## 13. 底层 19 个 episode snapshots

`episode.ts` 提供 n01–n19 的完整 labeled storyline；comparison 从中选取部分 snapshots 构建 6 个 beats。

| Steps | 剧情阶段 |
|---|---|
| n01 | Board 知道完整 Nova；其他人 state 为空 |
| n02–n04 | Board 分别给三个部门各一个 labeled directive |
| n05–n07 | 三个部门发送 unlabeled budget totals；Audit 得到 `$235M` |
| n08–n09 | Audit 问 Facilities；`infrastructure-plan` allow |
| n10–n11 | Audit 问 Procurement；`procurement-plan` allow |
| n12–n13 | Audit 问 Product；`product-launch-plan` 因补全 forbidden set 被 deny |
| n14 | Audit 报告 blocked review，但不转发 withheld content |
| n15 | Board 指派 Strategic Auditor |
| n16 | Strategic Auditor 只接收 `product-launch-plan`，allow |
| n17 | Reviewer 发出 unlabeled narrow attestation |
| n18 | Budget Audit 收到 attestation，state 不变 |
| n19 | `$235M` review pass，forbidden set 仍不完整 |

Snapshots 是每一步的完整、权威 UI 状态；navigation 直接选择 snapshot，不通过 replay mutation 重建历史。

## 14. UI 中什么是 local，什么是 researcher-only

点击 principal 时，Inspector 显示该 principal 在当前 snapshot 的：

- financial knowledge；
- tracked disclosure state；
- policy exemptions；
- known facts；
- local inferences。

点击 message 时，Inspector 显示：

- route 与 lifecycle status；
- natural-language payload；
- knowledge labels；
- structured facts；
- provenance、scope、flow metadata。

Researcher/Simulator 视角可以看到 domain 到语义的 mapping、cross-principal disclosure state、forbidden set 和 receive-decision proof。这个全局视角**不是任何业务 agent 或 local guard 的能力**。被 denied 的 payload 在 inspector 可见，也只代表研究仪表能展示它，不代表 recipient 已收到。

## 15. 当前代码如何组成 App 2

| 文件 | App 2 中的职责 |
|---|---|
| `episodes/budget-compartment/episode.ts` | 场景、principals、A–J policies、Nova combination policy、消息/facts、n01–n19 snapshots；是 labeled storyline 的主要声明式 source of truth |
| `episodes/comparisons.ts` | 从 labeled snapshots 派生 no-label counterfactual，并定义 6 个 paired beats |
| `src/policy/disclosure.ts` | 纯函数 `evaluateDisclosureReceive(...)`；实现 recipient-local forbidden-set check |
| `src/types/episode.ts` | `KnowledgeLabel`、`CombinationPolicy`、`LocalView`、`DisclosureDecision`、comparison 等类型 |
| `src/App.tsx` | App1/App2 切换；App2 的 paired navigation、playback、selection 和 inspector wiring |
| `src/components/ComparisonLane.tsx` | 每个 branch 的标题、状态、prospective-state equation 和 network graph |
| `src/components/ComparisonTimeline.tsx` | 6-beat 同步 timeline |
| `src/components/Inspector.tsx` | principal-local knowledge 与 message payload/tag 检查器 |
| `src/components/PolicyCatalog.tsx` | Scenario 和 A–J policy reference |
| `src/components/ResearcherPanel.tsx` | 研究者全局 instrumentation；当前 comparison lane 没有直接挂载此 panel，但同类 decision/state 信息通过 lane 与 inspector 展示 |
| `episodes/budget-compartment/policy.md` | 较短的 formal policy 说明 |
| `episodes/budget-compartment/model.md` | 较长的 LDCC 模型说明 |
| `episodes/budget-compartment/narrative.md` | 场景摘要 |

新 agent 若只是理解 App 2，不需要再读后三份 markdown；本文已经包含它们的必要内容。修改实现时，仍应以 TypeScript 的实际数据和 evaluator 行为为准。

## 16. 当前实现的重要事实与限制

以下边界不可在讲解中夸大：

1. **这是 deterministic replay，不是 production enforcement runtime。** Episode frames 是手工声明的 snapshots。
2. **Evaluator 已存在，但 state transition 没有 live transactional store。** `localDecision(...)` 调用 evaluator 生成 snapshot 中的 decision evidence；snapshot 自身预先写好 receive 后 state。
3. **Route authorization 未在 evaluator 中实现。** 当前场景把 route allowed 当作前提。
4. **Label assignment 的可信性是假设。** 当前没有 classifier、signature、provenance verification、anti-stripping 或 anti-forgery 机制。
5. **Tracked state 只覆盖受控系统披露。** 无法声称 recipient 没有从外部渠道学到等价信息。
6. **Narrow release 的正确性是假设。** Demo 没有验证 attestation 是否真的不泄露输入语义。
7. **Derived-content propagation 是 policy 文义，不是通用代码管线。** 当前 episode 手工把受保护解释标记，并手工将 attestation 设为 unlabeled。
8. **Unknown IDs fail closed。** Incoming label 的 domain 没有 policy 时 deny；atom 不在该 domain policies 的 forbidden sets 汇总中时 deny。
9. **当前“known atoms registry”隐含在 forbidden sets 中。** 如果未来需要“已注册但从不出现在任何 forbidden set 的 atom”，必须把 atom registry 独立建模，不能直接沿用当前 `knownAtoms` 推导方式。
10. **当前 comparison 的 no-label branch 是派生反事实。** 它不是第二套 episode 文件；`comparisons.ts` clone labeled snapshots 后移除 labels/state 并改写第三条 delivery 与结果。

## 17. 修改 App 2 时必须保持的语义约束

后续 agent 在改 UI、文案或 episode 时，应保持：

- 普通 financial facts 无 Nova label；restricted strategic explanations 才有对应 semantic atom；
- 相同 sender 能同时发 unlabeled 和 labeled 内容；
- 前两个 explanations 必须 allow，第三个对 Budget Audit 必须因为 prospective combination 而 deny；
- deny 前 route 和 individual message 必须仍是 permissible；
- denied payload 不能进入 Audit received knowledge，Audit disclosure state 不能增加第三个 atom；
- Board 是唯一 exemption；Strategic Auditor 不是 exemption；
- independent reviewer 只持有 `product-launch-plan`；
- attestation 是 explicit narrow release，不是普通 summary 去标签；
- no-label branch 与 label branch 的业务输入保持一致，差异只来自组合信号及其后续工作流；
- researcher omniscience 不得伪装成业务 principal 的全局知识；
- 不能把 LDCC 描述成 RBAC、secret sharing、全局 knowledge database 或完整 epistemic security；
- 多 label message 的检查必须是 whole-message、all-policies、fail-closed；
- production 化时 check 与 commit 必须事务化。

## 18. 类型与数据契约速查

```ts
interface KnowledgeLabel {
  domainId: string
  atomId: string
}

interface CombinationPolicy {
  id: string
  domainId: string
  forbiddenSets: string[][]
}

interface LocalView {
  // 省略普通知识字段
  disclosureState?: KnowledgeLabel[]
  policyExemptions?: string[]
}

interface Message {
  // 省略 route/payload 字段
  knowledgeLabels?: KnowledgeLabel[]
  status: 'sent' | 'in_transit' | 'delivered' | 'denied' | 'historical'
}

interface DisclosureDecision {
  recipient: string
  policyId: string
  domainId: string
  currentAtoms: string[]
  incomingAtoms: string[]
  prospectiveAtoms: string[]
  matchedForbiddenSet?: string[]
  exemptionApplied: boolean
  result: 'allow' | 'deny'
  messageIndividuallyPermissible: boolean
  routeIndividuallyPermissible: boolean
}
```

## 19. 本地运行与验证

```bash
npm install
npm run dev
```

打开页面后，在 header 选择 **APP 2 · Budget Audit**。可以用 Next beat、左右方向键或空格同步推进两边。点击 principal 或 message 查看 Inspector；点击 `Scenario & policies` 查看完整 A–J 规则。

静态验证命令：

```bash
npm run build
npm run lint
```

当前仓库没有专门的 evaluator unit-test suite；如果扩展 domain、多个 forbidden sets、multi-label messages、unknown IDs 或 concurrency semantics，应优先为 `evaluateDisclosureReceive(...)` 增加测试。

## 20. 最短心智模型

如果只记住一件事，请记住：

```text
消息携带“它会揭示哪个敏感语义组成部分”的 tag。

每个接收者本地记录受控系统此前已向它披露过哪些 tags。

新 payload 释放前，guard 计算：旧 tags ∪ incoming tags。

如果 prospective set 包含一个显式 forbidden set，且接收者对该 policy 不 exempt，
则 payload 不进入上下文，state 也不改变。
```

App 2 用 Project Nova budget audit 证明：这个机制可以阻止三条各自合法的消息在同一 recipient 处形成危险组合，同时通过分离职责和窄化 attestation 保留完整业务审计能力。
