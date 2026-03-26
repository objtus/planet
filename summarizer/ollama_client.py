"""Ollama HTTP API（/api/generate）。"""

import sys

import requests


def generate_text(base_url: str, model: str, prompt: str, *, timeout_sec: float = 600.0) -> str:
    """
    stream=false で 1 本の応答を返す。
    失敗時は stderr にメッセージを書き、呼び出し元で sys.exit する想定で例外を投げる。
    """
    url = base_url.rstrip("/") + "/api/generate"
    try:
        r = requests.post(
            url,
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=timeout_sec,
        )
    except requests.RequestException as e:
        print(f"Ollama 接続エラー: {e}", file=sys.stderr)
        raise

    if not r.ok:
        snippet = (r.text or "")[:500]
        print(f"Ollama HTTP {r.status_code}: {snippet}", file=sys.stderr)
        if r.status_code == 404 and "not found" in snippet.lower():
            print(
                f"ヒント: モデルが未導入か名前が違います。"
                f" `ollama pull {model}` を試すか、`ollama list` の名前に合わせて "
                "`config/settings.toml` の [ollama] model を変更してください。",
                file=sys.stderr,
            )
        r.raise_for_status()

    try:
        data = r.json()
    except ValueError as e:
        print("Ollama 応答が JSON ではありません", file=sys.stderr)
        raise

    text = data.get("response")
    if text is None or not isinstance(text, str):
        print(f"Ollama 応答に 'response' フィールドがありません: {data!r}", file=sys.stderr)
        raise ValueError("invalid ollama response")
    return text.strip()
