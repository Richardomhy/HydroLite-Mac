from pathlib import Path


def test_lineage_parent_child_and_acyclic(tmp_path: Path):
    from hydrolite.data_lineage import add_lineage_operation, list_dataset_children, list_dataset_parents, validate_lineage_graph
    from hydrolite.workspace import create_workspace

    root = tmp_path / "workspace"
    create_workspace(root, "Lineage")
    add_lineage_operation("raw", "standard", "field_mapping", root, source_checksum="a", output_checksum="b", reproducible_command="demo")
    assert list_dataset_children("raw", root) == ["standard"]
    assert list_dataset_parents("standard", root) == ["raw"]
    assert validate_lineage_graph(root)["status"] == "passed"
