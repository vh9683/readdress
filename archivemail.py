#! /usr/bin/python3.4


import sys
from settings import r
from bson import Binary

if __name__ == '__main__':
    instance = sys.argv[2]

    if not instance:
        instance = "1"

    while True:
        item = r.brpop('mailarchive')
        print ("instance : {} -> {}".format(instance, str(item)))
