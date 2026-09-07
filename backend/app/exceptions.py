"""Domain failures that can be translated at the API boundary."""


class ETFNotFoundError(Exception):
    """An explicit ETF lookup found no record for the requested codes."""

    def __init__(self, *codes: str) -> None:
        self.codes = tuple(code.strip().upper() for code in codes)
        super().__init__(*self.codes)
