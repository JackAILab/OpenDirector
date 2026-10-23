# 本地部署验证

## 2026-10-23 更新验收

- 从本次独立发布源码重新构建镜像 `opendirector:2026-10-23`。
- 全新 Compose 项目、bridge 网络与数据卷，本机测试端口 30194；容器 healthy。
- 浏览器验证管理员登录、无限积分、新建图片项目、画布、管理页，无页面脚本错误。
- Python 相关回归 91 passed / 1 skipped；资产恢复测试 3 passed；JS 语法与源码边界检查通过。
- Git 跟踪源码约 13 MiB，未包含媒体、数据库或模型权重；保留首次启动需要的中文字体。
- 没有调用付费模型，未把会话中尚未完成的 60 秒广告质量验收记为通过。

## 2026-10-17 基线验证

## 已执行

- 从独立源码导出目录构建 Linux Docker 镜像，成功安装 Python、固定版本 Kling CLI/HyperFrames/GSAP，编译 Three.js 场景 bundle。
- 使用全新容器数据库启动真实网关和本地 Kling 适配器进程，不读取线上账户库。
- 健康检查、首次管理员初始化、邮箱密码登录、无限积分、新建图片项目均通过。
- Chromium 实际打开画布和管理页，无页面脚本错误；中文字体正常加载；测试没有调用付费模型。
- 实际 Docker Compose 使用独立 bridge 网络和本机端口映射启动，健康检查通过，浏览器登录、画布、管理页验收通过。
- 手动节点回归测试 17 项通过。
- 私有 ModelScope showcase 从固定 commit 下载到新目录，通过归档 SHA-256 校验并恢复 47 个文件。约 339 MB 下载包，约 453 MB 展开文件。

## 复验命令

启动 Compose 后可运行浏览器验收（需 Node.js 和 Playwright Chromium）：

```bash
npm install --no-save playwright
npx playwright install chromium
node tests/browser/local_deployment.cjs
```

脚本读取本地 `.env`，创建验收项目并检查管理员登录、画布和管理页，不提交付费生成。`TEST_BASE_URL`、`TEST_ENV_FILE`、`TEST_SCREENSHOT` 可覆盖默认值。

## 限制

- 宿主 Docker 原来未运行，验证使用独立临时 daemon，先验证单容器，再通过 Compose bridge 网络映射到测试端口 30193，未占用线上 30080。Compose 文件仅绑定本机 30080；请确保本机端口空闲。
- macOS/Apple Silicon 尚未实机验证；同一 Compose 可构建，但模型 CLI、浏览器和渲染器跨架构行为需要在目标机器确认。
- 此次不使用线上凭证触发付费生成；供应商身份授权、额度和生成输出须用户配置后验收。
- 不导入线上用户项目与账户，因此不是线上私有数据的逐字节克隆。
- 完整广告库上传和固定版本校验结果以 `assets.lock.json` 中发布的 library 条目为准。
