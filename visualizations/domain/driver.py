class Driver:
    def __init__(self, number: int, name: str, team_name: str):
        self.__number: int = number
        self.__name: str = name
        self.__team_name: str = team_name

    def get_number(self) -> int:
        return self.__number

    def get_name(self) -> str:
        return self.__name

    def get_team_name(self) -> str:
        return self.__team_name
