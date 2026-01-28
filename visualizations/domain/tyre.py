class Tyre:
    def __init__(self, compound: str, new: bool):
        self.__compound = compound
        self.__new = new

    def get_compound(self) -> str:
        return self.__compound

    def get_new(self) -> bool:
        return self.__new
