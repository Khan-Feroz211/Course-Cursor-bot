import base64
import io
import json
import logging
import os

import httpx
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")


def _extract_json(text: str) -> dict:
    s = text.strip()
    if s.startswith("```json"):
        s = s[7:].strip()
    if s.startswith("```"):
        s = s[3:].strip()
    if s.endswith("```"):
        s = s[:-3].strip()
    return json.loads(s)


async def generate_chart(prompt, chart_type, title, xlabel, ylabel) -> dict:
    try:
        system = (
            "Extract chart data. Return ONLY valid JSON, no markdown: "
            "{chart_type, title, xlabel, ylabel, datasets:[{label, x:[], y:[]}]}"
        )
        user = (
            f"Prompt: {prompt}\n"
            f"chart_type: {chart_type}\n"
            f"title: {title}\n"
            f"xlabel: {xlabel}\n"
            f"ylabel: {ylabel}"
        )
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)) as client:
            res = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "stream": False,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                },
            )
        if res.status_code != 200:
            return {"error": "AI model is unavailable"}
        data = res.json()
        raw = data.get("message", {}).get("content", "")
        parsed = _extract_json(raw)

        ctype = (parsed.get("chart_type") or chart_type or "line").lower()
        ptitle = parsed.get("title") or title or "Chart"
        px = parsed.get("xlabel") or xlabel or "X"
        py = parsed.get("ylabel") or ylabel or "Y"
        datasets = parsed.get("datasets") or []
        if not datasets:
            return {"error": "No chart data found in prompt"}

        plt.style.use("seaborn-v0_8-whitegrid")
        plt.rcParams["font.family"] = "serif"
        fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
        colors = ["#0F4C81", "#F59E0B", "#10B981", "#EF4444", "#8B5CF6"]

        for i, ds in enumerate(datasets):
            x = ds.get("x", [])
            y = ds.get("y", [])
            label = ds.get("label", f"Series {i + 1}")
            color = colors[i % len(colors)]
            if ctype == "bar":
                bars = ax.bar(x, y, label=label, color=color, alpha=0.9)
                for bar in bars:
                    h = bar.get_height()
                    ax.text(bar.get_x() + bar.get_width() / 2, h, f"{h}", ha="center", va="bottom", fontsize=8)
            elif ctype == "scatter":
                ax.scatter(x, y, label=label, color=color, s=60, marker="o")
            elif ctype in {"pie", "doughnut"}:
                wedges, *_ = ax.pie(
                    y,
                    labels=x,
                    colors=colors[: len(y)],
                    autopct="%1.1f%%",
                    wedgeprops={"width": 0.45} if ctype == "doughnut" else None,
                )
                if label:
                    ax.legend(wedges, x, loc="center left", bbox_to_anchor=(1, 0.5))
                break
            else:
                ax.plot(x, y, label=label, color=color, marker="o", linewidth=2)

        ax.set_title(ptitle, fontweight="bold")
        if ctype not in {"pie", "doughnut"}:
            ax.set_xlabel(px)
            ax.set_ylabel(py)
            if len(datasets) > 1:
                ax.legend()
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor="white")
        plt.close(fig)
        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return {"image": img_b64, "title": ptitle}
    except (httpx.ReadTimeout, httpx.TimeoutException):
        logger.warning("Graph generation timed out — Ollama too slow")
        return {"error": "AI is taking too long to respond. The model may be warming up — please try again in 30 seconds."}
    except Exception as exc:
        logger.exception("Graph generation error")
        return {"error": str(exc)}
