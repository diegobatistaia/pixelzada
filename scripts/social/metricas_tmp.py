"""Leitura única das métricas do @pixelzada.br (temporário, branch de diagnóstico)."""
import json, os, sys, time
from scripts.social.instagram import call, conta, ApiError

token, ig = conta()
out = {"conta": {}, "media": [], "stories": [], "erros": []}

def tenta(rotulo, fn):
    try:
        return fn()
    except ApiError as e:
        out["erros"].append(f"{rotulo}: {e}")
        return None

out["conta"]["perfil"] = tenta("perfil", lambda: call("GET", "me", token,
    fields="username,followers_count,follows_count,media_count"))

agora = int(time.time())
desde = agora - 28 * 86400
for metr, extra in [
    ("reach", {"breakdown": "follow_type"}),
    ("views", {"breakdown": "follow_type"}),
    ("reach", {"breakdown": "media_product_type"}),
    ("views", {"breakdown": "media_product_type"}),
    ("accounts_engaged", {}), ("profile_views", {}), ("total_interactions", {"breakdown": "media_product_type"}),
    ("follows_and_unfollows", {"breakdown": "follow_type"}), ("likes", {}), ("shares", {}), ("saves", {}), ("comments", {}),
    ("profile_links_taps", {"breakdown": "contact_button_type"}),
]:
    chave = metr + ("_" + extra.get("breakdown", "") if extra else "")
    out["conta"][chave] = tenta(chave, lambda: call("GET", f"{ig}/insights", token, metric=metr,
        period="day", metric_type="total_value", since=desde, until=agora, **extra).get("data"))
out["conta"]["follower_count_dia"] = tenta("follower_count", lambda: call("GET", f"{ig}/insights", token,
    metric="follower_count", period="day", since=agora - 29 * 86400, until=agora).get("data"))
out["conta"]["reach_dia"] = tenta("reach_dia", lambda: call("GET", f"{ig}/insights", token,
    metric="reach", period="day", since=desde, until=agora).get("data"))
for b in ["age,gender", "city", "country"]:
    out["conta"]["publico_" + b] = tenta("publico " + b, lambda: call("GET", f"{ig}/insights", token,
        metric="follower_demographics", period="lifetime", metric_type="total_value", timeframe="this_month", breakdown=b).get("data"))

campos = "id,caption,permalink,timestamp,media_type,media_product_type,like_count,comments_count"
media, url = [], f"{ig}/media"
params = {"fields": campos, "limit": 100}
while url and len(media) < 600:
    r = tenta("lista", lambda: call("GET", url, token, **params))
    if not r: break
    media += r.get("data", [])
    url = (r.get("paging") or {}).get("next")
    params = {}
    if url:  # next já traz token e campos; call() acrescenta o token de novo, sem problema
        url = url.split("&access_token")[0]

REEL = ["reach", "views", "likes", "comments", "shares", "saved", "total_interactions",
        "ig_reels_avg_watch_time", "ig_reels_video_view_total_time", "reels_skip_rate", "follows", "profile_visits"]
FEED = ["reach", "views", "likes", "comments", "shares", "saved", "total_interactions", "follows", "profile_visits"]
for m in media:
    lista = REEL if m.get("media_product_type") == "REELS" else FEED
    ins = {}
    try:
        d = call("GET", f"{m['id']}/insights", token, metric=",".join(lista)).get("data", [])
        ins = {x["name"]: (x.get("values") or [{}])[0].get("value", x.get("total_value", {}).get("value")) for x in d}
    except ApiError:
        for k in lista:
            try:
                d = call("GET", f"{m['id']}/insights", token, metric=k).get("data", [])
                for x in d:
                    ins[x["name"]] = (x.get("values") or [{}])[0].get("value")
            except ApiError as e:
                ins[k] = "ERRO " + str(e)[:160]
    m["insights"] = ins
    if m.get("caption"):
        m["caption"] = m["caption"][:400]
    out["media"].append(m)

st = tenta("stories", lambda: call("GET", f"{ig}/stories", token, fields="id,timestamp,permalink,media_type").get("data", [])) or []
for s in st:
    try:
        d = call("GET", f"{s['id']}/insights", token, metric="reach,views,replies,shares,total_interactions,follows,profile_visits,navigation").get("data", [])
        s["insights"] = {x["name"]: (x.get("values") or [{}])[0].get("value", x.get("total_value")) for x in d}
    except ApiError as e:
        s["insights"] = "ERRO " + str(e)[:200]
    out["stories"].append(s)

os.makedirs("saida", exist_ok=True)
json.dump(out, open("saida/metricas.json", "w"), ensure_ascii=False, indent=1)
print(f"posts: {len(out['media'])}, stories: {len(out['stories'])}, erros: {len(out['erros'])}")
for e in out["erros"]:
    print("ERRO", e)
