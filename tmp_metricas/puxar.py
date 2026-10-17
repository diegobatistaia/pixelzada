"""Temporário: puxa métricas do @pixelzada.br para o dashboard (removido depois)."""
import json, sys, time, datetime as dt
from scripts.social.instagram import call, conta, ApiError

token, uid = conta()
out = {"gerado_em": dt.datetime.utcnow().isoformat() + "Z", "erros": []}

def tenta(nome, fn):
    try:
        return fn()
    except ApiError as e:
        out["erros"].append(f"{nome}: {e}")
        return None

out["perfil"] = tenta("perfil", lambda: call("GET", uid, token, fields="username,followers_count,follows_count,media_count"))

def ts(d):  # meia-noite BRT (03:00 UTC)
    return int(dt.datetime(d.year, d.month, d.day, 3, tzinfo=dt.timezone.utc).timestamp())

hoje = dt.date(2026, 10, 17)
janelas = {
    "total": (dt.date(2026, 10, 8), hoje + dt.timedelta(days=1)),
    "sem1": (dt.date(2026, 10, 8), dt.date(2026, 10, 15)),
    "pos15": (dt.date(2026, 10, 15), hoje + dt.timedelta(days=1)),
}
tot = {}
for jn, (a, b) in janelas.items():
    tot[jn] = {}
    for met, bd in [("reach", "follow_type"), ("reach", "media_product_type"), ("views", "follow_type"), ("views", "media_product_type"),
                    ("total_interactions", "media_product_type"), ("accounts_engaged", None), ("profile_views", None),
                    ("likes", None), ("shares", None), ("saves", None), ("comments", None), ("follows_and_unfollows", "follow_type"),
                    ("profile_links_taps", None)]:
        p = dict(metric=met, period="day", metric_type="total_value", since=ts(a), until=ts(b))
        if bd: p["breakdown"] = bd
        r = tenta(f"{jn}/{met}/{bd}", lambda: call("GET", f"{uid}/insights", token, **p))
        tot[jn][f"{met}|{bd}"] = (r or {}).get("data")
out["totais"] = tot

out["serie"] = {}
for met in ["reach", "follower_count"]:
    r = tenta(f"serie/{met}", lambda: call("GET", f"{uid}/insights", token, metric=met, period="day",
                                          since=ts(dt.date(2026, 10, 8)), until=ts(hoje)))
    out["serie"][met] = (r or {}).get("data")
for bd in ["age", "gender", "city", "country"]:
    r = tenta(f"publico/{bd}", lambda: call("GET", f"{uid}/insights", token, metric="engaged_audience_demographics",
                                           period="lifetime", timeframe="this_month", metric_type="total_value", breakdown=bd))
    out.setdefault("publico", {})[bd] = (r or {}).get("data")

campos = "id,caption,permalink,timestamp,media_type,media_product_type,like_count,comments_count"
media, url = [], f"{uid}/media"
pars = dict(fields=campos, limit=50)
while url:
    r = tenta("media", lambda: call("GET", url, token, **pars))
    if not r: break
    media += r.get("data", [])
    url = r.get("paging", {}).get("next")
    pars = {}
    if url and "access_token" in url:  # call() põe o token de novo
        import urllib.parse as up
        u = up.urlparse(url); q = dict(up.parse_qsl(u.query)); q.pop("access_token", None)
        url = f"{u.scheme}://{u.netloc}{u.path}"; pars = q

for m in media:
    m["caption"] = (m.get("caption") or "")[:200]
    if m["media_product_type"] == "REELS":
        mets = "reach,views,likes,comments,shares,saved,total_interactions,ig_reels_avg_watch_time,ig_reels_video_view_total_time,reels_skip_rate"
    else:
        mets = "reach,views,likes,comments,shares,saved,total_interactions,follows,profile_visits"
    r = tenta(f"media/{m['id']}", lambda: call("GET", f"{m['id']}/insights", token, metric=mets))
    m["insights"] = {x["name"]: x["values"][0]["value"] for x in (r or {}).get("data", [])}
out["media"] = media

st = tenta("stories", lambda: call("GET", f"{uid}/stories", token, fields="id,timestamp,permalink,media_type"))
stories = (st or {}).get("data", [])
for s in stories:
    r = tenta(f"story/{s['id']}", lambda: call("GET", f"{s['id']}/insights", token,
                                              metric="reach,views,replies,shares,total_interactions,follows,profile_visits,navigation"))
    s["insights"] = {x["name"]: x["values"][0]["value"] for x in (r or {}).get("data", [])}
out["stories"] = stories

json.dump(out, open("tmp_metricas/metricas-2026-10-17.json", "w"), ensure_ascii=False, indent=1)
print(f"ok: {len(media)} posts, {len(stories)} stories, {len(out['erros'])} erros")
