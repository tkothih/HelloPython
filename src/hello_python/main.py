class MyClass:
    def __init__(self, counter: int):
        self.counter = counter

    def add(self, n1: int) -> int:
        return n1 + self.counter
