def describe_grade(score):
    grades = [
        (90, "A", "Excellent work, grade: "),
        (80, "B", "Good work, grade: "),
        (70, "C", "Average work, grade: "),
        (60, "D", "Below average work, grade: "),
        (0, "F", "Failing work, grade: ")
    ]
    for threshold, letter, prefix in grades:
        if score >= threshold:
            return prefix + letter
