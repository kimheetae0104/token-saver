"""라우팅 난이도 실험용 샘플. 미묘한 버그가 하나 있다."""


def running_max(xs):
    """각 위치까지의 '누적 최댓값' 리스트를 반환한다.
    예: [3, 1, 5, 2] -> [3, 3, 5, 5]
    """
    out = []
    m = 0
    for x in xs:
        m = max(m, x)
        out.append(m)
    return out


def normalize(xs):
    """리스트를 합이 1이 되도록 정규화."""
    total = sum(xs)
    return [x / total for x in xs]
