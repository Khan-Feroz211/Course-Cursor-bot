import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from api.auth import require_login
from core.graph_plotter import generate_chart

logger = logging.getLogger(__name__)
router = APIRouter()


class PlotPayload(BaseModel):
    prompt: str
    chart_type: str = "line"
    title: str = "Chart"
    xlabel: str = "X"
    ylabel: str = "Y"


@router.post("/plot")
async def plot_graph(request: Request, payload: PlotPayload):
    require_login(request)
    try:
        result = await generate_chart(
            prompt=payload.prompt,
            chart_type=payload.chart_type,
            title=payload.title,
            xlabel=payload.xlabel,
            ylabel=payload.ylabel,
        )
        if "error" in result:
            return {"error": result["error"]}
        return result
    except Exception as exc:
        logger.exception("Plot route failed")
        raise HTTPException(status_code=500, detail={"error": "Failed to generate graph", "detail": str(exc)})
