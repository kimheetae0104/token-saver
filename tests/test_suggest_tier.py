"""measure.suggest_tier() — 라우팅 사다리 추천 결정론 함수 검증. pytest 없이 stdlib assert만.
실행: python3 tests/test_suggest_tier.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import measure


def test_oracle_present_recommends_haiku():
    """오라클 있으면 의미론적 위험·고위험 플래그와 무관하게 Haiku 1차(실험8 그대로)."""
    rec = measure.suggest_tier(has_oracle=True, semantic_risk=True, high_stakes=True)
    assert rec["tier"] == "haiku", rec
    assert rec["effort"] == "low", rec
    assert rec["escalation"] == ["haiku(프롬프트 강화 재시도)", "sonnet"], rec


def test_semantic_risk_and_high_stakes_without_oracle_recommends_opus():
    rec = measure.suggest_tier(has_oracle=False, semantic_risk=True, high_stakes=True)
    assert rec["tier"] == "opus", rec
    assert rec["effort"] == "high", rec


def test_semantic_risk_alone_recommends_sonnet():
    rec = measure.suggest_tier(has_oracle=False, semantic_risk=True, high_stakes=False)
    assert rec["tier"] == "sonnet", rec
    assert rec["effort"] == "high", rec


def test_high_stakes_alone_recommends_sonnet():
    rec = measure.suggest_tier(has_oracle=False, semantic_risk=False, high_stakes=True)
    assert rec["tier"] == "sonnet", rec
    assert rec["effort"] == "default", rec


def test_large_batch_without_oracle_recommends_haiku_batch_judge():
    """N>=20, 오라클 없음, 위험 플래그 없음 → 실험9 후속2·6 배치판정 사다리."""
    rec = measure.suggest_tier(has_oracle=False, batch_size=20)
    assert rec["tier"] == "haiku", rec
    assert rec["escalation"] == ["sonnet(배치판정)"], rec
    assert rec["note"] is not None and "원문 그대로" in rec["note"], rec


def test_small_batch_without_oracle_recommends_sonnet_direct():
    """N<10, 오라클 없음 → 실험9: 에스컬레이션 1건에도 역전되므로 Sonnet 직행."""
    rec = measure.suggest_tier(has_oracle=False, batch_size=5)
    assert rec["tier"] == "sonnet", rec
    assert rec["escalation"] is None, rec


def test_mid_batch_gap_defaults_to_sonnet():
    """N 10~19는 실측 공백 구간 — 안전하게 Sonnet, 근거 있는 양쪽 케이스와 구분되는 note."""
    rec = measure.suggest_tier(has_oracle=False, batch_size=15)
    assert rec["tier"] == "sonnet", rec
    assert "공백" in rec["reason"], rec


def test_default_call_matches_small_batch_case():
    """인자 없이 호출 시 batch_size=1 기본값 → 소표본 분기와 동일 결과."""
    default = measure.suggest_tier()
    small = measure.suggest_tier(batch_size=1)
    assert default == small, (default, small)
    assert default["tier"] == "sonnet", default


def test_fable_never_auto_recommended():
    """fable은 BASE_IN에 있는 티어지만(가격표) 어떤 조합에서도 자동 추천하지 않는다 —
    이 프로젝트 실험(7~9)이 haiku/sonnet/opus 경계만 다뤘고 fable 관련 실측이 없어서
    (실측만, 벤더 주장 없음 원칙). 조합 폭발을 피해 대표 케이스만 스윕."""
    combos = [
        dict(has_oracle=o, batch_size=b, semantic_risk=s, high_stakes=h)
        for o in (True, False) for b in (1, 5, 15, 20, 50)
        for s in (True, False) for h in (True, False)
    ]
    for kwargs in combos:
        rec = measure.suggest_tier(**kwargs)
        assert rec["tier"] != "fable", (kwargs, rec)


def test_suggest_tier_text_matches_cli_and_mcp_shared_format():
    text = measure.suggest_tier_text(has_oracle=True)
    rec = measure.suggest_tier(has_oracle=True)
    assert text.startswith(f"추천: {rec['tier']}(effort={rec['effort']})"), text
    assert rec["reason"] in text, text


def main():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
