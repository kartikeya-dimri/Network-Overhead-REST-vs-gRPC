#!/bin/bash
for i in {10..321}; do
    head -n $i scripts/run_experiment.sh > test_part.sh
    if ! bash -n test_part.sh 2>&1 | grep -q "unexpected EOF"; then
        continue
    else
        echo "Fails at line $i"
        break
    fi
done
