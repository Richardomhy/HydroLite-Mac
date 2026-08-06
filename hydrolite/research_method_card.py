from hydrolite.research_registry import NOTICE, built_in_sources


def method_cards():
    return [{"method_id": row["source_id"], "notice": NOTICE, "borrowed_concepts": row["borrowed_concepts"], "excluded_elements": row["excluded_elements"]} for row in built_in_sources()]
