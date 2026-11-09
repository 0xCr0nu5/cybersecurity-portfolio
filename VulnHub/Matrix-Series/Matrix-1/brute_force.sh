#!/bin/bash

prefix="k1ll0r"
output="wordlist.txt"
charset=({a..z} {0..9})
count=0

> "$output"  # clear/create the file

for c1 in "${charset[@]}"; do
    for c2 in "${charset[@]}"; do
        echo "${prefix}${c1}${c2}" >> "$output"
        count=$(( count + 1 ))
    done
done

echo "[+] Done! $count combinations saved to $output"

