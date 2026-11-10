def decode(s):
    vals = [ord(c) & 31 for c in s]
    out = ''
    for j in range(0, len(vals) - 1, 2):
        out += chr((vals[j] + vals[j+1] - 1) % 26 + 97)
    return out

print(decode('hEzAdCfHzA'), '::', decode('hEzAdCfHzAhAiJzAeIaDjBcBhHgAzAfHfN'))
