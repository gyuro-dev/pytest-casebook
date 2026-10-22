"""まだ直していない不具合のある関数。"""


def title_case(text: str) -> str:
    # 不具合: 「o'neil」が「O'Neil」ではなく「O'neil」になる
    return text.capitalize()
