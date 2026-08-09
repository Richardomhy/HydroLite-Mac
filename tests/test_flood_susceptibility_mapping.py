import json
import pandas as pd

from hydrolite.flood_susceptibility_mapping import classify_relative_susceptibility, validate_susceptibility_map, write_susceptibility_geojson


def test_mapping_outputs_relative_susceptibility_not_risk(tmp_path):
    frame = pd.DataFrame({"point_id": ["A", "B"], "longitude": [113.0, 113.1], "latitude": [22.0, 22.1], "probability": [.1, .9]})
    frame["relative_susceptibility_class"] = classify_relative_susceptibility(frame.probability).astype(str)
    frame["is_flood_risk"] = False
    output = write_susceptibility_geojson(frame, tmp_path / "map.geojson")
    assert validate_susceptibility_map(frame)["status"] == "passed"
    assert all(feature["properties"]["is_flood_risk"] is False for feature in json.loads(output.read_text())["features"])
