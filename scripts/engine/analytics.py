"""Metricas semanais de trafego - GA4 e Search Console.

Roda no GitHub Actions (tem internet) e escreve data/analytics.json, que a
Routine (sem saida para a web) le do mesmo jeito que le o briefing.json.

Credencial: variavel de ambiente GA_SEARCH_CONSOLE_CREDENTIALS com o JSON
inteiro da conta de servico (guardado como secret do repositorio, nunca no
codigo). A conta de servico precisa ter sido adicionada como leitora na
propriedade do GA4 e como usuaria no Search Console - isso e feito uma vez,
direto nos paineis do Google, nao por aqui.
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta
from urllib.parse import quote

import requests
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account

from .config import Config
from .util import isoformat, utcnow

CREDENTIALS_ENV = "GA_SEARCH_CONSOLE_CREDENTIALS"
SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
]
LANGUAGES = ("pt", "en", "es")


class AnalyticsError(Exception):
    pass


def _credentials():
    raw = os.environ.get(CREDENTIALS_ENV)
    if not raw:
        raise AnalyticsError(f"variável de ambiente {CREDENTIALS_ENV} não configurada")
    info = json.loads(raw)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    creds.refresh(GoogleAuthRequest())
    return creds


def _page_language(path: str) -> str | None:
    first = path.strip("/").split("/", 1)[0]
    return first if first in LANGUAGES else None


# ------------------------------------------------------------------- GA4 ---

def _ga4_call(creds, property_id: str, body: dict) -> dict:
    url = f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport"
    resp = requests.post(url, headers={"Authorization": f"Bearer {creds.token}"},
                          json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _ga4_report(creds, property_id: str, days: int) -> dict:
    date_range = [{"startDate": f"{days}daysAgo", "endDate": "today"}]

    totals_data = _ga4_call(creds, property_id, {
        "dateRanges": date_range,
        "metrics": [{"name": "activeUsers"}, {"name": "screenPageViews"},
                    {"name": "engagementRate"}, {"name": "averageSessionDuration"}],
    })
    trow = (totals_data.get("rows") or [{}])[0]
    tvals = trow.get("metricValues", [])
    totals = {
        "active_users": int(tvals[0]["value"]) if len(tvals) > 0 else 0,
        "page_views": int(tvals[1]["value"]) if len(tvals) > 1 else 0,
        "engagement_rate": round(float(tvals[2]["value"]), 4) if len(tvals) > 2 else 0.0,
        "avg_session_seconds": round(float(tvals[3]["value"]), 1) if len(tvals) > 3 else 0.0,
    }

    paged_data = _ga4_call(creds, property_id, {
        "dateRanges": date_range,
        "dimensions": [{"name": "pagePathPlusQueryString"}],
        "metrics": [{"name": "activeUsers"}, {"name": "screenPageViews"},
                    {"name": "engagementRate"}],
        "orderBys": [{"metric": {"metricName": "screenPageViews"}, "desc": True}],
        "limit": 5000,
    })
    rows = paged_data.get("rows", [])

    # Visualizacoes por pagina, para o bloco "Mais lidas" da home. O mesmo
    # artigo chega com ?ref=... de quem compartilhou: soma tudo na URL limpa.
    views_by_path: dict[str, int] = {}
    for r in rows:
        path = r["dimensionValues"][0]["value"].split("?", 1)[0].split("#", 1)[0]
        path = path if path.endswith("/") else f"{path}/"
        views_by_path[path] = views_by_path.get(path, 0) + int(r["metricValues"][1]["value"])

    top_pages = [{
        "path": r["dimensionValues"][0]["value"],
        "active_users": int(r["metricValues"][0]["value"]),
        "page_views": int(r["metricValues"][1]["value"]),
        "engagement_rate": round(float(r["metricValues"][2]["value"]), 4),
    } for r in rows[:20]]

    by_language: dict[str, dict] = {}
    for r in rows:
        lang = _page_language(r["dimensionValues"][0]["value"])
        if not lang:
            continue
        bucket = by_language.setdefault(lang, {"active_users": 0, "page_views": 0})
        bucket["active_users"] += int(r["metricValues"][0]["value"])
        bucket["page_views"] += int(r["metricValues"][1]["value"])

    return {"totals": totals, "top_pages": top_pages, "by_language": by_language,
            "views_by_path": dict(sorted(views_by_path.items(),
                                         key=lambda kv: kv[1], reverse=True))}


# --------------------------------------------------------- Search Console --

def _search_console_query(creds, site_url: str, start: date, end: date,
                           dimensions: list[str], row_limit: int) -> list[dict]:
    url = (f"https://www.googleapis.com/webmasters/v3/sites/{quote(site_url, safe='')}"
           "/searchAnalytics/query")
    body = {"startDate": start.isoformat(), "endDate": end.isoformat(),
            "dimensions": dimensions, "rowLimit": row_limit}
    resp = requests.post(url, headers={"Authorization": f"Bearer {creds.token}"},
                          json=body, timeout=30)
    resp.raise_for_status()
    return resp.json().get("rows", [])


def _search_console_report(creds, site_url: str, days: int) -> dict:
    end = utcnow().date()
    start = end - timedelta(days=days)

    totals_rows = _search_console_query(creds, site_url, start, end, [], row_limit=1)
    t = totals_rows[0] if totals_rows else {}
    totals = {
        "clicks": int(t.get("clicks", 0)),
        "impressions": int(t.get("impressions", 0)),
        "ctr": round(t.get("ctr", 0.0), 4),
        "avg_position": round(t.get("position", 0.0), 1),
    }

    top_queries = [{
        "query": r["keys"][0],
        "clicks": int(r.get("clicks", 0)),
        "impressions": int(r.get("impressions", 0)),
        "avg_position": round(r.get("position", 0.0), 1),
    } for r in _search_console_query(creds, site_url, start, end, ["query"], row_limit=20)]

    top_pages = [{
        "page": r["keys"][0],
        "clicks": int(r.get("clicks", 0)),
        "impressions": int(r.get("impressions", 0)),
    } for r in _search_console_query(creds, site_url, start, end, ["page"], row_limit=20)]

    return {"totals": totals, "top_queries": top_queries, "top_pages": top_pages}


# ------------------------------------------------------------------- run ---

def run(cfg: Config, days: int = 28) -> dict:
    property_id = str(cfg.require("analytics.ga4_property_id"))
    site_url = cfg.require("analytics.search_console_site")
    creds = _credentials()
    return {
        "generated_at": isoformat(utcnow()),
        "window_days": days,
        "ga4": _ga4_report(creds, property_id, days),
        "search_console": _search_console_report(creds, site_url, days),
    }
