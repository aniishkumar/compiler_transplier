class CompileError(Exception):
    def __init__(self, message: str, line: int = 1, phase: str = "compile"):
        self.message, self.line, self.phase = message, line, phase
        super().__init__(f"{phase} error on line {line}: {message}")
