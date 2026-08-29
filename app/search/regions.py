from app.search.models import RegionCode

_REGION_CODES = {"춘천": RegionCode.CHUNCHEON, "원주": RegionCode.WONJU, "강릉": RegionCode.GANGNEUNG, "동해": RegionCode.DONGHAE, "태백": RegionCode.TAEBAEK, "속초": RegionCode.SOKCHO, "삼척": RegionCode.SAMCHEOK, "홍천": RegionCode.HONGCHEON, "횡성": RegionCode.HOENGSEONG, "영월": RegionCode.YEONGWOL, "평창": RegionCode.PYEONGCHANG, "정선": RegionCode.JEONGSEON, "철원": RegionCode.CHEORWON, "화천": RegionCode.HWACHEON, "양구": RegionCode.YANGGU, "인제": RegionCode.INJE, "고성": RegionCode.GOSEONG, "양양": RegionCode.YANGYANG}

def region_code_for(region: str | None) -> RegionCode | None:
    if not region:
        return None
    normalized = region.strip().removesuffix("시").removesuffix("군")
    try:
        return RegionCode(normalized.upper())
    except ValueError:
        return _REGION_CODES.get(normalized)
