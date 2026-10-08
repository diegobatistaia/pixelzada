"""Load and validate site.config.yaml.

Every niche-specific value in the engine comes through here. If a module needs
a constant that would differ between sites, it belongs in the config file, not
in the code.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "site.config.yaml"

REQUIRED = ["site", "niche", "sources", "keywords", "quality_gate", "editorial", "publishing"]


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    data: dict
    path: Path

    # -- generic access ----------------------------------------------------
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def require(self, dotted: str) -> Any:
        value = self.get(dotted, None)
        if value in (None, ""):
            raise ConfigError(f"{self.path.name}: '{dotted}' está vazio e é obrigatório")
        return value

    def localized(self, dotted: str, lang: str, default: Any = None) -> Any:
        """Read a {pt:..., en:..., es:...} block for one language."""
        value = self.get(dotted, default)
        if isinstance(value, dict):
            return value.get(lang, value.get(self.default_language, default))
        return value

    # -- shortcuts ---------------------------------------------------------
    @property
    def languages(self) -> list[str]:
        return list(self.get("site.languages", ["pt"]))

    @property
    def default_language(self) -> str:
        return self.get("site.default_language", self.languages[0])

    @property
    def base_url(self) -> str:
        return str(self.get("site.base_url", "")).rstrip("/")

    def url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def categories(self, lang: str) -> list[dict]:
        """Editorias válidas para um idioma.

        Uma editoria pode declarar `languages: [pt]` e existir só naquela
        edição. Traduzir o rótulo não resolve o caso regional: uma seção sobre
        o Brasil não pertence à edição em inglês, com rótulo nenhum.
        """
        out = []
        for cat in self.get("editorial.categories", []):
            allowed = cat.get("languages")
            if allowed and lang not in allowed:
                continue
            out.append({
                "slug": cat["slug"].get(lang, cat["slug"][self.default_language]),
                "label": cat["label"].get(lang, cat["label"][self.default_language]),
                "color": cat.get("color", self.get("brand.primary", "#3A4556")),
                "key": cat["slug"][self.default_language],
            })
        return out

    def category_or_fallback(self, key: str, lang: str) -> dict | None:
        """A editoria pedida, ou a de reserva quando ela não existe no idioma.

        Acontece quando uma pauta regional é escrita nos três idiomas: em pt ela
        é "IA no Brasil", e nas outras edições precisa ir para algum lugar.
        """
        found = self.category(key, lang)
        if found:
            return found
        fallback = self.get("editorial.fallback_category")
        return self.category(fallback, lang) if fallback else None

    def category(self, key: str, lang: str) -> dict | None:
        for cat in self.categories(lang):
            if cat["key"] == key:
                return cat
        return None

    def source(self, owner: str) -> dict | None:
        for src in self.get("sources.rss", []):
            if src.get("owner") == owner:
                return src
        return None

    # -- publishing ramp ---------------------------------------------------
    @property
    def run_hours(self) -> list[int]:
        """Horários (no fuso do site) em que a coleta roda a cada dia."""
        hours = self.get("publishing.run_hours") or [7]
        return sorted(int(h) for h in hours)

    def posts_per_language(self, today: date | None = None) -> int:
        """How many posts per language today's ramp phase allows."""
        launch = self.get("publishing.launch_date") or ""
        ramp = sorted(self.get("publishing.ramp", []), key=lambda r: r["from_day"])
        if not ramp:
            return 1
        if not launch:
            return ramp[0]["posts_per_language"]
        started = datetime.strptime(str(launch), "%Y-%m-%d").date()
        elapsed = ((today or date.today()) - started).days
        allowed = ramp[0]["posts_per_language"]
        for phase in ramp:
            if elapsed >= phase["from_day"]:
                allowed = phase["posts_per_language"]
        return allowed


def validate(data: dict, path: Path) -> None:
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        raise ConfigError(f"{path.name}: faltam as seções {missing}")

    languages = data["site"].get("languages") or []
    if not languages:
        raise ConfigError(f"{path.name}: site.languages não pode ser vazio")
    if data["site"].get("default_language") not in languages:
        raise ConfigError(f"{path.name}: site.default_language precisa estar em site.languages")

    for i, cat in enumerate(data["editorial"].get("categories", [])):
        # Uma editoria pode valer só para alguns idiomas; só exigimos slug e
        # label para aqueles em que ela de fato existe.
        cobre = cat.get("languages") or languages
        desconhecidos = [l for l in cobre if l not in languages]
        if desconhecidos:
            raise ConfigError(
                f"{path.name}: editorial.categories[{i}].languages cita {desconhecidos}, "
                "que não estão em site.languages")
        for field in ("slug", "label"):
            missing_langs = [l for l in cobre if l not in cat.get(field, {})]
            if missing_langs:
                raise ConfigError(
                    f"{path.name}: editorial.categories[{i}].{field} não cobre {missing_langs}")

    # Um bloco de conteudo repetido na home mostraria as mesmas materias duas
    # vezes e esconderia as mais novas. Anuncio e newsletter podem repetir.
    layout = data["editorial"].get("home_layout") or []
    repetidos = sorted({b for b in layout if layout.count(b) > 1
                        and b not in ("ad_between_blocks", "newsletter")})
    if repetidos:
        raise ConfigError(f"{path.name}: editorial.home_layout repete {repetidos}")
    theme = (data.get("brand") or {}).get("default_theme", "light")
    if theme not in ("light", "dark", "system"):
        raise ConfigError(f"{path.name}: brand.default_theme deve ser light, dark ou system")

    seen = set()
    for src in data.get("sources", {}).get("rss", []):
        for field in ("name", "url", "owner"):
            if not src.get(field):
                raise ConfigError(f"{path.name}: fonte RSS sem '{field}': {src}")
        seen.add(src["url"])
    if len(seen) != len(data["sources"]["rss"]):
        raise ConfigError(f"{path.name}: há URLs de RSS duplicadas em sources.rss")

    gate = data["quality_gate"]
    lo, hi = gate.get("word_count", {}).get("min"), gate.get("word_count", {}).get("max")
    if not lo or not hi or lo >= hi:
        raise ConfigError(f"{path.name}: quality_gate.word_count inválido")
    if gate.get("min_independent_sources", 0) < 2:
        raise ConfigError(
            f"{path.name}: quality_gate.min_independent_sources abaixo de 2 - "
            "a checagem cruzada de duas fontes independentes não é negociável")


@lru_cache(maxsize=1)
def load(path: str | Path = CONFIG_PATH) -> Config:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"configuração não encontrada: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    validate(data, path)
    return Config(data=data, path=path)


def bot_user_agent() -> str:
    """User-Agent dos robôs de coleta, montado a partir de `bot.user_agent`."""
    try:
        cfg = load()
    except ConfigError:
        return "Mozilla/5.0 (compatible; NewsBot/1.0)"
    agent = cfg.get("bot.user_agent") or f"{cfg.get('site.name', 'News')}Bot/1.0"
    return f"Mozilla/5.0 (compatible; {agent}; +{cfg.base_url})"


def utm_source() -> str:
    """Identificador do site em links de atribuição (ex.: Unsplash)."""
    try:
        return str(load().get("site.name", "site")).lower()
    except ConfigError:
        return "site"


if __name__ == "__main__":
    cfg = load()
    print(f"OK  {cfg.path.name}")
    print(f"    site      {cfg.get('site.name')} ({cfg.base_url})")
    print(f"    idiomas   {', '.join(cfg.languages)} (padrão: {cfg.default_language})")
    print(f"    fontes    {len(cfg.get('sources.rss', []))} feeds")
    print(f"    categorias{'':1}{len(cfg.categories(cfg.default_language))}")
    print(f"    ritmo hoje{'':1}{cfg.posts_per_language()} posts por idioma")
