"""TEMPORÁRIO: puxa métricas completas do @pixelzada.br (14 dias) e grava JSON."""
import json, sys, time
from datetime import datetime, timedelta, timezone
sys.path.insert(0, ".")
from scripts.social import instagram as IG

token, ig = IG.conta()
agora = datetime.now(timezone.utc)
out = {"puxado_em": agora.isoformat(), "erros": []}
def tenta(nome, f):
    try:
        return f()
    except Exception as e:
        out["erros"].append(f"{nome}: {e}")
        return None

out["perfil"] = tenta("perfil", lambda: IG.call("GET", ig, token, fields="username,followers_count,follows_count,media_count,biography"))
out["limite_publicacao"] = tenta("limite", lambda: IG.call("GET", f"{ig}/content_publishing_limit", token, fields="config,quota_usage"))
# Conta por dia (BRT: dia começa 03:00 UTC)
dias = {}
TOT = "views,reach,accounts_engaged,total_interactions,likes,comments,shares,saves,follows_and_unfollows,profile_links_taps"
for i in range(15, -1, -1):
    ini = (agora - timedelta(days=i)).replace(hour=3, minute=0, second=0, microsecond=0)
    fim = ini + timedelta(days=1)
    if ini > agora: continue
    d = ini.date().isoformat(); dias[d] = {}
    for grupo in (TOT, "follows_and_unfollows"):
        r = tenta(f"conta {d} {grupo[:20]}", lambda: IG.call("GET", f"{ig}/insights", token, metric=grupo, period="day", metric_type="total_value", since=int(ini.timestamp()), until=int(min(fim, agora).timestamp())))
        for m in (r or {}).get("data", []):
            tv = m.get("total_value") or {}
            dias[d][m["name"]] = tv.get("value")
    r = tenta(f"conta {d} fu", lambda: IG.call("GET", f"{ig}/insights", token, metric="follows_and_unfollows", period="day", metric_type="total_value", breakdown="follow_type", since=int(ini.timestamp()), until=int(min(fim, agora).timestamp())))
    for m in (r or {}).get("data", []):
        for b in (m.get("total_value") or {}).get("breakdowns", []):
            for res in b.get("results", []):
                dias[d]["fu_" + "_".join(res.get("dimension_values", []))] = res.get("value")
out["conta_por_dia"] = dias
out["follower_count"] = tenta("follower_count", lambda: IG.call("GET", f"{ig}/insights", token, metric="follower_count", period="day", since=int((agora-timedelta(days=28)).timestamp()), until=int(agora.timestamp())))
out["reach_media_type"] = tenta("reach breakdown", lambda: IG.call("GET", f"{ig}/insights", token, metric="reach", period="day", metric_type="total_value", breakdown="media_product_type,follow_type", since=int((agora-timedelta(days=7)).timestamp()), until=int(agora.timestamp())))
out["views_media_type"] = tenta("views breakdown", lambda: IG.call("GET", f"{ig}/insights", token, metric="views", period="day", metric_type="total_value", breakdown="media_product_type,follow_type", since=int((agora-timedelta(days=7)).timestamp()), until=int(agora.timestamp())))
for dem in ("follower_demographics", "engaged_audience_demographics", "reached_audience_demographics"):
    out[dem] = {}
    for bd in ("age", "gender", "city", "country"):
        out[dem][bd] = tenta(f"{dem} {bd}", lambda: IG.call("GET", f"{ig}/insights", token, metric=dem, period="lifetime", metric_type="total_value", timeframe="this_week" if dem != "follower_demographics" else "this_month", breakdown=bd))
out["online_followers"] = tenta("online", lambda: IG.call("GET", f"{ig}/insights", token, metric="online_followers", period="lifetime", since=int((agora-timedelta(days=2)).timestamp()), until=int((agora-timedelta(days=1)).timestamp())))
# Mídias 14 dias
midias, params, url = [], {"fields": "id,media_type,media_product_type,timestamp,permalink,caption,like_count,comments_count", "limit": 100}, f"{ig}/media"
limite = agora - timedelta(days=14)
for _ in range(15):
    r = tenta("media", lambda: IG.call("GET", url, token, **params))
    if not r: break
    velho = False
    for m in r.get("data", []):
        if datetime.fromisoformat(m["timestamp"].replace("+0000", "+00:00")) < limite: velho = True; continue
        midias.append(m)
    after = (r.get("paging") or {}).get("cursors", {}).get("after")
    if velho or not after or not (r.get("paging") or {}).get("next"): break
    params = dict(params, after=after)
MET = "views,reach,likes,comments,shares,saved,total_interactions,ig_reels_avg_watch_time,ig_reels_video_view_total_time"
for m in midias:
    met = MET if m.get("media_product_type") == "REELS" else "views,reach,likes,comments,shares,saved,total_interactions"
    r = tenta(f"ins {m['id']}", lambda: IG.call("GET", f"{m['id']}/insights", token, metric=met))
    m["insights"] = {x["name"]: (x.get("values") or [{}])[0].get("value") for x in (r or {}).get("data", [])}
    for extra in ("follows", "profile_visits", "reposts", "crossposted_views", "facebook_views"):
        try:
            r = IG.call("GET", f"{m['id']}/insights", token, metric=extra)
            for x in r.get("data", []):
                m["insights"][x["name"]] = (x.get("values") or [{}])[0].get("value")
        except Exception:
            pass
out["midias"] = midias
json.dump(out, open("tmp-metricas/metricas.json", "w"), ensure_ascii=False, indent=1)
print(len(midias), "mídias;", len(out["erros"]), "erros")
for e in out["erros"][:30]: print(e)
