from dataclasses import replace

import pytest

from hydrolite.emission_factor_approval import approve_factor, approved_project_factors, factor_stage, build_project_factor_set
from hydrolite.source_load_ledger import calculate_generated_load
from test_source_load_ledger import _factor, _activity


def factor(**kwargs):
    meta = dict(title="Anonymous fixture", issuer="test institution", year=2020, original_unit="kg/year/person", normalized_unit="kg/year/person", method="source generation", reference="fixture:1", retrieval_date="2026-01-01", applicability="fixture only", limitations="not real project")
    return _factor(evidence=meta, **kwargs)


def test_official_requires_separate_project_decision():
    f = factor()
    assert approved_project_factors([f], [], "p1") == []
    a = approve_factor(f, "p1", "approved_for_project", actor="tester", comment="Verified test")
    assert len(approved_project_factors([f], [a], "p1")) == 1
    assert approved_project_factors([f], [a], "other") == []
    assert approved_project_factors([replace(f, value=2)], [a], "p1") == []
    rejected = approve_factor(f, "p1", "rejected", actor="tester", comment="withdrawn")
    assert approved_project_factors([f], [a, rejected], "p1") == []


@pytest.mark.parametrize("changes", [{"example": True}, {"factor_stage": "export_factor"}, {"notes": "径流流失系数"}, {"notes": "入河系数"}])
def test_unsafe_factor_cannot_be_approved(changes):
    with pytest.raises(ValueError): approve_factor(factor(**changes), "p1", "approved_for_project", actor="t", comment="test")


def test_stage_blocks_generated_load():
    with pytest.raises(ValueError): calculate_generated_load(_activity(), factor(notes="输出系数"))
    assert calculate_generated_load(_activity(), factor())["central"] == pytest.approx(1)
    assert build_project_factor_set("p", [], [], ["TN"]).unresolved_categories == ("TN",)


def test_approval_comment_and_metadata_required():
    with pytest.raises(ValueError): approve_factor(factor(), "p", "approved_for_project", actor="t", comment="")
    with pytest.raises(ValueError): approve_factor(_factor(), "p", "approved_for_project", actor="t", comment="test")
