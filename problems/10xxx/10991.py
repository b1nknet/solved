n = int(input())

for i in range(1, n + 1):
    print(' ' * (n - i), end='')
    print(('').join(['* ' for _ in range(i)])[:-1])