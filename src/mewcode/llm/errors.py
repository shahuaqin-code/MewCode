"""Never expose SDK exception bodies: compatible servers may echo credentials."""


def safe_error(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    if status in (401, 403):
        return "鉴权失败，请检查密钥与访问权限。"
    if status == 429:
        return "请求被限流，请稍后重新发送。"
    if status == 404:
        return "模型或端点不存在，请检查配置。"
    if status is not None:
        return "服务拒绝了请求，请检查模型、参数或服务状态。"
    return "请求未完成，请检查网络连接与服务状态后重新发送。"
