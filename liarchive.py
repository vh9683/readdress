#! /usr/bin/python3.4


import sys
from redis import StrictRedis
from bson import Binary
import pymongo
import pickle

if __name__ == '__main__':
  instance = sys.argv[-1]

  if not instance:
    instance = "1"

  try:
    conn=pymongo.MongoClient()
    print ("Connected successfully!!!")
  except pymongo.errors.ConnectionFailure as e:
    print ("Could not connect to MongoDB: %s" % e )

  db = conn.inbounddb.liMailBackUp
  r = StrictRedis()

  while True:
    item = r.brpoplpush('liarchive', 'liarchivebackup')
    itemlist = pickle.loads(item)
    if (len(itemlist) == 2):
      db.insert( { 'tagged':itemlist[0], 'inboundJson':Binary(str(itemlist[1]).encode(), 128)} )
    else:
        continue
    print ('len of liarchivebackup is : {}'.format(r.llen('liarchivebackup')))
    r.lrem('liarchivebackup', 0, item)
    print ('len of liarchivebackup is : {}'.format(r.llen('liarchivebackup')))

