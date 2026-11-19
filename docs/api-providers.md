# API 接入指南

High_SC 的 API 模式直接向配置的地址发送 HTTP JSON 请求，不需要另外部署转发服务器。第三方渠道须兼容受支持协议；同名模型不保证具有相同接口能力。

## 通用配置

1. 在“模型设置”选择 Chat Completions、Responses 或 Anthropic Messages。
2. 填写渠道提供的 API 地址、模型 ID 和 API Key。
3. 按渠道文档设置认证和兼容参数。
4. 点击“测试连接”，再“保存配置”。测试发送短 JSON 指令，会调用所选模型，但不上传论文。

### 地址与认证

| 配置 | 示例（占位域名，不是真实服务） |
|---|---|
| 基础地址 | `https://gateway.example/v1`，自动加 `/chat/completions` 等路径 |
| 标准完整地址 | `https://gateway.example/v1/responses`，自动模式避免重复拼接 |
| 自定义网关 | `https://gateway.example/models/reader:invoke`，选择“完整地址原样使用” |
| 带版本参数 | `https://gateway.example/custom/messages?api-version=2026-01-01`，按路由选自动或原样 |

地址不允许嵌入用户名、密码、片段标记或常见密钥查询参数。密钥放在专门的密钥栏或自定义请求头。

“按协议自动选择”使用 Bearer（Chat / Responses）或 `x-api-key`（Messages）。网关要求 `api-key` 时直接切换即可。无认证的本地服务可选“不自动发送认证头”。

自定义头示例：

```json
{
  "X-Gateway-Key": "${API_KEY}",
  "X-Project": "paper-reading"
}
```

`${API_KEY}` 在发送时替换为密钥栏的值。自定义头最后写入，可以覆盖默认认证头。不发送自动认证时仍可通过此处提供自定义认证。禁止覆盖 Host、Content-Length 等传输控制字段，也不接受换行符。

这些头作为敏感配置保存；读取设置时只显示是否已有配置。留空保留，填写 JSON 整体替换，`{}` 或勾选清除则删除。Windows 使用 DPAPI；非 Windows 仅通过文件权限保护。

## 请求差异

| 项目 | Chat Completions | Responses | Messages |
|---|---|---|---|
| 默认路径 | `/chat/completions` | `/responses` | `/messages` |
| 输入 | `messages` | `input` | 顶层 `system` + `messages` |
| 默认长度字段 | `max_tokens` | `max_output_tokens` | `max_tokens` |
| JSON 模式 | `response_format` | `text.format` | 通过文本指令约束 |
| 默认认证 | Bearer | Bearer | `x-api-key` + `anthropic-version` |

部分渠道的 Chat 模型要求 `max_completion_tokens`。在输出长度字段中选择它即可，不必重复放入额外 JSON。显式填写在额外 JSON 中的长度字段具有更高优先级，程序会移除其他长度字段以避免冲突。

温度默认不发送，原生 JSON 模式默认关闭，适合能力不完全一致的兼容渠道。即使原生 JSON 模式关闭，提示词仍要求 JSON，且程序会校验其内容。遇到不支持参数的错误，应依据渠道文档关闭相应选项，不会静默切换服务或模型。

额外请求体示例（仅在该渠道支持时使用）：

```json
{"reasoning_effort":"xhigh"}
```

Responses 的对应形式可能为：

```json
{"reasoning":{"effort":"xhigh"}}
```

参数名和支持的强度由所选模型与渠道决定。禁止覆盖 model、消息、input、工具和 stream 等工作流字段。程序使用非流式响应，不执行模型工具。

## 官方 API 与本地模型

OpenAI 官方 API 的基础地址为 `https://api.openai.com/v1`，使用其支持的 Chat 或 Responses 协议，需要独立 API 凭据。参阅[官方 API 文档](https://developers.openai.com/api/docs)。本机 Codex 模式单独通过 CLI 的 ChatGPT 登录运行，不把该登录当成 API Key。

本地服务若实现 OpenAI 兼容接口，可使用它提供的 `http://127.0.0.1:端口/v1` 地址，填写已加载的模型 ID，按实际配置选择无认证或 API Key。模型需有足够的中英文翻译能力、上下文和 JSON 输出能力。

## 排错

| 现象 | 检查方式 |
|---|---|
| 401 / 403 | 检查密钥、认证头、模型访问权限和网关要求 |
| 404 | 核对 API 地址和路由，尝试完整地址原样使用；聊天网页地址不能作为 API |
| 参数不支持 | 关闭 JSON 模式或 temperature，核对长度字段及额外 JSON |
| 429 | 等待额度恢复，降低批次并检查渠道限额；自动重试不会创造额度 |
| 响应截断 / 空输出 | 减小每批段落数或提高输出上限；推理 token 也可能占用预算 |
| JSON 解析失败 | 确认协议匹配、模型可遵循 JSON 指令；尝试原生 JSON 模式 |
| 超时 / 连接失败 | 检查渠道连通性、代理、超时设置；不支持自动跟随重定向 |

默认最多重试两次，针对超时、连接问题、408 / 429 / 部分 5xx。API 模式暂停在当前请求完成后生效。

兼容性经过本地协议模拟测试；没有为所有第三方服务逐一开通付费账号。专有签名、OAuth 授权、流式专用接口和私有响应格式需要额外适配。
