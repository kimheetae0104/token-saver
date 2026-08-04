def describe_grade(score):
    grades = [
        (90, "A", "Excellent work"),
        (80, "B", "Good work"),
        (70, "C", "Average work"),
        (60, "D", "Below average work"),
    ]

    for threshold, letter, quality in grades:
        if score >= threshold:
            return f"{quality}, grade: {letter}"

    return "Failing work, grade: F"
