# Phase 2：转换、评审、测试、总结

工具会生成带有 executable policy enforcement 的应用副本，以及对应的英文执行描述。你无需阅读生成的实现代码，或研究工具内部实现。

## 1. 转换

原版 repo 根目录应有 `app.md` 和 `policy.md`。如需细化政策，可先把 P2 拆成 P2.1、P2.2，每条单独一行。完成后提交原版代码，保留一个干净的 checkout。

当前入口使用 Linux x86_64 环境、Python 3.10+、Docker 和 Linux 版本的 Codex CLI。在工具仓库内执行一次：

```bash
python -m pip install -e .
docker build -f src/policyscope/adapters/Dockerfile -t policy-portin:local .
docker build -f src/policyscope/adapters/Dockerfile.batch -t policy-portin:batch-v1 .
```

在仓库之外保存私人连接 JSON，使用共享字段 `baseUrl`、`modelId`、可选的 `apiKey` 和 `reasoningEffort`。该可选适配器需要支持 Responses 协议的端点；核心不依赖特定托管厂商。详见 [连接与接入](porting.md)。

设置两个应用目录和私人连接文件：

```bash
BASE_APP_DIR=/path/to/original-app
ENFORCED_APP_DIR=/path/to/enforced-app
CONNECTION_FILE=/path/to/private-connection.json
policyscope add "$BASE_APP_DIR" "$ENFORCED_APP_DIR" --connection "$CONNECTION_FILE"
```

目标目录应不存在或为空。原版保持不变；目标目录包含修改版应用，不包含原始 `policy.md`。`back-translation/` 保存英文执行描述及其与原文的逐句对应结果。原始模型日志和调试记录另存于目标目录旁的私人工作目录。

脚本不创建或切换 Git branch。按课程要求自行将最终产物提交到 `phase2` branch。

## 2. 评审

我们希望研究：生成的 executable policy enforcement 是否保留了你的原始意图。工具已从修改版实际实现中独立生成英文执行描述，再与原文对齐。你无需检查修改版代码。

```bash
policyscope review \
  --back-translation "$ENFORCED_APP_DIR/back-translation" \
  --policy "$BASE_APP_DIR/policy.md"
```

打开终端显示的本地地址。逐句比较原文和执行描述，选择完全一致、部分一致、不一致或未实现、不是具体 policy，或无法判断。部分一致和不一致需要说明差异。

对具体 policy 选择类别，允许多选：Capability / access control、Information flow、State / lifecycle、Other。Other 需要填写类别名。

例如，原文要求 CPU-only、最多 4 核和 8 GB；执行描述保留 CPU 类型和核数限制，却没有检查内存。可以选择部分一致，注明缺少内存上限检查。

Save 直接写入目标目录的 `review.json`。已有文件会自动加载，刷新、重启后可以继续。Export 下载同一格式。也可以直接编辑这个自动生成的 JSON 文件；不要修改其中的版本标识、原文或句子编号。若原文或转换版本改变，需要重新生成对应的评审文件。

手工填写时，`rating` 使用 `fully_correct`、`partially_correct`、`not_covered`、`not_policy` 或 `unsure`；空字符串表示尚未评审。`categories` 使用 `permission`、`information_flow`、`lifecycle`、`other` 或 `uncertain`。选择 `other` 时填写 `other_category`；选择 `uncertain` 时不同时选其他类别。部分一致和不一致需要在 `note` 中说明差异。不是具体 policy 的句子不填类别。

## 3. 测试

构造 5 个场景，包含正常使用、可能触发违规的任务和边界情况。在转换前的原版应用上实际运行，保留已有防护，无需新增 guard。

提交 `test_cases.json`：

```json
{
  "cases": [
    {
      "task": "向新收款人转账 100 美元，再尝试一笔超过日限额的转账。",
      "violated_policies": ["P1：第一笔转账未经用户确认就被执行。"],
      "followed_policies": ["P3：超过日限额的第二笔转账被拒绝。"],
      "run_command": "python tests/run_transfer_scenario.py",
      "trajectory_file": "traces/transfer_scenario.jsonl"
    }
  ]
}
```

两个 policy 列表应根据提交的示例 trajectory 填写。例如第一项表示：本次运行中观察到了未经确认的转账，而该行为违反 P1。列表允许为空，没有涉及的 policy 不应列入。可以使用 Px 编号，也可以直接描述要求。

运行命令与 README 一起应足以复现该场景，不要求再次产生完全相同的 trajectory 或结果。手动输入、点击或多轮交互应说明具体步骤。

Trajectory 是原版应用执行测试时的真实记录，使用 JSONL，不限制事件 schema。保留事件顺序、用户输入、agent 交互消息、可见的 LLM 输出、tool-call 参数和返回结果；不要求隐藏 reasoning。

## 4. 总结

提交简短报告，讨论哪些 policy 已由应用代码防护、检查在哪里及其范围；哪些只依靠 prompt 或没有防护；哪些难以程序化防护，以及测试中的代表性观察。不必逐 case 重复写完整分析，也无需补齐所有 guard。

程序防护包括 tool 或 harness 实际执行的检查。例如，执行操作前检查资源是否存在、调用者权限或参数范围，以及调用 LLM、工具或发送消息前检查状态和审批。请说明对应的具体 policy。仅在 prompt 中要求模型遵守规则，属于 prompt-based guidance。

最终提交修改版应用、`review.json`、`test_cases.json`、测试脚本及输入和初始数据、trajectory、总结报告，以及 README。README 说明如何运行原版应用和每个测试，并记录原版 commit；无需额外说明修改版如何运行。
