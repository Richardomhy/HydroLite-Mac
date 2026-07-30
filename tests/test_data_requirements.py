from pathlib import Path


def test_requirement_matrix_lists_upload_retrieval_and_missing(tmp_path: Path):
    from hydrolite.data_requirements import build_project_data_requirement_matrix, find_auto_retrievable_datasets, find_missing_required_datasets
    from hydrolite.workspace import create_workspace

    root = tmp_path / "workspace"
    create_workspace(root, "Requirements")
    matrix = build_project_data_requirement_matrix("full_modeling_workflow", root)
    assert not matrix.empty
    assert not find_missing_required_datasets(matrix).empty
    assert not find_auto_retrievable_datasets(matrix).empty
