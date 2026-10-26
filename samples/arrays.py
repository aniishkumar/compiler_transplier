def square(n):
    return n * n

numbers = [2, 4, 6, 8, 10]
sum = 0
for i in range(5):
    sum += square(numbers[i])
print(sum)
