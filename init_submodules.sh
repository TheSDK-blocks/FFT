#!/bin/sh
DIR="$( cd "$( dirname $0 )" && pwd )"
cd $DIR

for module in \
    ./chisel; do
    git submodule update --init $module
done


