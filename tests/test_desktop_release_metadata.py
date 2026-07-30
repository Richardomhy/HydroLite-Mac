from hydrolite.release_metadata import build_release_manifest, compare_release_versions, validate_release_manifest


def test_release_metadata_is_consistent():
    manifest = build_release_manifest()
    assert validate_release_manifest(manifest)["status"] == "passed"
    assert manifest["channel"] == "dev"
    assert compare_release_versions("0.7.0", "0.7.1") < 0
