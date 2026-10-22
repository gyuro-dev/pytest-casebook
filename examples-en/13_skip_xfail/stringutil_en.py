"""A function with a bug that has not been fixed yet."""


def title_case(text: str) -> str:
    # bug: "o'neil" becomes "O'neil" instead of "O'Neil"
    return text.capitalize()
