# Given a list of numbers, one shall calculate the maximum number and return it.

from typing import List


# 1. assume the first value is the maximum
def calculate_max(numbers: List[int]) -> int:
    biggest = numbers[0]
    return biggest

def test_calculate_max():
    numbers = [5, 12, 1, 0]
    biggest = calculate_max(numbers)
    assert biggest == 12