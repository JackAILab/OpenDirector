# OpenDirector

VisualAgent / AdvertiseAgent 创作系统的独立部署版本。提供统一画布与故事板、Director 对话、图片和视频生成、参考节点连接、图片编辑、视频时间轴、Agent 剪辑助手、3D 场景工具、账户与积分管理。

**源码在 GitHub，大体积素材在私有 ModelScope 数据集。** 本地可启动相同的工作室界面与后端逻辑；真实生成需要你自己的模型凭证和额度。源码与素材不包含线上账户、密码、会话、积分数据库或用户私有项目，不会复刻线上登录状态。部分高级工具和供应商模式仍有验证限制，不能将按钮存在理解为每条链路均已通过完整生产验收。

当前同步版本：**2026-10-23**。更新与验证边界见 [本次发布说明](docs/RELEASE_2026-10-23.md)。

## 快速部署（Docker Compose）

要求：Docker Engine/Desktop + Compose v2、Python 3.11+（初始化脚本）、可访问 Python/npm/Docker 镜像源；预留至少 15 GB 空间，完整素材库另计。Linux 与 macOS 使用同一 Compose；本次 Linux 构建/验证结果见 [部署验证](docs/DEPLOYMENT_VERIFICATION.md)，macOS 尚未实机验证。

```bash
git clone https://github.com/JackAILab/OpenDirector.git
cd OpenDirector
python3 deployment/local/init.py
# 打开 .env，设置自己的 ADMIN_EMAIL；ADMIN_PASSWORD 已随机生成。
docker compose up -d --build
docker compose ps
```

打开 <http://localhost:30080>，右上角登录。管理员用 `.env` 中的邮箱和密码登录，积分不限；普通注册账户初始 0 积分，可申请积分。管理页面：<http://localhost:30080/management>。邮箱注册默认不发送验证邮件；公网使用前应配置 SMTP 并开启邮件验证。微信和手机号入口暂未接入。

启动不会调用付费模型。管理员仅首次创建，修改 `.env` 不会重置已有账户密码或提升普通账户权限。服务默认只绑定本机；不要直接把开发部署暴露到公网。

## 接入真实模型

1. Director：在 `.env` 设置 `CREATIVE_MODEL_URL`（OpenAI compatible 的 `/v1` 地址）和 `CREATIVE_MODEL`，把 API key 写入 `secrets/director-key`。不要把 key 提交到 Git。
2. Kling：在**宿主机终端**安装 Node.js 18+，执行以下命令并按浏览器提示登录；OAuth 回调需要宿主机的本地端口，因此不要在隔离容器内做首次登录。

   ```bash
   KLING_HOME="$PWD/secrets/kling" npx --yes @klingai/cli-cn@0.1.4 login
   docker compose exec studio kling who_am_i
   ```

   `secrets/kling` 挂载给容器用于令牌刷新；不要上传这个目录。`who_am_i` 只检查身份和能力，不生成媒体。
3. 修改 `.env` 后运行 `docker compose up -d --force-recreate`。在界面选定模型、时长与输入，确认积分后再生成。

模型服务不随源码免费提供。没有配置 Director 或 Kling 时，工作室、账户、画布仍可打开，但对应生成会失败。MiniMax H3、ASR 等可选服务需要另外部署或提供服务配置；本包不含这些模型权重。供应商未返回百分比时只显示实际阶段，不伪造进度；401/429 不会自动换模型付费重试。

## 从 ModelScope 恢复素材

私有数据集：[JackAILab/AdvertiseAgent_Assests](https://modelscope.cn/datasets/JackAILab/AdvertiseAgent_Assests)（保留现有 `Assests` 拼写）。需要该数据集的访问权限。Token 只通过环境变量传入，不要写进代码或命令历史。

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install modelscope-hub==0.1.7
read -s MODELSCOPE_API_TOKEN
export MODELSCOPE_API_TOKEN
# 输入 Token 后回车；下载并校验与本源码匹配的固定版本
python scripts/download_assets.py --bundle showcase
# 完整广告参考库（可选，约 187 GB；建议预留 210 GB）
python scripts/download_assets.py --bundle library
# 分析证据、审核数据库和参考 Skill 数据
python scripts/download_assets.py --bundle learning
unset MODELSCOPE_API_TOKEN
```

下载器使用 `assets.lock.json` 中的版本和 SHA-256，不覆盖内容不同的本地文件。`showcase` 恢复案例工程所用图片、视频、字体；`library` 恢复 `assets/library`，供独立素材库入口使用。工作室首页不会公开展示整个素材库。`learning` 恢复分析数据库、证据帧和参考 Skill 数据。下载前停止服务，避免数据库被同时写入。资源是文件归档而非训练表格，所以这里使用 Hub 文件下载，不使用 `MsDataset.load()` 直接读取 tar 包。

完整构成见 [项目结构](docs/PROJECT_STRUCTURE.md)，版本、恢复与发布规则见 [资产说明](docs/ASSET_RELEASE.md)。私有参考素材中第三方作品仍归原作者，不因下载而获得公开再分发或训练许可。

## 数据与日常操作

- `studio-data` Docker 卷：账户、积分、私有项目和 Kling 任务状态。
- `outputs/`：本地生成与合成输出，默认不会上传。
- `assets/library/`：可选广告素材库；与账户数据分开。
- `secrets/`（含 `secrets/kling`）：模型凭证，必须保密。
- `docker compose logs -f --tail=100 studio`：查看启动/运行日志。
- `docker compose down`：停止服务，保留数据。**`down -v` 会删除命名卷中的账户和项目数据。**

单机仅运行一个 API worker，避免进程内任务锁失效。升级前备份上述数据，停止任务后更新源码再重建镜像；不混用不同版本源码与资产清单。

## 架构

```text
Task → Agent → Runner → Tool/Model → Observation → Trajectory → Evaluator
```

模型适配器在 `harness/models`，受控动作在 `harness/tools`，账户/积分在 `gateway`，项目和编辑 API 在 `harness/studio`。模型负责画面与声音，代码负责可读字幕和 UI。付费生成须显式授权，结果不覆盖旧版本；`training_eligible=false` 直到技术、内容与人工审阅通过。

## 开发

```bash
pip install -e '.[studio,live,test]'
pytest -q tests/test_manual_nodes.py
```

浏览器回归在 `tests/browser`。部分历史验收脚本依赖测试账户或专用服务，不能不加配置地直接运行；不要运行带付费提交的验收脚本来检查安装。

本仓库公开源码不自动授予第三方素材或依赖许可证；依赖按各自许可证使用，参见 [第三方说明](docs/THIRD_PARTY.md)。

## 源码与资产边界

`python scripts/release/check_source.py` 检查 Git 跟踪文件。CI 会拒绝媒体、数据库、模型权重、凭证与超限文件；完整数据由私有 ModelScope 管理。不要将生成输出或账号数据库加入 Git。
