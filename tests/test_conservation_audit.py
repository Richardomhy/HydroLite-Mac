from hydrolite.conservation import run_conservation_audit
def test_conservation_audit():
    result=run_conservation_audit('projects/qgis_workflow_project','output/conservation')
    assert result['status']=='needs_review'
