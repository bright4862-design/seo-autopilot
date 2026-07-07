from app.artifact_filter import MAX_ARTIFACT_EVIDENCE, is_artifact_url, record_artifact


def test_detects_encoded_base64_path():
    assert is_artifact_url("https://example.com/section/L2NyZWRpdC1pbW1vYmlsaWVyL2luZGV4Lmh0bWw=")


def test_does_not_flag_normal_slug():
    assert not is_artifact_url("https://example.com/pret-immobilier/type-prets/")


def test_artifact_evidence_cap():
    artifacts = []
    for index in range(MAX_ARTIFACT_EVIDENCE + 10):
        record_artifact(artifacts, f"https://example.com/L2NyZWRpdC1pbW1vYmlsaWVyL2luZGV4Lmh0bWw={index}", "internal_link", "/", "bad")
    assert len(artifacts) == MAX_ARTIFACT_EVIDENCE
