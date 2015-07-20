#!/usr/bin/python3.4
import urllib 
import sys
import urllib.parse
from urllib.parse import unquote

with open(sys.argv[1],'r') as f:
    records = f.readlines()
    s = records[0]
    text = urllib.parse.unquote(s)
    #text = unquote(unquote(records[0].encode('ascii')))
    #text = urllib.parse.unquote(records[0].encode('ascii')).decode('utf-8')
    print("{}".format(text))
