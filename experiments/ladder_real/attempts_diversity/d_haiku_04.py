def describe_grade(score):
    grades = [
        (90, "A", "Excellent"),
        (80, "B", "Good"),
        (70, "C", "Average"),
        (60, "D", "Below average"),
        (0, "F", "Failing")
    ]

    for threshold, letter, description in grades:
        if score >= threshold:
            return f"{description} work, grade: {letter}"
