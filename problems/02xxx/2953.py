ul = []
for i in range(5):
    score = sum(list(map(int, input().split())))
    ul.append({ "num": i + 1, "score": score })

sl = sorted(ul, key=(lambda x: x['score']), reverse=True)
print(sl[0]['num'], sl[0]['score'])