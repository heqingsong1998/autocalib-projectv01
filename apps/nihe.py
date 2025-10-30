import numpy as np

# 数据点
x = np.array([
16.94736842,
1428.013699,
2834.082192,
4193.041096,
2822.027397,
1424.914286,
-5.410958904
])
y = np.array([
-0.000515497,
-4.865272647,
-9.717071418,
-14.59966962,
-9.753219176,
-4.893535082,
-0.045798524
])

# 构建设计矩阵
A = np.vstack([x**2, x, np.ones(len(x))]).T

# 求解最小二乘问题
coefficients = np.linalg.lstsq(A, y, rcond=None)[0]

# 输出系数
a, b, c = coefficients
print(f"a = {a}")
print(f"b = {b}")
print(f"c = {c}")