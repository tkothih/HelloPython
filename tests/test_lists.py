# Given a list of numbers, one shall calculate the maximum number and return it.

from typing import List


# 1. assume the first value is the maximum
# 2. iterate over the list
# 3. compare biggest with the current element and if smaller update biggest
def calculate_max(numbers: List[int]) -> int:
    biggest = numbers[0] # 1
    for number in numbers: # 2
        if biggest < number: # 3
            biggest=number
    return biggest

def test_calculate_max():
    numbers = [5, 12, 1, 0]
    biggest = calculate_max(numbers)
    assert biggest == 12

def calculate_min(numbers: List[int]) -> int:
    smallest = numbers[0]
    for number in numbers:
        if smallest > number:
            smallest=number
    return smallest

def test_calculate_min():
    numbers = [5, 12, 1]
    result = calculate_min(numbers)
    assert result == 1


# calculate the sum of all numbers
# initialise the sum to zero

def calculate_average(numbers: List[int]) -> float:
    average = 0
    sum=0
    number_of_elements=0
    for number in numbers:
        sum=sum+number
        number_of_elements=number_of_elements+1
    
    average=sum/number_of_elements
    return average

def test_calculate_average():
    numbers = [2,3,4]
    result = calculate_average(numbers)
    assert result == 3
    numbers = [10,5,2,-1]
    result = calculate_average(numbers)
    assert result == 4
    numbers = [10,5]
    result = calculate_average(numbers)
    assert result == 7.5