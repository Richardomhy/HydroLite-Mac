from pathlib import Path

import pytest

from hydrolite.config import load_case


def test_missing_yaml_field_has_clear_error(tmp_path: Path):
    case = tmp_path / "bad.yaml"
    case.write_text(
        """
name: bad
model:
  time_step_hours: 1
outputs:
  directory: outputs/bad
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="root.inputs"):
        load_case(case)


def test_output_inside_data_raw_is_rejected(tmp_path: Path):
    case = tmp_path / "bad.yaml"
    case.write_text(
        """
name: bad
model:
  time_step_hours: 1
inputs:
  directory: data_demo
  rainfall: rainfall.csv
  subcatchments: subcatchments.csv
  reaches: reaches.csv
outputs:
  directory: data_raw/generated
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="data_raw"):
        load_case(case)
