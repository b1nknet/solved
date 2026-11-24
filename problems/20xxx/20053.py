n = int(input())

for _ in range(n):
    m = int(input())
    x = list(map(int, input().split()))
    print(min(x), max(x))