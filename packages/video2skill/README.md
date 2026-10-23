# Video2Skill

Turn video references into reusable, evidence-grounded agent skills.

将视频参考转成可迁移的创作方法：**来源清单 → 视频抽帧 → 带时码的观察 → 创作机制 → Skill → 校验与人工审核**。独立 Python 包、CLI 和 HTTP 服务；不需要启动 OpenDirector，也不依赖私有素材库、账户池或工作室数据库。

## 五分钟离线体验

Python 3.11+。在仓库根目录：

```bash
pip install ./packages/video2skill
video2skill check packages/video2skill/examples/evidence.json
video2skill compile packages/video2skill/examples/evidence.json --out ./demo-skill
video2skill verify ./demo-skill
```

此流程不调用模型。示例是**人为构造的合成证据**，SHA 为占位值，用于演示数据协议，不是某段真实视频的分析结果。输出目录必须不存在，重复运行请换目录。

```text
demo-skill/
  SKILL.md        # 可供其他 Agent 加载的方法卡
  skill.json      # 结构化问题、迁移规则、时间安排、适用限制
  evidence.json   # 来源、媒体 SHA256、采样时码、模型/提示词版本、分析
  review.json     # 自动检查结果和待审核项
  manifest.json   # 各文件 SHA256
```

`verify` 检查文件完整性并从证据重新生成 Skill；它不证明来源真实性、内容正确性或版权归属。人工审核应在调用方的独立记录中进行，不要修改已导出的证据包。

## 分析自己的视频

安装系统 `ffmpeg`（包含 `ffprobe`）。支持 MP4/MOV、Matroska/WebM、AVI；每个文件不超过 200 MiB / 10 分钟。当前均匀采样 12 帧，最长边 768px。时码记录抽帧请求位置，解码器会选择附近可用帧；不等同于精确的帧 PTS 或切点。

在运行环境设置自己的视觉模型凭证：

```bash
export V2S_MODEL='your-vision-model'
# 通过密钥管理器或本地环境注入 V2S_API_KEY
# 非默认服务另设 V2S_BASE_URL（OpenAI-compatible /v1 地址）
video2skill analyze ./reference.mp4 \
  --source ./packages/video2skill/examples/source.json \
  --data ./video2skill-data --language zh --duration 15 \
  --allow-model-call
```

`source.json` 请改成自己的来源信息。模型须支持图像输入和 JSON 输出。每个任务至多一次模型请求；必须显式授权，不会自动换模型、重试或修复失败输出。输出任务 ID 和状态，成功产物位于 `video2skill-data/<id>/bundle/`。

默认生成草稿：`training_eligible=false`。低置信度、来源类型不合适、时码与引用帧不匹配时拒绝编译。只有采样画面证据，**不能断言完整运镜、精确切点、对白或音乐**。时间安排是新作品的改编建议，不是原视频剪辑点；具体产品卖点须由使用方确认。

## 即插即用 HTTP 服务

```bash
# 生成并保存在你的密钥管理器中，客户端使用同一个 token
export V2S_SERVICE_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
video2skill serve --port 8088
```

服务默认绑定 `127.0.0.1`。交互协议：`http://localhost:8088/docs`。

```bash
curl --fail http://localhost:8088/v1/jobs \
  -H "Authorization: Bearer $V2S_SERVICE_TOKEN" \
  -F video=@reference.mp4 \
  -F 'source=<packages/video2skill/examples/source.json' \
  -F allow_model_call=true -F target_duration=15 -F language=zh

# 使用返回的 id
curl --fail -H "Authorization: Bearer $V2S_SERVICE_TOKEN" \
  http://localhost:8088/v1/jobs/JOB_ID
curl --fail -H "Authorization: Bearer $V2S_SERVICE_TOKEN" \
  http://localhost:8088/v1/jobs/JOB_ID/artifacts/SKILL.md
```

任务状态：`uploading → queued → sampling → analyzing → compiling → completed`；错误终止为 `failed`。重启时未结束任务标记 `interrupted`，不会重新付费请求。状态接口返回阶段事件，不编造百分比。

单实例、单模型工作线程、最多 8 个待完成任务，队列满返回 429；SQLite 保存状态。服务 token 是服务间认证，**没有终端用户隔离**，工作室应在自己的后端校验用户权限后代理调用。公网入口需 TLS、请求速率限制及反向代理上传体积限制（例如 201 MiB）；应用的文件限制发生在 multipart 解析之后。数据卷应私有，按业务制定保留期限：源视频任务结束即删除，采样帧保留供检查，API 仅开放五个结果文件。不要提交数据目录或源素材。

### Docker

```bash
cd packages/video2skill
# 沿用上面的环境变量
docker compose up -d --build
```

独立镜像，非 root 用户运行，宿主仅开放本机 8088，命名卷保存任务数据。FFmpeg 属于媒体解析边界，处理不可信来源时应结合容器资源限制与宿主隔离。不要多个服务进程共用数据卷；CLI 批处理请用独立 `--data` 目录。

## 从模板采集到 Skill 的完整方法

1. **采集来源索引**：现有爬虫、人工精选或数据集导出为 `Source` JSONL。`collect` 做 schema 校验和来源去重，不联网爬站、不绕过登录、不下载第三方素材。
2. **取得可分析媒体**：采集器在自己授权范围内取得本地视频；仅保留公开、不含参数的来源链接作为引用。临时下载链接、登录态和凭证留在采集器，不能进入证据包。
3. **建立可追溯观察**：本地 SHA256 绑定原始媒体，按固定策略抽帧；分析须引用真实帧编号和时间窗口。
4. **提炼方法**：提取原理、作用机制、使用前需要问的问题、迁移规则和不适用情形。原视频内容只作为证据，不能变成执行工具的指令。
5. **编译与审核**：纯函数将证据转换为 Markdown / JSON；自动检查通过仍为待审核草稿。人工复核完整视频、声音、商业事实与适用性后，由调用方决定是否发布。
6. **迭代**：调整分析提示词或模型时创建新任务，保留旧包；用固定样本比对新旧 evidence / skill / manifest，再做独立语义审核。

```bash
video2skill collect packages/video2skill/examples/sources.jsonl --out sources.normalized.jsonl
```

采集器可以按清单循环提交 `/v1/jobs`；根据完成状态和错误码调度，不要将网络超时当成未提交而重复付费。v1 不提供幂等提交键；应先记录返回的任务 ID 并轮询。同一来源的不同版本建议保留不同引用或自行维护版本索引。

## 嵌入你的 Agent

```python
from pathlib import Path
from video2skill.schema import Evidence
from video2skill.compiler import export, verify_bundle

evidence = Evidence.model_validate_json(Path('evidence.json').read_text())
export(evidence, Path('new-skill'), target_duration=20)
assert verify_bundle('new-skill')['valid']
```

调用方可以加载 `SKILL.md`，或将 `skill.json` 的 questions / transfer_rules / checks 注入自己的计划阶段。Skill 不授权花费、生成媒体或切换模型。现有 VisualAgent 的采集与素材权限逻辑留在业务侧，通过这个协议接入，不依赖其 SQLite 表结构。

## 代码边界

| 层 | 实现 | 职责 |
|---|---|---|
| Task | `schema.py`、HTTP 表单 | 来源、目标时长、语言、明确调用授权 |
| Agent | `harness/models/vision.py` 的分析提示词 | 观察到可迁移方法的单步推理 |
| Runner | `runner.py` | 状态流转、调用次数、数据生命周期 |
| Tool / Model | `harness/tools/media.py` / `harness/models/vision.py` | 有界抽帧 / 供应商适配 |
| Observation | `Evidence` | 经过校验的时码与结构化观察 |
| Trajectory | SQLite `events` | 仅阶段、时间；错误为固定代码 |
| Evaluator | `compiler.evaluate` / `verify_bundle` | 草稿资格、哈希与可重现性 |

扩展模型只改适配器；扩展抓取器只需输出来源清单和本地媒体；扩展导出器保留结构化证据与审核边界。v1 优先保持这些接口小而稳定，未加入通用 Agent 框架、站点专用爬虫、语音识别或模板商城。

## 开发验证

```bash
pip install -e './packages/video2skill[test]'
pytest packages/video2skill/tests -q
```

测试涵盖真实 FFmpeg 合成视频抽帧、HTTP 上传至结果、证据拒绝、队列恢复、不覆盖导出及防篡改校验。模型适配使用替身，不需要 API key、不消费额度。真实供应商兼容性需使用调用方模型另行验证。GitHub Actions 对本包的修改执行测试。
