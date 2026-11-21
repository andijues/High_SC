from __future__ import annotations

import json
import re
import time
from urllib.parse import parse_qsl, urlparse, urlunparse

import httpx


class ModelError(RuntimeError):
    pass


class OutputTooLong(ModelError):
    batch_too_large=True


def parse_json(text: str):
    text = text.strip().removeprefix("\ufeff")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        if start >= 0:
            try:
                value, _ = json.JSONDecoder().raw_decode(text[start:])
                return value
            except json.JSONDecodeError:
                pass
    raise ModelError("模型没有返回有效 JSON。请换用支持 JSON 指令的模型，或在设置中开启 JSON 模式后重试")


def validate_connection(config):
    if config.get('api_style')=='codex':
        if not config.get('model','').strip():raise ModelError('请填写模型名称')
        from .codex_client import codex_status
        status=codex_status(config)
        if not status['chatgpt_login']:raise ModelError(status['message'])
        return
    url = urlparse(config.get("base_url", ""))
    if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.fragment:
        raise ModelError("请填写有效 API 地址；不要在地址中包含账户、密码或片段标记")
    if any(re.sub(r'[-_]', '', k.lower()) in {'key','apikey','token','accesstoken','authorization','secret','password','signature','sig','credential'} for k, _ in parse_qsl(url.query)):
        raise ModelError("请将密钥放入 API 密钥或自定义请求头；地址查询参数仅用于 api-version 等非敏感配置")
    if not config.get("model", "").strip():
        raise ModelError("请填写模型名称")
    if url.hostname == 'api.openai.com' and not config.get('api_key','').strip():
        raise ModelError('官方 OpenAI API 需要 API Key。请在 API 设置中填写并保存密钥后再测试')
    validate_headers(config.get('extra_headers') or {})


def endpoint(base: str, style: str, mode="auto") -> str:
    if mode == 'exact': return base
    parsed = urlparse(base)
    base = parsed.path.rstrip("/")
    routes = {"chat": "/chat/completions", "responses": "/responses", "anthropic": "/messages"}
    route = routes[style]
    if base.endswith(route):
        return urlunparse(parsed._replace(path=base))
    for tail in routes.values():
        if base.endswith(tail):
            base = base[:-len(tail)]
            break
    return urlunparse(parsed._replace(path=base + route))


def validate_headers(headers):
    if not isinstance(headers, dict) or len(headers) > 32:
        raise ModelError('自定义请求头必须是最多 32 项的 JSON 对象')
    forbidden = {'host','content-length','content-type','connection','transfer-encoding','proxy-authorization','cookie','accept-encoding'}
    for name, value in headers.items():
        if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) or name.lower() in forbidden:
            raise ModelError('自定义请求头名称无效或涉及传输控制，请使用服务商规定的认证或标识头')
        if not isinstance(value, str) or any(ord(c) < 32 or ord(c) > 126 for c in value):
            raise ModelError('请求头值必须是可打印 ASCII 字符串，不允许换行')


def request_headers(cfg):
    headers = httpx.Headers({'Content-Type':'application/json'})
    key = cfg.get('api_key','')
    auth = cfg.get('auth_mode','auto')
    if auth == 'auto': auth = 'x-api-key' if cfg['api_style'] == 'anthropic' else 'bearer'
    if key and auth == 'bearer': headers['Authorization'] = 'Bearer ' + key
    elif key and auth != 'none': headers[auth] = key
    if cfg['api_style'] == 'anthropic': headers['anthropic-version'] = '2023-06-01'
    for name, value in (cfg.get('extra_headers') or {}).items():
        headers[name] = value.replace('${API_KEY}', key)
    return headers


def redact(cfg, text):
    values = [cfg.get('api_key',''), cfg.get('proxy','')]
    for value in (cfg.get('extra_headers') or {}).values():
        values.extend([value, value.replace('${API_KEY}', cfg.get('api_key',''))])
    for secret in sorted(set(values), key=len, reverse=True):
        if secret: text = text.replace(secret, '[敏感配置已隐藏]')
    # Exceptions may include URLs; do not echo query values into task logs.
    return re.sub(r'([?&][A-Za-z0-9_-]+=)[^\s&\"<>]+', r'\1[隐藏]', text)


class ModelClient:
    def __init__(self, config, usage_callback=None, cancel_check=None, request_callback=None):
        self.config = config
        self.usage_callback = usage_callback or (lambda _: None)
        self.cancel_check = cancel_check or (lambda: None)
        self.request_callback = request_callback or (lambda _: None)
        validate_connection(config)

    def request(self, system, payload, expect_json=True, small=False):
        cfg = self.config
        style = cfg["api_style"]
        content = json.dumps(payload, ensure_ascii=False) if not isinstance(payload, str) else payload
        event={'task':payload.get('task','') if isinstance(payload,dict) else '',
               'input_chars':len(system)+len(content),
               'paragraphs':len(payload.get('paragraphs',[])) if isinstance(payload,dict) else 0,
               'context_chars':len(json.dumps(payload.get('global_outline',{}),ensure_ascii=False)) if isinstance(payload,dict) else 0}
        if style=='codex':
            from .codex_client import request
            self.request_callback(event)
            if cfg.get('adaptive_batching',True) and event['task']=='annotate' and event['paragraphs']>4:
                cfg={**cfg,'timeout':min(1800,int(cfg['timeout']*min(2,event['paragraphs']/4)))}
            return request(cfg,system,payload,expect_json,self.usage_callback,self.cancel_check)
        headers = request_headers(cfg)
        reasoning_requested = bool(cfg.get('extra_body', {}).get('reasoning') or cfg.get('extra_body', {}).get('reasoning_effort'))
        # Reasoning tokens share the output budget. A 300-token probe can be
        # truncated before emitting JSON even when credentials/model are valid.
        tokens = min(cfg["max_tokens"], 300) if small and style != 'responses' and not reasoning_requested else cfg["max_tokens"]
        messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]
        if style == "responses":
            body = {"model": cfg["model"], "input": messages, "max_output_tokens": tokens}
            if cfg.get("json_mode") and expect_json:
                body["text"] = {"format": {"type": "json_object"}}
        elif style == "anthropic":
            body = {"model": cfg["model"], "system": system, "messages": messages[1:], "max_tokens": tokens}
        else:
            body = {"model": cfg["model"], "messages": messages, "max_tokens": tokens}
            if cfg.get("json_mode") and expect_json:
                body["response_format"] = {"type": "json_object"}
        if cfg.get("send_temperature"):
            body["temperature"] = cfg["temperature"]
        token_field = cfg.get('token_field','auto')
        if token_field != 'auto':
            for field in ('max_tokens','max_completion_tokens','max_output_tokens'): body.pop(field, None)
            if token_field != 'omit': body[token_field] = tokens
        extras = cfg.get("extra_body", {})
        reserved = {"model", "messages", "system", "input", "stream", "tools", "tool_choice"}
        if reserved & extras.keys():
            raise ModelError("额外参数不能覆盖 model、messages、input、stream 或 tools 等工作流字段")
        if len({'max_tokens','max_completion_tokens','max_output_tokens'} & extras.keys()) > 1:
            raise ModelError('额外参数中只能指定一种输出 token 字段')
        if {'max_tokens','max_completion_tokens','max_output_tokens'} & extras.keys():
            for field in ('max_tokens','max_completion_tokens','max_output_tokens'): body.pop(field, None)
        body.update(extras)
        body["stream"] = False
        url = endpoint(cfg["base_url"], style, cfg.get('endpoint_mode','auto'))
        for attempt in range(cfg["retries"] + 1):
            self.cancel_check()
            try:
                with httpx.Client(timeout=httpx.Timeout(cfg["timeout"], connect=min(30,cfg["timeout"])), proxy=cfg.get("proxy") or None, follow_redirects=False) as client:
                    self.request_callback(event)
                    response = client.post(url, headers=headers, json=body)
                if response.status_code >= 400 or 300 <= response.status_code < 400:
                    detail = redact(cfg, response.text)[:900]
                    if response.status_code in {408, 429, 500, 502, 503, 504} and attempt < cfg["retries"]:
                        self._backoff(attempt)
                        continue
                    raise ModelError(f"模型服务返回 HTTP {response.status_code}：{detail}。请核对接口协议、地址、模型和权限")
                result = response.json()
                if not isinstance(result, dict): raise ModelError('接口响应必须是 JSON 对象，请核对所选协议')
                if result.get('error'):
                    raise ModelError('模型服务返回错误：' + redact(cfg, json.dumps(result['error'],ensure_ascii=False))[:600])
                if style == "responses":
                    if result.get("status") == "incomplete":
                        raise OutputTooLong("模型响应被截断，请提高输出上限或减小每批段落数")
                    text = result.get("output_text") or "".join(c.get("text", "") for o in result.get("output", []) for c in o.get("content", []) if c.get("type") == "output_text")
                elif style == "anthropic":
                    if result.get("stop_reason") == "max_tokens":
                        raise OutputTooLong("模型响应被截断，请提高输出上限或减小每批段落数")
                    text = "".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
                else:
                    choice = (result.get("choices") or [{}])[0]
                    if choice.get("finish_reason") == "length":
                        raise OutputTooLong("模型响应被截断，请提高输出上限或减小每批段落数")
                    message = choice.get("message", {})
                    if message.get("refusal"):
                        raise ModelError("模型拒绝处理该输入，请检查返回说明或更换模型")
                    text = message.get("content", "")
                    if isinstance(text, list): text = "".join(c.get("text", "") for c in text)
                self.usage_callback(result.get("usage", {}))
                self.cancel_check()
                if not text:
                    raise ModelError("模型返回空内容，请检查模型设置或提高输出 token 上限")
                return parse_json(text) if expect_json else text
            except (httpx.HTTPError, ValueError) as exc:
                if attempt < cfg["retries"]:
                    self._backoff(attempt)
                    continue
                detail = redact(cfg, str(exc))
                raise ModelError(f"连接或解析模型服务失败：{detail[:400]}。可在 API 设置中调整超时或代理") from None
        raise ModelError("模型调用未完成")

    def _backoff(self, attempt):
        for _ in range(min(12, 2 ** (attempt + 1)) * 4):
            self.cancel_check()
            time.sleep(.25)

    def test(self):
        result = self.request("Return a JSON object only. Do not add Markdown.", {"task": "test", "instruction": "Reply with {\"ok\":true}."}, small=True)
        if result.get("ok") is not True:
            raise ModelError("接口已响应，但未通过 JSON 指令测试；请更换模型或开启 JSON 模式")
        message=f"本机 Codex 实际调用通过：{self.config['model']} / {self.config.get('codex_effort','xhigh')}（ChatGPT 登录）" if self.config['api_style']=='codex' else "连接与 JSON 输出测试通过"
        return {"ok": True, "message": message}
