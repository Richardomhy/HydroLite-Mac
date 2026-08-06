from hydrolite.research_registry import built_in_sources


def audit_source_licenses():
    return [{"source_id": row["source_id"], "status": row["source_license"], "integration_mode": row["implementation_mode"]} for row in built_in_sources()] + [{"source_id": "ruiduobao/gee-dataset-intelligence-skill", "status": "license_file_missing", "integration_mode": "method_inspired_clean_room"}]
