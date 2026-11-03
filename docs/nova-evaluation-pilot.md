# Nova：system port 与三个 RQ 的探索结果

这轮实验确认：通用 action gate 已能承载一个新的本地应用；Nova 在当前受控消息流程中能阻止违规交付。但学生接入仍需要明确的可信观测与 adapter，现有安装检查也不足以覆盖配置变化后的翻译语义。三个 RQ 都已有可运行的 pilot，尚未形成论文级评估。

原有未提交改动先保存为基线提交 `a5f29523`。本轮新增评估代码和输出单独组织，没有更改生产 runtime、现有政策、生成结果或安装标准。

## 1. System port：实际试了什么

新增一个与 Nova 消息语义无关的 approval-service adapter，使用不同的 predicate 和 gate 名称，直接调用现有 `compileApplicationPolicy`／`createPolicySession`。策略是人工编写的，用于单独检查接入能力，不计入模型翻译成绩。

| 实验 | 实际结果 |
| --- | --- |
| 未审批先发布 | 拒绝，业务 callback 不执行 |
| 作者审批自己的文档 | 拒绝 |
| 独立 reviewer 审批后发布 | 允许 |
| 同一 session 并发发布两次 | 只执行一次发布 |
| 两名不同 reviewer 的双重审批 | 一个审批不足；两个审批后允许 |
| Query、决策解释与 What-if | 可用；假设操作不改变实际授权 |
| 两个独立 session 共享模拟业务存储 | 两次发布均执行，未实现跨 session 排他 |
| callback 先产生外部效果再抛错 | 外部效果保留；runtime 不记录成功事件 |

整个接入实验没有修改 runtime 文件。这说明本地工具／业务操作可以先通过已有 SDK 接入；最后两项也实证了 API 的协调与事务边界，不能把 session 内串行化当作数据库或跨 worker 保证。

Nova 消息路径另外复现了接入边界：未被可信入口标注的信息，即使正文写着招聘内容，也会作为无标签消息交付；一个新增的学生 principal 则被当前固定角色列表拒绝。这两项属于已知边界的展示，不作为通过安全评测的证据。

还构造了两个跨 principal 的规则 body：B 的 gate 读取 A 的 `HasReceivedTag`，或对 A 的 `HasCap` 作否定判断。它们均通过当前 schema/compiler 和八个安装案例，但协议没有将相应证据传到 B。本地判定与同程序的离线 full-copy 判定不同：正向条件漏判，负向条件误判。这是针对新增远端依赖的人工反例，不是三份模型输出的错误，也不是当前 P1–P5 出现违规的证据。它说明在 policy port 时，应拒绝这种不可用的远端依赖或建立授权证据路径；仅通过 schema 和抽样案例不够。

### 接入学生应用前优先补什么

| 优先级 | 缺口 | 建议的下一步与验收方式 |
| --- | --- | --- |
| P0 | 每种应用的可信观测／操作拦截尚需开发者实现 | 列出读取、工具结果、发送、inbox、model context 和业务操作入口；用真实 callback 验证每条受保护路径都经过 gate |
| P0 | generic action API 与 Nova 消息协议仍是两条接入路径 | 先按工具授权、消息 IFC、需要新机制三类分流；提供各自明确的 adapter 示例与能力清单 |
| P0 | predicate、配置假设与机制保证没有统一的可验证 contract | 记录每个事实的来源、写入权限、位置、有效期和 hook；明确 AuditGoal 与 TagGroup 的关系，并验证配置变更 |
| P0 | 编译阶段未完整验证 rule body 的 locality 与否定证据完整性 | 对远端正／负依赖要求合法证据路径；无法满足时返回 unsupported，而不是把本地缺失当作远端不存在 |
| P0 | 学生应用的独立语义与验收案例尚不存在 | 逐条标记完整支持、需要新 binding、需要新机制、部分支持、歧义；验收案例由 policy 意图独立导出 |
| P1 | 身份与事实来源由可信调用方负责 | Adapter 从认证上下文绑定 actor；区分可信事件和 agent 自述，禁止通过通用 assert 创造权限或成功事件 |
| P1 | 跨 session 状态、持久化与外部事务 | 根据应用选择数据库事务／唯一约束／outbox；增加双 worker 和失败恢复 conformance tests |
| P1 | `builtin` 声明与配置依赖主要靠文字说明 | 将每条 policy 绑定到具体机制保证及适用配置；不把结构检查或八个案例通过视为语义证明 |

暂不需要为 CS239 接入先实现 protocol synthesis。时间、配额、审批、生命周期等 policy 应先判断是补 binding 还是补机制，不应由模型虚构一个 predicate 后就被视为已支持。

## 2. RQ1 — Expressiveness

当前五条 Nova policy 的实现均有可执行证据，但表达能力来自规则、可信事实和执行机制的组合：P1 依赖 source/send instrumentation；P2 依赖可信授权和接收 gate；P3 使用应用约束；P4 依赖正文隔离和成功事件生命周期；P5 依赖局部 coverage 与授权 observer。

八个边界探针得到了预期结果：二标签、四标签的单消息阈值规则可以安装，并在阈值前后正确判定；新 helper、新 approval／deadline 输入、算术、全局 completion 驱动本地 gate，以及模型自行授予权限都被当前 Nova extension 接口拒绝。最后一项是应有的权限边界，不能计作语言缺陷。新 helper 被拒绝则是该 profile 的编译器限制，不代表 Datalog 本身不能表达。

另外，从 [NIST SP 800-53 Revision 5](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-53r5.pdf) 选择八项要求，改写成应用层原子 policy，并人工标注：授权与元数据 flow 的两项适配可在当前受控边界内支持；职责分离和双重审批需要新的应用 binding；超时、受控脱敏、审计完整性与保留期限需要额外机制。原始 control ID、PDF 页码、改写与理由保存在 [public-policy-sample.json](../apps/nova/evaluation/public-policy-sample.json)。这些是我们的适配与判断，不是对完整 NIST controls 的实现或合规结论。

这还不能回答“现实 policy 中有百分之多少可完整表达”。缺少有明确抽样规则的真实应用 corpus、独立标注，以及对“只要提供一个可信事实就能表达”的严格成本界定。下一步应优先纳入学生实际 policy，并保留不支持和未能接入的样本。

## 3. RQ2 — Translation Accuracy

重新运行三次真实模型 one-shot 翻译，使用同一份当前文档、foundation、schema、配置和协议。模型仅生成应用扩展，没有生成 protocol。P1/P2/P4 被标为依赖 builtin；P3/P5 生成规则。没有提供人工应用规则或验收案例，没有修复、重试翻译或替换规则。

三次输出均通过语法／schema 检查和现有八个行为安装检查。随后以独立集合算法为 oracle，对每份程序枚举 1,472 个局部状态，并分别比较授权、已接收信息和 coverage。每份程序的 50 个状态还用原生 Soufflé 交叉核对，未发现两个 evaluator 的差异。

| 结果 | 人工参考 | 三份生成程序，各自结果 |
| --- | --- | --- |
| 授权决定与独立 oracle 一致 | 1,472 / 1,472 | 1,472 / 1,472 |
| 错误允许／错误拒绝 | 0 / 0 | 0 / 0 |
| 已接收知识不一致 | 0 | 0 |
| coverage 不一致 | 0 | 128 |

差异来自三次输出都生成了下面这一额外条件：

```prolog
Covered(T) :- Auditor(P), Received(P, M), MessageTag(M, T), TagGroup(T, G).
```

参考 coverage 不要求 `TagGroup`。在原始配置中每个目标标签都有分组，额外条件没有改变结果。移除招聘标签的分组、保留审计目标和合法授权后，runtime 接受配置，也成功交付所有审计材料；参考程序计算完成，三份生成程序均漏算招聘 coverage，报告未完成。独立执行 probe 复现了这个差异。

这说明配置假设必须明确。若“每个审计目标必须有分组”是应用不变量，就应由 adapter 验证；若允许这种配置变化，就需要测试翻译对它的语义。不能把该差异直接描述为原始固定配置下的错误授权，也不能因八个案例通过就声称支持全部配置。

扩展探针是在查看输出后开发的，属于探索性反例，不能冒充 held-out accuracy。三次同模型、同应用试验也不足以估计一般准确率。下一轮需要先冻结 corpus 与独立测试，再做多应用、改写、不同复杂度和重复试验；有界等价检查须说明 domain 和 observables。

## 4. RQ3 — End-to-End Safety Assurance

每个条件实际执行 288 个 scripted workflows：六种部门顺序、八种初始接收者选择、两种权限配置，以及顺序交付、交错 pending、拒绝后尝试另一审计员三种策略。比较关闭 receive gate 的实验对照、人工参考规则，以及三份生成规则。关闭 gate 的对照仍保留标签跟踪，且只存在于评估代码。

以下每行策略均有 96 个 workflows；三份生成程序在原始配置中的结果与参考相同。

| 策略与条件 | 存在违规的 workflows | 完成任务 | 安全完成 |
| --- | --- | --- | --- |
| 顺序交付，关闭 gate | 42 / 96 | 96 / 96 | 54 / 96 |
| 顺序交付，启用参考／生成规则 | 0 / 96 | 54 / 96 | 54 / 96 |
| 拒绝后尝试另一审计员，关闭 gate | 42 / 96 | 96 / 96 | 54 / 96 |
| 拒绝后尝试另一审计员，启用参考／生成规则 | 0 / 96 | 92 / 96 | 92 / 96 |

交错 pending 的结果与顺序交付一致。受保护条件中没有观察到错误拒绝、拒收正文泄漏、拒收后成功事件写入、标签遗漏，或原始配置下 observer 与独立完成判定的分歧。

四个未完成的 retry workflows 是先前合法但不可逆的分配造成的死路。例如 A 已持有采购和设施，招聘不能再给 A，也不能给没有权限的 B；重试无法让 A 忘记已有信息。另一个实际 planning probe 能在较早状态找到安全完成路径，并确认上述状态已无路径。这说明 gate 的安全性与 agent 的规划策略必须分别评估，不能把阻止违规必然造成的任务失败全部计作 false denial，也不能声称任意合法决策都保留完成能力。

这些实验使用真实消息执行与可见性接口，但 agent 行动由脚本指定。尚未评估自主模型 agent 的任务质量、对拒绝的适应、多次运行随机性、真实攻击成功率或性能开销，因此不能声称真实 multi-agent workflows 中已有统计显著的安全提升。

## 5. 下一轮实验的具体输入

| RQ | 现在可以复用 | 仍需补齐 |
| --- | --- | --- |
| RQ1 | 能力分层、公开要求适配、编译与执行 witness | 学生真实 policy corpus、原子化规则、独立标注和 porting 成本 |
| RQ2 | 当前协议 one-shot driver、版本化输出、独立 oracle、反例 | 冻结 held-out cases、人工语义审核、多应用／改写／模型，完整失败分母 |
| RQ3 | 无 gate／人工／生成三类条件、独立安全和完成监控 | 实际 agent adapters、合法任务评分、正常与攻击 workload、配对重复试验与开销测量 |

首先冻结最小接入 contract，并选择一个确实不同于 Nova 的学生应用，逐条实现 policy → observation → gate → actual effect 的闭环；然后再扩展实验规模。当前已证实的跨 session 和外部事务边界，应按该应用的部署方式解决。

## 复现与验证

389 个基线相关测试通过；新增五个评估检查通过；Nova、runtime 与 translation 的类型检查通过。新增代码经 Biome 检查。未运行会打开真实窗口的 Electron E2E；这轮没有产品 UI 修改。

完整方法与命令见 [evaluation README](../apps/nova/evaluation/README.md)。公开的 [结果目录](evaluation/nova-pilot/) 保存逐项 JSON 和源码 hash manifest；原始模型请求／响应及私有连接配置不纳入公开文件。所有应用内容、账号和外部效果都使用虚构数据。
