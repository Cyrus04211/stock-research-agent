"""
DeepSeek API 客户端 — OpenAI 兼容格式
"""
import openai
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL


def get_client() -> openai.OpenAI:
    """获取 DeepSeek API 客户端"""
    return openai.OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
    )


def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    temperature: float = 0.6,
    max_tokens: int = 8192,
) -> str:
    """
    调用 DeepSeek LLM，返回分析文本
    """
    client = get_client()
    response = client.chat.completions.create(
        model=model or DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content
