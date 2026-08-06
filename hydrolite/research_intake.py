from hydrolite.research_registry import built_in_sources


def intake_sources():
    return {"status": "passed", "sources": built_in_sources(), "reuse": "clean_room_only"}
