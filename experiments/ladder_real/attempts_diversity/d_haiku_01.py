def describe_grade(score):
    thresholds = [
        (90, "A", "Excellent work"),
        (80, "B", "Good work"),
        (70, "C", "Average work"),
        (60, "D", "Below average work"),
    ]

    for min_score, letter, desc in thresholds:
        if score >= min_score:
            return f"{desc}, grade: {letter}"

    return "Failing work, grade: F"
